"""ProcureAI Stage 5.4D: atomic rollback and safe retry.

Runs in-process against ONLY the isolated procureai-test Turso database.
Do not run concurrently with other database users/tests.
"""

import os
import uuid
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlparse

import libsql
import pytest
from dotenv import dotenv_values
from fastapi import HTTPException

ROOT = Path(__file__).resolve().parent.parent
CONFIG = dotenv_values(ROOT / '.env.test')
BUDGET_ID = 'BUD-MAINT-2026'
OFFER_ID = 'OFF-1002'
UNIT_CENTS = 2350


def checked_credentials():
    url = CONFIG.get('TURSO_DATABASE_URL') or ''
    token = CONFIG.get('TURSO_AUTH_TOKEN') or ''
    parsed = urlparse(url)
    host = (parsed.hostname or '').lower()
    if not (parsed.scheme == 'libsql'
            and host.startswith('procureai-test-')
            and host.endswith('.turso.io')
            and token
            and CONFIG.get('ENABLE_DEMO_WRITES') == 'true'
            and CONFIG.get('DEMO_REQUESTER_ID') == 'EMP-1001'
            and CONFIG.get('DEMO_APPROVER_ID') == 'EMP-1002'):
        pytest.fail('STOP: .env.test does not match the isolated ProcureAI test database.')
    return url, token


@contextmanager
def database(url, token):
    db = libsql.connect(database=url, auth_token=token)
    try:
        db.execute('PRAGMA foreign_keys=ON')
        yield db
    finally:
        db.close()


def snapshot(db, key):
    committed = db.execute(
        'SELECT committed_amount_cents FROM budgets WHERE budget_id=?',
        (BUDGET_ID,)
    ).fetchone()
    assert committed is not None
    rows = db.execute(
        'SELECT requisition_id, total_amount_cents, requisition_status FROM purchase_requisitions '
        'WHERE idempotency_key=?', (key,)
    ).fetchall()
    return committed[0], rows


def cleanup_by_key(url, token, key):
    """Only delete our own successful retry, if any, in one transaction."""
    with database(url, token) as db:
        db.execute('BEGIN IMMEDIATE')
        try:
            row = db.execute(
                'SELECT requisition_id,budget_id,total_amount_cents,requisition_status '
                'FROM purchase_requisitions WHERE idempotency_key=?', (key,)
            ).fetchone()
            if row:
                pr_id, budget_id, cents, status = row
                assert budget_id == BUDGET_ID
                db.execute('DELETE FROM audit_logs WHERE requisition_id=?', (pr_id,))
                db.execute('DELETE FROM approval_requests WHERE requisition_id=?', (pr_id,))
                db.execute('DELETE FROM purchase_requisitions WHERE requisition_id=?', (pr_id,))
                assert db.execute('SELECT changes()').fetchone()[0] == 1
                if status in ('APPROVED', 'PENDING_APPROVAL'):
                    db.execute(
                        'UPDATE budgets SET committed_amount_cents=committed_amount_cents-? '
                        'WHERE budget_id=? AND committed_amount_cents>=?',
                        (cents, budget_id, cents)
                    )
                    assert db.execute('SELECT changes()').fetchone()[0] == 1
            db.commit()
        except Exception:
            db.rollback()
            raise


@pytest.mark.parametrize('failure_point,quantity', [
    ('PR', 10),    # Fault after budget reservation, before requisition INSERT
    ('APR', 40),   # Fault after requisition INSERT, before approval INSERT
])
def test_rollback_then_safe_retry(monkeypatch, failure_point, quantity):
    url, token = checked_credentials()

    # Configure import to use the isolated TEST database, never the development one.
    monkeypatch.setenv('PROCUREAI_ENV', 'test')
    from api import requisitions
    assert os.environ.get('PROCUREAI_ENV') == 'test'
    assert urlparse(os.environ.get('TURSO_DATABASE_URL', '')).hostname == urlparse(url).hostname

    key = f'recovery-{uuid.uuid4().hex}'
    request = requisitions.RequisitionRequest(
        offer_id=OFFER_ID, quantity=quantity, idempotency_key=key, confirmed=True
    )
    with database(url, token) as db:
        before, original = snapshot(db, key)
        assert not original
        budget = db.execute(
            'SELECT allocated_amount_cents,spent_amount_cents FROM budgets WHERE budget_id=?',
            (BUDGET_ID,)
        ).fetchone()
        assert budget and budget[0] - before - budget[1] >= quantity * UNIT_CENTS

    real_new_id = requisitions.new_id

    def inject_failure(prefix):
        if prefix == failure_point:
            raise RuntimeError(f'CONTROLLED_TEST_FAILURE_{failure_point}')
        return real_new_id(prefix)

    try:
        # The monkeypatch lasts only for the first attempt.
        with monkeypatch.context() as injection:
            injection.setattr(requisitions, 'new_id', inject_failure)
            with pytest.raises(HTTPException) as failure:
                requisitions.create_requisition(request)
            assert failure.value.status_code == 503, str(failure.value)

        with database(url, token) as db:
            after_failure, rows = snapshot(db, key)
            assert after_failure == before, 'Budget commitment leaked after injected failure'
            assert not rows, 'Partial requisition remained after injected failure'
            orphan_approvals = db.execute(
                'SELECT COUNT(*) FROM approval_requests WHERE requisition_id IN '
                '(SELECT requisition_id FROM purchase_requisitions WHERE idempotency_key=?)', (key,)
            ).fetchone()[0]
            assert orphan_approvals == 0
            audit_matches = db.execute(
                'SELECT COUNT(*) FROM audit_logs WHERE details_json LIKE ?',
                (f'%{key}%',)
            ).fetchone()[0]
            assert audit_matches == 0

        # Retry with exactly the same idempotency key, now without injected failure.
        created = requisitions.create_requisition(request)
        assert created['duplicate_request'] is False
        assert created['total_amount_cents'] == quantity * UNIT_CENTS
        with database(url, token) as db:
            after_retry, rows = snapshot(db, key)
            assert len(rows) == 1
            assert after_retry == before + quantity * UNIT_CENTS
            pr_id = rows[0][0]
            approval_count = db.execute(
                'SELECT COUNT(*) FROM approval_requests WHERE requisition_id=?',
                (pr_id,)
            ).fetchone()[0]
            audit_count = db.execute(
                "SELECT COUNT(*) FROM audit_logs WHERE requisition_id=? AND action='REQUISITION_CREATED'",
                (pr_id,)
            ).fetchone()[0]
            assert approval_count == (1 if quantity == 40 else 0)
            assert audit_count == 1

        replay = requisitions.create_requisition(request)
        assert replay['duplicate_request'] is True
        assert replay['requisition_id'] == created['requisition_id']
        with database(url, token) as db:
            after_replay, rows = snapshot(db, key)
            assert len(rows) == 1
            assert after_replay == after_retry, 'Idempotent retry duplicated budget commitment'
    finally:
        cleanup_by_key(url, token, key)

    with database(url, token) as db:
        restored, remaining = snapshot(db, key)
        assert restored == before, 'Cleanup did not restore original budget'
        assert not remaining
