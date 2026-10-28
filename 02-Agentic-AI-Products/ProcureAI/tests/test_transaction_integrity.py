"""Transaction tests for the isolated ProcureAI test API (port 8001).

Synthetic data only. Tests remove requisitions they create and restore their
outstanding budget commitments. Never run against the development API.
"""

import uuid
from pathlib import Path
from contextlib import contextmanager
from urllib.parse import urlparse

import httpx
import libsql
import pytest
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parent.parent
TEST_CONFIG = dotenv_values(ROOT / ".env.test")
API_URL = "http://127.0.0.1:8001"


@contextmanager
def isolated_db_connection():
    url = TEST_CONFIG.get("TURSO_DATABASE_URL") or ""
    token = TEST_CONFIG.get("TURSO_AUTH_TOKEN") or ""
    hostname = (urlparse(url).hostname or "").lower()
    if not hostname.startswith("procureai-test-") or not hostname.endswith(".turso.io"):
        pytest.fail("Write tests blocked: .env.test does not target procureai-test")
    if not token:
        pytest.fail("Write tests blocked: .env.test has no Turso token")
    connection = libsql.connect(database=url, auth_token=token)
    try:
        yield connection
    finally:
        connection.close()


def test_db_connection():
    """Verify the isolated Turso database is reachable and seeded."""
    with isolated_db_connection() as db:
        count = db.execute("SELECT COUNT(*) FROM materials").fetchone()[0]
        assert count == 6, f"Expected six test materials, found {count}"


@pytest.fixture(scope="module")
def sandbox():
    # Check identity BEFORE any POST that could change purchasing state.
    with httpx.Client(base_url=API_URL, timeout=30) as client:
        try:
            r = client.get("/health")
            r.raise_for_status()
        except httpx.HTTPError as error:
            pytest.fail(f"Test API on 8001 is unavailable: {error}")
        if r.json().get("environment") != "test":
            pytest.fail("Write tests blocked: port 8001 is not in test environment")

        with isolated_db_connection() as db:
            db.execute("PRAGMA foreign_keys=ON")
            budget = db.execute("""
                SELECT allocated_amount_cents-committed_amount_cents-spent_amount_cents
                FROM budgets WHERE cost_center_id='CC-MAINT-SEA'
            """).fetchone()
            if budget is None or budget[0] < 200000:
                pytest.fail("Test budget needs at least $2,000 of available funds")

        keys = []
        try:
            yield client, keys
        finally:
            # Only delete test-generated requests; prevent leaking money commitments.
            # Even if a test fails after a successful POST, the key identifies its PR.
            if keys:
                with isolated_db_connection() as db:
                    db.execute("PRAGMA foreign_keys=ON")
                    db.execute("BEGIN IMMEDIATE")
                    try:
                        for key in keys:
                            row = db.execute("""
                                SELECT requisition_id,budget_id,total_amount_cents,requisition_status
                                FROM purchase_requisitions WHERE idempotency_key=?
                            """, (key,)).fetchone()
                            if not row:
                                continue
                            pr_id, budget_id, cents, status = row
                            db.execute("DELETE FROM audit_logs WHERE requisition_id=?", (pr_id,))
                            db.execute("DELETE FROM approval_requests WHERE requisition_id=?", (pr_id,))
                            db.execute("DELETE FROM purchase_requisitions WHERE requisition_id=?", (pr_id,))
                            if status in ("APPROVED", "PENDING_APPROVAL"):
                                db.execute("""
                                    UPDATE budgets SET committed_amount_cents=committed_amount_cents-?
                                    WHERE budget_id=? AND committed_amount_cents>=?
                                """, (cents, budget_id, cents))
                                assert db.execute("SELECT changes()").fetchone()[0] == 1
                        db.commit()
                    except Exception:
                        db.rollback()
                        raise


def new_key(keys):
    key = str(uuid.uuid4())
    keys.append(key)
    return key


def make_pr(client, keys, quantity):
    data = {"offer_id": "OFF-1002", "quantity": quantity,
            "idempotency_key": new_key(keys), "confirmed": True}
    response = client.post("/api/v1/requisitions", json=data)
    assert response.status_code == 201, response.text
    return response.json(), data


def approval_for(pr_id):
    with isolated_db_connection() as db:
        row = db.execute("""
            SELECT approval_id,approval_status FROM approval_requests WHERE requisition_id=?
        """, (pr_id,)).fetchone()
        return row


def committed():
    with isolated_db_connection() as db:
        return db.execute("""
            SELECT committed_amount_cents FROM budgets
            WHERE cost_center_id='CC-MAINT-SEA'
        """).fetchone()[0]


def test_small_purchase_and_idempotency(sandbox):
    client, keys = sandbox
    before = committed()
    result, req = make_pr(client, keys, 10)
    assert result["status"] == "APPROVED"
    assert result["total_amount_cents"] == 23500
    assert committed() == before + 23500
    assert approval_for(result["requisition_id"]) is None

    replay = client.post("/api/v1/requisitions", json=req)
    assert replay.status_code == 201
    assert replay.json()["duplicate_request"] is True
    assert replay.json()["requisition_id"] == result["requisition_id"]
    assert committed() == before + 23500

    conflict = client.post("/api/v1/requisitions", json={**req,"quantity":11})
    assert conflict.status_code == 409
    assert committed() == before + 23500


def test_manager_approval_and_repeated_decision(sandbox):
    client, keys = sandbox
    before = committed()
    result, _ = make_pr(client, keys, 40)
    assert result["status"] == "PENDING_APPROVAL"
    assert result["total_amount_cents"] == 94000
    approval = approval_for(result["requisition_id"])
    assert approval and approval[1] == "PENDING"
    assert committed() == before + 94000
    url = f"/api/v1/approvals/{approval[0]}/approve"
    resp = client.post(url, json={"comment":"Approved by automated test","confirmed":True})
    assert resp.status_code == 200, resp.text
    assert resp.json()["requisition_status"] == "APPROVED"
    assert committed() == before + 94000
    again = client.post(url, json={"comment":"Repeat","confirmed":True})
    assert again.status_code == 200
    assert again.json()["already_decided"] is True
    assert committed() == before + 94000


def test_manager_rejection_releases_budget(sandbox):
    client, keys = sandbox
    before = committed()
    result, _ = make_pr(client, keys, 40)
    assert result["status"] == "PENDING_APPROVAL"
    approval = approval_for(result["requisition_id"])
    assert approval and approval[1] == "PENDING"
    assert committed() == before + 94000
    url = f"/api/v1/approvals/{approval[0]}/reject"
    resp = client.post(url, json={"comment":"Rejected by automated test","confirmed":True})
    assert resp.status_code == 200, resp.text
    assert resp.json()["requisition_status"] == "REJECTED"
    assert resp.json()["budget_released"] is True
    assert committed() == before
    with isolated_db_connection() as db:
        actions = {r[0] for r in db.execute(
            "SELECT action FROM audit_logs WHERE requisition_id=?",
            (result["requisition_id"],)).fetchall()}
    assert {"REQUISITION_CREATED", "REQUISITION_REJECTED"} <= actions


def test_insufficient_budget_rejected_without_writes(sandbox):
    client, keys = sandbox
    before = committed()
    key = new_key(keys)
    response = client.post("/api/v1/requisitions", json={
        "offer_id":"OFF-1002", "quantity":10000,
        "idempotency_key":key, "confirmed":True})
    assert response.status_code == 409, response.text
    assert committed() == before
    with isolated_db_connection() as db:
        assert db.execute(
            "SELECT COUNT(*) FROM purchase_requisitions WHERE idempotency_key=?",
            (key,)).fetchone()[0] == 0
