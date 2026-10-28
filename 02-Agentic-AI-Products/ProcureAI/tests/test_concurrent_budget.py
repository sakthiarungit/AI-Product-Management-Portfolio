
"""ProcureAI Stage 5.4C — Concurrent Budget Testing.

Run ONLY against procureai-test and the isolated test API
at http://127.0.0.1:8001.

The test sends two competing purchase requisitions.
Only one should succeed when the budget can fund
one purchase but not both.

Never run concurrently with other test/database users.
"""

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from threading import Barrier
from urllib.parse import urlparse
import uuid

import httpx
import libsql
import pytest
from dotenv import dotenv_values


ROOT = Path(__file__).resolve().parent.parent
CONFIG = dotenv_values(ROOT / ".env.test")

API_BASE = "http://127.0.0.1:8001"
COST_CENTER = "CC-MAINT-SEA"
OFFER_ID = "OFF-1002"
UNIT_CENTS = 2350


# --------------------------------------------------
# 1. Verify the isolated database
# --------------------------------------------------

def verified_config():
    url = CONFIG.get("TURSO_DATABASE_URL") or ""
    token = CONFIG.get("TURSO_AUTH_TOKEN") or ""

    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()

    valid = (
        parsed.scheme == "libsql"
        and host.startswith("procureai-test-")
        and host.endswith(".turso.io")
        and bool(token)
        and CONFIG.get("ENABLE_DEMO_WRITES") == "true"
        and CONFIG.get("DEMO_REQUESTER_ID") == "EMP-1001"
    )

    if not valid:
        pytest.fail(
            "Refusing concurrency test: "
            "invalid test database configuration."
        )

    return url, token


# --------------------------------------------------
# 2. Database connection
# --------------------------------------------------

@contextmanager
def db_connection(url, token):
    db = libsql.connect(
        database=url,
        auth_token=token
    )

    try:
        db.execute("PRAGMA foreign_keys = ON")
        yield db
    finally:
        db.close()


# --------------------------------------------------
# 3. Read budget
# --------------------------------------------------

def budget_record(db):
    return db.execute(
        """
        SELECT
            budget_id,
            allocated_amount_cents,
            committed_amount_cents,
            spent_amount_cents
        FROM budgets
        WHERE cost_center_id = ?
          AND fiscal_year =
              CAST(strftime('%Y','now') AS INTEGER)
          AND currency = 'USD'
        """,
        (COST_CENTER,)
    ).fetchone()


# --------------------------------------------------
# 4. Submit concurrent request
# --------------------------------------------------

def send_request(payload, barrier):
    try:
        barrier.wait(timeout=15)

        with httpx.Client(
            base_url=API_BASE,
            timeout=httpx.Timeout(40.0)
        ) as client:

            response = client.post(
                "/api/v1/requisitions",
                json=payload
            )

            try:
                body = response.json()
            except ValueError:
                body = {"raw_text": response.text[:500]}

            return {
                "status": response.status_code,
                "body": body,
                "error": None
            }

    except Exception as exc:
        return {
            "status": None,
            "body": None,
            "error": (
                f"{type(exc).__name__}: {exc}"
            )
        }


# --------------------------------------------------
# 5. Read created test requisitions
# --------------------------------------------------

def created_records(db, keys):
    records = []

    for key in keys:
        row = db.execute(
            """
            SELECT
                requisition_id,
                budget_id,
                total_amount_cents,
                requisition_status
            FROM purchase_requisitions
            WHERE idempotency_key = ?
            """,
            (key,)
        ).fetchone()

        if row:
            records.append({
                "requisition_id": row[0],
                "budget_id": row[1],
                "amount_cents": row[2],
                "status": row[3],
                "idempotency_key": key
            })

    return records


# --------------------------------------------------
# 6. Clean up only confirmed test records
# --------------------------------------------------

def cleanup_requests(url, token, keys):
    with db_connection(url, token) as db:
        db.execute("BEGIN IMMEDIATE")

        try:
            for key in keys:
                row = db.execute(
                    """
                    SELECT
                        requisition_id,
                        budget_id,
                        total_amount_cents,
                        requisition_status
                    FROM purchase_requisitions
                    WHERE idempotency_key = ?
                    """,
                    (key,)
                ).fetchone()

                if row is None:
                    continue

                pr_id, budget_id, amount, status = row

                db.execute(
                    "DELETE FROM audit_logs "
                    "WHERE requisition_id = ?",
                    (pr_id,)
                )

                db.execute(
                    "DELETE FROM approval_requests "
                    "WHERE requisition_id = ?",
                    (pr_id,)
                )

                db.execute(
                    "DELETE FROM purchase_requisitions "
                    "WHERE requisition_id = ?",
                    (pr_id,)
                )

                if status in (
                    "PENDING_APPROVAL",
                    "APPROVED"
                ):
                    db.execute(
                        """
                        UPDATE budgets
                        SET committed_amount_cents =
                            committed_amount_cents - ?
                        WHERE budget_id = ?
                          AND committed_amount_cents >= ?
                        """,
                        (amount, budget_id, amount)
                    )

                    changed = db.execute(
                        "SELECT changes()"
                    ).fetchone()[0]

                    assert changed == 1, (
                        "Budget cleanup failed"
                    )

            db.commit()

        except Exception:
            db.rollback()
            raise


# --------------------------------------------------
# 7. Concurrency test
# --------------------------------------------------

def test_simultaneous_requests_cannot_overspend():

    url, token = verified_config()

    # Verify test server
    try:
        response = httpx.get(
            f"{API_BASE}/health",
            timeout=10
        )
        response.raise_for_status()

    except httpx.HTTPError as exc:
        pytest.fail(
            f"Test API unavailable: {exc}"
        )

    assert (
        response.json().get("environment") == "test"
    ), "Refusing test: API is not in test mode"

    # Read initial budget
    with db_connection(url, token) as db:
        budget = budget_record(db)

        assert budget is not None

        budget_id, allocated, committed_before, spent = (
            budget
        )

        available = (
            allocated - committed_before - spent
        )

        assert available >= 94000, (
            "Insufficient test budget for concurrency test"
        )

        price = db.execute(
            """
            SELECT unit_price
            FROM supplier_catalog
            WHERE offer_id = ?
            """,
            (OFFER_ID,)
        ).fetchone()

        assert price is not None
        assert round(float(price[0]) * 100) == UNIT_CENTS

    # Each request fits individually,
    # but both requests cannot fit together.
    quantity = available // (2 * UNIT_CENTS) + 1
    amount = quantity * UNIT_CENTS

    assert 1 <= quantity <= 10000
    assert amount <= available < (2 * amount)

    keys = [
        f"concurrency-{uuid.uuid4().hex}"
        for _ in range(2)
    ]

    payloads = [
        {
            "offer_id": OFFER_ID,
            "quantity": quantity,
            "idempotency_key": key,
            "confirmed": True
        }
        for key in keys
    ]

    barrier = Barrier(2)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(
                send_request,
                payload,
                barrier
            )
            for payload in payloads
        ]

        results = [
            future.result(timeout=55)
            for future in futures
        ]

    print("\nConcurrent API results:")

    for index, result in enumerate(results, 1):
        print(
            f"Request {index}: "
            f"HTTP={result['status']}, "
            f"error={result['error']}, "
            f"body={result['body']}"
        )

    # Always inspect database state before deciding
    # whether this test succeeded.
    with db_connection(url, token) as db:
        current = budget_record(db)
        assert current is not None
        assert current[0] == budget_id

        committed_after = current[2]
        records = created_records(db, keys)

    print("\nDatabase verification:")
    print("Committed before:", committed_before)
    print("Committed after:", committed_after)
    print("Test requisitions:", records)

    # Budget invariant must never be violated.
    assert committed_after + spent <= allocated, (
        "CRITICAL: Budget has been overcommitted"
    )

    statuses = [
        result["status"]
        for result in results
    ]

    # Do not mistake a transport failure for
    # a successful budget rejection.
    transport_failure = any(
        not isinstance(status, int)
        for status in statuses
    )

    if transport_failure:
        pytest.fail(
            "One or more concurrent requests returned "
            "no HTTP response. The database state has "
            "been preserved for investigation. "
            f"Results: {results}; "
            f"Created records: {records}"
        )

    if sorted(statuses) != [201, 409]:
        pytest.fail(
            "Expected one HTTP 201 and one HTTP 409. "
            "The database state has been preserved "
            "for investigation. "
            f"Actual results: {results}; "
            f"Created records: {records}"
        )

    # Confirm the 409 is specifically a budget rejection.
    rejected = next(
        result for result in results
        if result["status"] == 409
    )

    rejection_detail = str(
        (rejected["body"] or {}).get("detail", "")
    ).lower()

    assert "budget" in rejection_detail, (
        f"HTTP 409 was not a budget rejection: "
        f"{rejected['body']}"
    )

    assert len(records) == 1, (
        f"Expected exactly one created requisition: "
        f"{records}"
    )

    assert committed_after == committed_before + amount, (
        "Budget commitment does not match "
        "the accepted requisition"
    )

    # Only clean up after the expected outcome
    # and database state have both been verified.
    cleanup_requests(url, token, keys)

    with db_connection(url, token) as db:
        restored = budget_record(db)

        assert restored is not None
        assert restored[2] == committed_before, (
            "Budget not restored after cleanup"
        )

        assert not created_records(db, keys), (
            "Test requisitions remain after cleanup"
        )

    print(
        "\nConcurrency test passed. "
        "One request accepted, one budget-rejected, "
        "and the test budget restored."
    )
