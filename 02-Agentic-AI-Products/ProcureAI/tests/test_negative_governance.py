"""ProcureAI Stage 5.4A — non-mutating negative governance API tests.

Run only against the isolated ProcureAI test API on 127.0.0.1:8001.
Every POST in this suite is intentionally invalid and must fail before writes.
"""
from __future__ import annotations

import uuid

import httpx
import pytest

TEST_API_BASE = "http://127.0.0.1:8001"


@pytest.fixture(scope="module")
def client():
    with httpx.Client(base_url=TEST_API_BASE, timeout=25.0) as api_client:
        response = api_client.get("/health")
        assert response.status_code == 200, (
            "Test server not available on port 8001. Do not use port 8000."
        )
        health = response.json()
        assert health.get("environment") == "test", (
            "Refusing to run: API does not report environment=test."
        )
        yield api_client


def blocked_requisition(client, *, offer_id="OFF-1002", quantity=10, confirmed=False):
    return client.post(
        "/api/v1/requisitions",
        json={
            "offer_id": offer_id,
            "quantity": quantity,
            "idempotency_key": f"negative-{uuid.uuid4().hex}",
            "confirmed": confirmed,
        },
    )


def test_missing_human_confirmation_is_blocked(client):
    response = blocked_requisition(client, confirmed=False)
    assert response.status_code == 400, response.text


def test_expired_contract_offer_is_blocked(client):
    response = blocked_requisition(client, offer_id="OFF-1003", confirmed=True)
    assert response.status_code == 422, response.text


def test_inactive_supplier_offer_is_blocked(client):
    response = blocked_requisition(client, offer_id="OFF-1010", confirmed=True)
    assert response.status_code == 422, response.text


def test_unknown_supplier_offer_is_blocked(client):
    response = blocked_requisition(client, offer_id="OFF-9999", confirmed=True)
    assert response.status_code == 422, response.text


def test_invalid_quantity_is_blocked_by_schema(client):
    response = blocked_requisition(client, quantity=0, confirmed=True)
    assert response.status_code == 422, response.text


def test_unknown_manager_approval_is_not_found(client):
    response = client.post(
        "/api/v1/approvals/APR-DOES-NOT-EXIST/approve",
        json={"comment": "Negative test", "confirmed": True},
    )
    assert response.status_code == 404, response.text
