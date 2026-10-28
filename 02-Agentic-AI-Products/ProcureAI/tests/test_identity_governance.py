"""Stage 5.4B: controlled negative identity tests.

Run from ProcureAI root: python -m pytest tests/test_identity_governance.py -v
Uses the isolated .env.test Turso database and in-process backend functions.
No development API or development database is used.
"""

import uuid
from pathlib import Path
from contextlib import contextmanager
from urllib.parse import urlparse

import httpx
import libsql
import pytest
from dotenv import dotenv_values
from fastapi import HTTPException

ROOT = Path(__file__).resolve().parent.parent
CONFIG = dotenv_values(ROOT / ".env.test")
API_BASE = "http://127.0.0.1:8001"


def verified_config():
    url = CONFIG.get("TURSO_DATABASE_URL") or ""
    token = CONFIG.get("TURSO_AUTH_TOKEN") or ""
    host = (urlparse(url).hostname or "").lower()
    if not (urlparse(url).scheme == "libsql"
            and host.startswith("procureai-test-")
            and host.endswith(".turso.io") and token):
        pytest.fail("Refusing identity tests: .env.test is not the isolated Turso test DB")
    if (CONFIG.get("ENABLE_DEMO_WRITES") != "true"
            or CONFIG.get("DEMO_REQUESTER_ID") != "EMP-1001"
            or CONFIG.get("DEMO_APPROVER_ID") != "EMP-1002"):
        pytest.fail("Unexpected synthetic test identities or disabled writes in .env.test")
    return url, token


@pytest.fixture(scope="module")
def setup():
    url, token = verified_config()
    try:
        response = httpx.get(API_BASE + "/health", timeout=10)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        pytest.fail(f"Isolated test API unavailable on 8001: {exc}")
    if response.json().get("environment") != "test":
        pytest.fail("Refusing tests: port 8001 does not report test mode")
    with database((url, token)) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        row = connection.execute(
            "SELECT employee_status FROM employees WHERE employee_id='EMP-1004'"
        ).fetchone()
        if row != ("INACTIVE",):
            pytest.fail("Synthetic EMP-1004 must be inactive")
        row = connection.execute(
            "SELECT employee_role, employee_status FROM employees WHERE employee_id='EMP-1003'"
        ).fetchone()
        if row != ("REQUESTER", "ACTIVE"):
            pytest.fail("Synthetic EMP-1003 must be an active, non-manager employee")
        row = connection.execute(
            "SELECT allocated_amount_cents-committed_amount_cents-spent_amount_cents "
            "FROM budgets WHERE cost_center_id='CC-MAINT-SEA'"
        ).fetchone()
        if not row or row[0] < 94000:
            pytest.fail("At least $940 of free test budget is required")
    return url, token


@contextmanager
def database(config):
    url, token = config
    connection = libsql.connect(database=url, auth_token=token)
    try:
        yield connection
    finally:
        connection.close()


def test_inactive_requester_cannot_create_requisition(setup, monkeypatch):
    # Set the process environment BEFORE importing API modules. This cannot
    # change the running test API (which is a separate process).
    monkeypatch.setenv("PROCUREAI_ENV", "test")
    from api.requisitions import RequisitionRequest, create_requisition

    # Modify only this pytest process. The API on 8001 stays EMP-1001.
    monkeypatch.setenv("DEMO_REQUESTER_ID", "EMP-1004")
    key = f"inactive-{uuid.uuid4().hex}"
    with database(setup) as db:
        before = db.execute(
            "SELECT committed_amount_cents FROM budgets WHERE cost_center_id='CC-MAINT-SEA'"
        ).fetchone()[0]
    with pytest.raises(HTTPException) as caught:
        create_requisition(RequisitionRequest(
            offer_id="OFF-1002", quantity=10, idempotency_key=key, confirmed=True
        ))
    assert caught.value.status_code == 403
    with database(setup) as db:
        after = db.execute(
            "SELECT committed_amount_cents FROM budgets WHERE cost_center_id='CC-MAINT-SEA'"
        ).fetchone()[0]
        created = db.execute(
            "SELECT COUNT(*) FROM purchase_requisitions WHERE idempotency_key=?", (key,)
        ).fetchone()[0]
    assert after == before
    assert created == 0


def test_unassigned_employee_cannot_approve(setup, monkeypatch):
    monkeypatch.setenv("PROCUREAI_ENV", "test")
    from api.approvals import process_approval_decision

    # Make a legitimate pending requisition via the test-only API.
    key = f"unauthorized-{uuid.uuid4().hex}"
    payload = {"offer_id": "OFF-1002", "quantity": 40,
               "idempotency_key": key, "confirmed": True}
    pr_id = None
    approval_id = None
    try:
        with httpx.Client(base_url=API_BASE, timeout=25) as client:
            response = client.post("/api/v1/requisitions", json=payload)
        assert response.status_code == 201, response.text
        pr_id = response.json()["requisition_id"]
        assert response.json()["status"] == "PENDING_APPROVAL"
        with database(setup) as db:
            approval = db.execute(
                "SELECT approval_id, approval_status, approver_id FROM approval_requests "
                "WHERE requisition_id=?", (pr_id,)
            ).fetchone()
            assert approval and approval[1:] == ("PENDING", "EMP-1002")
            approval_id = approval[0]
            before = db.execute(
                "SELECT committed_amount_cents FROM budgets WHERE cost_center_id='CC-MAINT-SEA'"
            ).fetchone()[0]

        # The attempted approval is made by EMP-1003, not assigned EMP-1002.
        monkeypatch.setenv("DEMO_APPROVER_ID", "EMP-1003")
        with pytest.raises(HTTPException) as caught:
            process_approval_decision(approval_id, "APPROVED", "Unauthorized test")
        assert caught.value.status_code == 403

        with database(setup) as db:
            row = db.execute(
                "SELECT approval_status FROM approval_requests WHERE approval_id=?",
                (approval_id,)
            ).fetchone()
            pr = db.execute(
                "SELECT requisition_status FROM purchase_requisitions WHERE requisition_id=?",
                (pr_id,)
            ).fetchone()
            after = db.execute(
                "SELECT committed_amount_cents FROM budgets WHERE cost_center_id='CC-MAINT-SEA'"
            ).fetchone()[0]
        assert row == ("PENDING",)
        assert pr == ("PENDING_APPROVAL",)
        assert after == before
    finally:
        # Strictly remove only the known requisition created by this test.
        # If interrupted before this cleanup, investigate by idempotency_key.
        with database(setup) as db:
            db.execute("PRAGMA foreign_keys = ON")
            db.execute("BEGIN IMMEDIATE")
            try:
                row = db.execute(
                    "SELECT requisition_id,budget_id,total_amount_cents,requisition_status "
                    "FROM purchase_requisitions WHERE idempotency_key=?", (key,)
                ).fetchone()
                if row:
                    rid, budget_id, cents, status = row
                    db.execute("DELETE FROM audit_logs WHERE requisition_id=?", (rid,))
                    db.execute("DELETE FROM approval_requests WHERE requisition_id=?", (rid,))
                    db.execute("DELETE FROM purchase_requisitions WHERE requisition_id=?", (rid,))
                    if status in ("APPROVED", "PENDING_APPROVAL"):
                        db.execute(
                            "UPDATE budgets SET committed_amount_cents=committed_amount_cents-? "
                            "WHERE budget_id=? AND committed_amount_cents>=?",
                            (cents, budget_id, cents)
                        )
                        assert db.execute("SELECT changes()").fetchone()[0] == 1
                db.commit()
            except Exception:
                db.rollback()
                raise
