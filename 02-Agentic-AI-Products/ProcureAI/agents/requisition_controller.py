
import json
import os
import uuid

from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


API_BASE_URL = os.getenv(
    "CATALOG_API_BASE_URL",
    "http://127.0.0.1:8000"
).rstrip("/")


def call_api(path, payload):
    request = Request(
        url=f"{API_BASE_URL}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    try:
        with urlopen(request, timeout=20) as response:
            return (
                response.status,
                json.loads(response.read().decode("utf-8"))
            )

    except HTTPError as error:
        try:
            details = json.loads(
                error.read().decode("utf-8")
            )
        except (ValueError, UnicodeError):
            details = {"detail": "Request failed"}

        return error.code, details

    except (URLError, TimeoutError):
        return 503, {
            "detail": "ProcureAI backend unavailable"
        }


def submit_with_confirmation(offer_id, quantity):
    """
    Trusted terminal-side submission flow.

    The employee must explicitly confirm the
    verified purchase summary before any write.
    """

    offer_id = offer_id.strip().upper()

    # ------------------------------------------
    # 1. Validate using the backend
    # ------------------------------------------

    status, result = call_api(
        "/api/v1/procurement/validate",
        {
            "offer_id": offer_id,
            "quantity": quantity
        }
    )

    if status != 200:
        print("\nValidation could not be completed.")
        print(result.get("detail", result))
        return

    validation_status = result["validation_status"]

    if validation_status not in (
        "VALIDATION_PASSED",
        "APPROVAL_REQUIRED"
    ):
        print("\nSubmission blocked.")
        print(f"Reason: {validation_status}")
        return

    purchase = result["purchase"]
    budget = result["budget"]
    policy = result["policy"]

    total_cents = purchase["requested_amount_cents"]
    currency = purchase["currency"]

    # ------------------------------------------
    # 2. Show authoritative purchase summary
    # ------------------------------------------

    print("\n========================================")
    print("       PURCHASE CONFIRMATION")
    print("========================================")

    print(f"Material: {purchase['material_name']}")
    print(f"Material ID: {purchase['material_id']}")
    print(f"Supplier: {purchase['supplier_name']}")
    print(f"Offer ID: {purchase['offer_id']}")
    print(f"Quantity: {purchase['quantity']}")
    print(f"Currency: {currency}")

    print(
        f"Total: {total_cents / 100:,.2f} {currency}"
    )

    print(
        f"Available budget: "
        f"{budget['available_budget_cents'] / 100:,.2f} "
        f"{currency}"
    )

    print(
        "Manager approval required: "
        f"{policy['manager_approval_required']}"
    )

    print(
        "\nThis action will create a requisition "
        "and commit the verified budget amount."
    )

    # ------------------------------------------
    # 3. Explicit application-side confirmation
    # ------------------------------------------

    answer = input(
        "\nSubmit purchase requisition? "
        "Type YES to confirm: "
    ).strip()

    if answer != "YES":
        print("\nSubmission cancelled. No PR created.")
        return

    # ------------------------------------------
    # 4. Create idempotency key outside the LLM
    # ------------------------------------------

    idempotency_key = str(uuid.uuid4())

    # ------------------------------------------
    # 5. Submit to controlled backend
    # ------------------------------------------

    status, response = call_api(
        "/api/v1/requisitions",
        {
            "offer_id": offer_id,
            "quantity": quantity,
            "idempotency_key": idempotency_key,
            "confirmed": True
        }
    )

    if status not in (200, 201):
        print("\nRequisition submission not confirmed.")
        print(response.get("detail", response))
        print(
            "Submission key:",
            idempotency_key
        )
        print(
            "Do not retry with a different key "
            "until the original result is checked."
        )
        return

    print("\n========================================")
    print("      REQUISITION CREATED")
    print("========================================")

    print(
        f"PR Number: {response['requisition_id']}"
    )
    print(f"Status: {response['status']}")
    print(
        "Budget committed: ",
        response["budget_committed"]
    )

    if response["manager_approval_required"]:
        print(
            f"Pending manager: {response['approver_id']}"
        )

    print(
        "\nThis is a simulated requisition. "
        "No purchase order was placed."
    )
