
import os

import httpx
import pytest
from dotenv import load_dotenv

load_dotenv()

API_BASE = os.getenv(
    "CATALOG_API_BASE_URL",
    "http://127.0.0.1:8000"
).rstrip("/")


@pytest.fixture(scope="module")
def client():
    with httpx.Client(
        base_url=API_BASE,
        timeout=20.0
    ) as api_client:
        yield api_client


def test_backend_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_search_helmets(client):
    response = client.get(
        "/api/v1/materials",
        params={"search": "helmet"}
    )

    assert response.status_code == 200

    materials = response.json()["materials"]

    assert isinstance(materials, list)
    assert any(
        item["material_id"] == "MAT-1001"
        for item in materials
    )


def test_supplier_offers(client):
    response = client.get(
        "/api/v1/materials/MAT-1001/supplier-offers"
    )

    assert response.status_code == 200

    offers = response.json()["offers"]
    offer_ids = {
        offer["offer_id"]
        for offer in offers
    }

    assert "OFF-1002" in offer_ids

    # Expired contract and inactive supplier
    # offers must not be returned.
    assert "OFF-1003" not in offer_ids
    assert "OFF-1010" not in offer_ids


def test_budget_validation(client):
    response = client.post(
        "/api/v1/procurement/validate",
        json={
            "offer_id": "OFF-1002",
            "quantity": 10
        }
    )

    assert response.status_code == 200

    result = response.json()

    assert result["purchase"]["requested_amount_cents"] == 23500
    assert result["validation_status"] in (
        "VALIDATION_PASSED",
        "APPROVAL_REQUIRED",
        "BUDGET_INSUFFICIENT",
        "APPROVAL_ROUTE_UNAVAILABLE"
    )
