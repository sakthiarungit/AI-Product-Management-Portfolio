
import asyncio
import json
import os
import re

from pathlib import Path
from typing import Annotated
from urllib.parse import urlencode, quote
from urllib.request import urlopen, Request
from urllib.error import HTTPError, URLError

from azure.identity import AzureCliCredential
from dotenv import load_dotenv
from pydantic import Field

from agent_framework import Agent, tool
from agent_framework.openai import OpenAIChatClient

# Support running as a script or as a Python module.
try:
    from agents.requisition_controller import (
        submit_with_confirmation
    )
except ModuleNotFoundError:
    from requisition_controller import (
        submit_with_confirmation
    )


# ==================================================
# 1. Load Environment Configuration
# ==================================================

project_root = Path(__file__).resolve().parent.parent

load_dotenv(
    project_root / ".env",
    override=True
)

CATALOG_API_BASE_URL = os.getenv(
    "CATALOG_API_BASE_URL",
    "http://127.0.0.1:8000"
).rstrip("/")


# ==================================================
# 2. Shared Read-Only API Helper
# ==================================================

def call_procurement_api(
    url: str,
    service_name: str
) -> str:
    """
    Call a read-only ProcureAI FastAPI endpoint.

    Return the API's JSON response, or a
    structured error that the agent can explain.
    """

    try:
        with urlopen(url, timeout=15) as response:
            return response.read().decode("utf-8")

    except HTTPError as error:

        print(
            f"[TOOL ERROR] {service_name}: "
            f"HTTP {error.code}"
        )

        if error.code == 404:
            return json.dumps({
                "status": "not_found",
                "message": (
                    f"{service_name}: "
                    "requested record not found"
                )
            })

        return json.dumps({
            "status": "error",
            "http_status": error.code,
            "message": (
                f"{service_name} request failed"
            )
        })

    except (URLError, TimeoutError) as error:

        print(
            f"[TOOL ERROR] {service_name}: "
            f"{type(error).__name__}"
        )

        return json.dumps({
            "status": "error",
            "message": (
                f"{service_name} is temporarily "
                "unavailable"
            )
        })


# ==================================================
# 3. Tool 1 — Material Catalog Search
# ==================================================

@tool(approval_mode="never_require")
def search_catalog(
    query: Annotated[
        str,
        Field(
            description=(
                "Material or product description "
                "to search for"
            )
        )
    ]
) -> str:
    """
    Search active materials in the catalog.

    Uses the existing FastAPI material search API.
    """

    parameters = urlencode({
        "search": query
    })

    url = (
        f"{CATALOG_API_BASE_URL}"
        f"/api/v1/materials?{parameters}"
    )

    print(
        f"\n[TOOL CALLED] "
        f"search_catalog(query={query!r})"
    )

    return call_procurement_api(
        url=url,
        service_name="Catalog search"
    )


# ==================================================
# 4. Tool 2 — Eligible Supplier Offers
# ==================================================

@tool(approval_mode="never_require")
def get_supplier_offers(
    material_id: Annotated[
        str,
        Field(
            description=(
                "Verified material identifier, "
                "for example MAT-1001"
            )
        )
    ]
) -> str:
    """
    Retrieve eligible contracted supplier offers.

    Backend checks include:
    - Active material
    - Active supplier
    - Active contract
    - Valid contract dates
    """

    material_id = material_id.strip().upper()

    print(
        f"\n[TOOL CALLED] "
        f"get_supplier_offers("
        f"material_id={material_id!r})"
    )

    if not re.fullmatch(
        r"MAT-[0-9]+",
        material_id
    ):
        return json.dumps({
            "status": "invalid_input",
            "message": "Invalid material ID format"
        })

    url = (
        f"{CATALOG_API_BASE_URL}"
        "/api/v1/materials/"
        f"{quote(material_id, safe='')}"
        "/supplier-offers"
    )

    return call_procurement_api(
        url=url,
        service_name="Supplier offers"
    )


# ==================================================
# 5. Tool 3 — Budget and Policy Validation
# ==================================================

@tool(approval_mode="never_require")
def validate_procurement_request(
    offer_id: Annotated[
        str,
        Field(
            description=(
                "Verified supplier offer identifier, "
                "for example OFF-1002"
            )
        )
    ],
    quantity: Annotated[
        int,
        Field(
            description=(
                "Requested purchase quantity. "
                "Whole number between 1 and 10000."
            ),
            gt=0,
            le=10000
        )
    ]
) -> str:
    """
    Validate a purchasing request using FastAPI.

    The backend checks:
    - Requester and cost center
    - Supplier and contract eligibility
    - Contracted price
    - Available budget
    - Manager approval policy

    Read-only operation:
    No PR creation and no budget commitment.
    """

    offer_id = offer_id.strip().upper()

    print(
        "\n[TOOL CALLED] "
        "validate_procurement_request("
        f"offer_id={offer_id!r}, "
        f"quantity={quantity})"
    )

    if not re.fullmatch(
        r"OFF-[0-9]+",
        offer_id
    ):
        return json.dumps({
            "status": "invalid_input",
            "message": "Invalid supplier offer ID"
        })

    if (
        not isinstance(quantity, int)
        or isinstance(quantity, bool)
        or not 1 <= quantity <= 10000
    ):
        return json.dumps({
            "status": "invalid_input",
            "message": (
                "Quantity must be a whole number "
                "between 1 and 10000"
            )
        })

    url = (
        f"{CATALOG_API_BASE_URL}"
        "/api/v1/procurement/validate"
    )

    payload = json.dumps({
        "offer_id": offer_id,
        "quantity": quantity
    }).encode("utf-8")

    api_request = Request(
        url=url,
        data=payload,
        headers={
            "Content-Type": "application/json"
        },
        method="POST"
    )

    try:
        with urlopen(
            api_request,
            timeout=15
        ) as response:

            return response.read().decode("utf-8")

    except HTTPError as error:

        print(
            "[TOOL ERROR] Procurement validation: "
            f"HTTP {error.code}"
        )

        return json.dumps({
            "status": "validation_error",
            "http_status": error.code,
            "message": (
                "The procurement backend rejected "
                "the request or could not complete "
                "validation. Purchase not cleared."
            )
        })

    except (URLError, TimeoutError) as error:

        print(
            "[TOOL ERROR] Procurement validation: "
            f"{type(error).__name__}"
        )

        return json.dumps({
            "status": "error",
            "message": (
                "Procurement validation service "
                "is unavailable. Purchase not cleared."
            )
        })


# ==================================================
# 6. Create and Configure Procurement Agent
# ==================================================

def create_procurement_agent():

    client = OpenAIChatClient(
        model=os.environ[
            "AZURE_OPENAI_DEPLOYMENT_NAME"
        ],
        base_url=os.environ[
            "AZURE_OPENAI_BASE_URL"
        ],
        credential=AzureCliCredential()
    )

    agent = Agent(
        client=client,
        name="ProcureAI",

        instructions=(
            "You are ProcureAI, an enterprise AI "
            "procurement assistant. "

            "Your responsibilities are material discovery, "
            "supplier comparison, and read-only "
            "procurement validation. "

            # --------------------------------------
            # Capability 1: Material Search
            # --------------------------------------

            "CAPABILITY 1: MATERIAL SEARCH. "

            "When an employee requests materials, "
            "use search_catalog to retrieve active "
            "matching materials. "

            "Use only verified catalog data. "
            "Never invent material IDs, descriptions, "
            "technical specifications, certifications, "
            "or availability. "

            "When multiple materials match, present "
            "the candidates and ask one focused "
            "clarification question. "

            "Do not claim that a material meets "
            "safety-critical requirements without "
            "verified specifications and intended use. "

            # --------------------------------------
            # Capability 2: Supplier Comparison
            # --------------------------------------

            "CAPABILITY 2: SUPPLIER COMPARISON. "

            "When the employee selects a material "
            "and requests supplier options, "
            "use get_supplier_offers. "

            "Use only verified offer IDs, supplier "
            "names, prices, currencies, contract IDs, "
            "and lead times returned by the backend. "

            "The backend enforces supplier and "
            "contract eligibility. "

            "Compare price and lead time, but never "
            "assume the cheapest offer is automatically "
            "the best option. "

            "If no eligible offers exist, "
            "explain that clearly. "

            "Do not invent supplier prices, "
            "inventory availability, or delivery dates. "

            # --------------------------------------
            # Capability 3: Procurement Validation
            # --------------------------------------

            "CAPABILITY 3: PROCUREMENT VALIDATION. "

            "When a verified supplier offer and "
            "quantity are available and the user "
            "requests purchase validation, call "
            "validate_procurement_request. "

            "Do not invent or guess offer IDs. "
            "Use the supplier offers service if "
            "the offer is not yet verified. "

            "The backend determines the authoritative "
            "purchase amount, budget eligibility, "
            "and approval requirements. "

            "Use the backend validation_status "
            "to explain the outcome. "

            "VALIDATION_PASSED means configured "
            "checks passed, but no purchase has "
            "been created or funds reserved. "

            "APPROVAL_REQUIRED means manager approval "
            "is necessary before the purchase is "
            "fully approved. "

            "BUDGET_INSUFFICIENT means the request "
            "cannot proceed without resolving "
            "the budget limitation. "

            "APPROVAL_ROUTE_UNAVAILABLE means no "
            "valid approval route was found. "

            "Never override a backend rejection. "

            "If validation fails or the backend "
            "is unavailable, state that the "
            "purchase has not been cleared. "

            # --------------------------------------
            # Financial Accuracy
            # --------------------------------------

            "FINANCIAL ACCURACY. "

            "Budget and validated purchase amounts "
            "are provided in integer cents. "

            "Convert USD cents into dollars when "
            "presenting the result to employees. "

            "Use the backend-calculated amount "
            "as the authoritative amount. "

            "Do not combine amounts across currencies. "

            "Estimates exclude unknown taxes, "
            "shipping, and other charges. "

            # --------------------------------------
            # Requisition Submission
            # --------------------------------------

            "REQUISITION SUBMISSION. "

            "This terminal application has a "
            "separate trusted submission controller. "

            "The employee may submit a verified "
            "purchase through the application command "
            "'submit OFFER_ID QUANTITY', for example "
            "'submit OFF-1002 10'. "

            "This command is handled by the "
            "application, not by an AI tool. "

            "When an employee asks to create or "
            "submit a requisition in natural language, "
            "explain that they must review and confirm "
            "the purchase using the submit command. "

            "Do not claim you have submitted a PR "
            "or changed a budget through an AI tool. "

            "Do not treat conversational agreement "
            "as confirmed purchasing authorization. "

            "The trusted controller shows a purchase "
            "summary and requires the employee to "
            "type YES before submitting the request. "

            "Do not invent requisition numbers "
            "or claim transactions were completed "
            "without a confirmed backend result. "

            # --------------------------------------
            # Limitations and Error Handling
            # --------------------------------------

            "CURRENT LIMITATIONS. "

            "You cannot confirm physical inventory "
            "availability or reserve stock. "

            "You can validate budgets but cannot "
            "directly reserve, commit, or spend funds. "

            "You cannot directly create, approve, "
            "or reject purchase requisitions. "

            "You cannot create purchase orders "
            "or execute real purchases. "

            "Manager approval remains a separate "
            "human-controlled backend workflow. "

            "Always present backend tool failures "
            "clearly without fabricating results. "

            "Keep responses professional, "
            "clear, concise, and easy to understand."
        ),

        tools=[
            search_catalog,
            get_supplier_offers,
            validate_procurement_request
        ]
    )

    return agent


# ==================================================
# 7. Application Entry Point and Conversation
# ==================================================

async def main():

    print("\n========================================")
    print("       ProcureAI - Procurement Agent")
    print("========================================")

    print("\nWelcome to ProcureAI!")

    print(
        "Search materials, compare suppliers, "
        "validate purchases, or submit a requisition."
    )

    print(
        "\nSubmission command: submit OFF-1002 10"
    )

    print(
        "Type 'exit' to close the application.\n"
    )

    agent = create_procurement_agent()

    # Preserve conversational context until the
    # user closes the terminal application.
    session = agent.create_session()

    while True:

        request = input(
            "Employee: "
        ).strip()

        # ------------------------------------------
        # Exit
        # ------------------------------------------

        if request.lower() in [
            "exit",
            "quit"
        ]:
            print(
                "\nThank you for using ProcureAI."
            )
            break

        # ------------------------------------------
        # Empty Request
        # ------------------------------------------

        if not request:
            print(
                "\nPlease enter a procurement request.\n"
            )
            continue

        # ------------------------------------------
        # Trusted Requisition Submission
        # ------------------------------------------
        # This branch runs outside the AI agent.
        # It controls confirmation and API writes.
        # ------------------------------------------

        if request.lower().split()[0] == "submit":

            parts = request.split()

            if len(parts) != 3:
                print(
                    "\nUsage: submit OFF-1002 10\n"
                )
                continue

            offer_id = parts[1].strip().upper()

            if not re.fullmatch(
                r"OFF-[0-9]+",
                offer_id
            ):
                print(
                    "\nInvalid offer ID. "
                    "Example: OFF-1002\n"
                )
                continue

            try:
                quantity = int(parts[2])

                if not 1 <= quantity <= 10000:
                    raise ValueError()

            except ValueError:
                print(
                    "\nQuantity must be a whole "
                    "number between 1 and 10000.\n"
                )
                continue

            print(
                "\nStarting trusted purchase "
                "confirmation..."
            )

            # Do not invoke the language model.
            # The controller validates the request,
            # displays the verified summary, and
            # requires explicit confirmation.
            try:
                submit_with_confirmation(
                    offer_id=offer_id,
                    quantity=quantity
                )

            except Exception as error:
                print(
                    "\nSubmission controller failed: "
                    f"{type(error).__name__}\n"
                )

            print()
            continue

        # ------------------------------------------
        # Ordinary Agent Conversation
        # ------------------------------------------

        print(
            "\nProcessing your request..."
        )

        try:
            response = await agent.run(
                request,
                session=session
            )

            print(
                "\n----------------------------------------"
            )

            print("ProcureAI:")
            print(response.text)

            print(
                "----------------------------------------\n"
            )

        except Exception as error:

            print(
                "\nAgent execution failed: "
                f"{type(error).__name__}: {error}\n"
            )


# ==================================================
# 8. Run Application
# ==================================================

if __name__ == "__main__":
    asyncio.run(main())
