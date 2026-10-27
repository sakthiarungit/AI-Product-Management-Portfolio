
import asyncio
import json
import logging
import os

from urllib.parse import urlencode, quote
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

import streamlit as st

from agents.procurement_agent import create_procurement_agent


# ==================================================
# 1. Application Configuration
# ==================================================

st.set_page_config(
    page_title="ProcureAI",
    page_icon="🛒",
    layout="wide"
)

logger = logging.getLogger("procureai.streamlit")

API_BASE_URL = os.getenv(
    "CATALOG_API_BASE_URL",
    "http://127.0.0.1:8000"
).rstrip("/")


# ==================================================
# 2. Backend API Helper
# ==================================================

def call_api(path, method="GET", payload=None):
    """
    Call the ProcureAI FastAPI backend.

    API failures are returned explicitly.
    The UI must not manufacture missing data.
    """

    headers = {"Accept": "application/json"}
    data = None

    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = Request(
        url=f"{API_BASE_URL}{path}",
        data=data,
        headers=headers,
        method=method
    )

    try:
        with urlopen(request, timeout=20) as response:
            return json.loads(
                response.read().decode("utf-8")
            )

    except HTTPError as error:
        try:
            details = json.loads(
                error.read().decode("utf-8")
            )
        except (ValueError, UnicodeError):
            details = {}

        message = details.get(
            "detail",
            f"API returned HTTP {error.code}"
        )

        raise RuntimeError(str(message)) from error

    except (URLError, TimeoutError) as error:
        raise RuntimeError(
            "Cannot reach the ProcureAI backend. "
            "Check FastAPI on port 8000."
        ) from error


# ==================================================
# 3. Procurement State
# ==================================================

def empty_procurement():
    return {
        "material_id": None,
        "offer_id": None,
        "quantity": 1,
        "validation": None,
        "requisition_id": None
    }


if "messages" not in st.session_state:
    st.session_state.messages = []

if "agent" not in st.session_state:
    st.session_state.agent = create_procurement_agent()

if "agent_session" not in st.session_state:
    st.session_state.agent_session = (
        st.session_state.agent.create_session()
    )

if "procurement" not in st.session_state:
    st.session_state.procurement = empty_procurement()

if "material_results" not in st.session_state:
    st.session_state.material_results = []

if "supplier_offers" not in st.session_state:
    st.session_state.supplier_offers = []

if "material_search_query" not in st.session_state:
    st.session_state.material_search_query = "helmet"

if "material_search_loaded" not in st.session_state:
    st.session_state.material_search_loaded = False


def clear_validation():
    st.session_state.procurement["validation"] = None
    st.session_state.procurement["requisition_id"] = None


def select_material(material_id):
    previous = st.session_state.procurement["material_id"]

    if previous == material_id:
        return

    st.session_state.procurement["material_id"] = material_id
    st.session_state.procurement["offer_id"] = None

    st.session_state.supplier_offers = []
    clear_validation()


def select_offer(offer_id):
    if st.session_state.procurement["offer_id"] != offer_id:
        st.session_state.procurement["offer_id"] = offer_id
        clear_validation()


def select_quantity(quantity):
    quantity = int(quantity)

    if st.session_state.procurement["quantity"] != quantity:
        st.session_state.procurement["quantity"] = quantity
        clear_validation()


# ==================================================
# 4. Material Search and Supplier Lookup
# ==================================================

def search_materials(query):
    parameters = urlencode({"search": query})

    result = call_api(
        f"/api/v1/materials?{parameters}"
    )

    materials = result.get("materials", [])

    st.session_state.material_results = materials
    st.session_state.material_search_loaded = True

    # A new search resets the existing selection.
    select_material(None)

    return materials


def load_supplier_offers(material_id):
    result = call_api(
        "/api/v1/materials/"
        f"{quote(material_id, safe='')}"
        "/supplier-offers"
    )

    st.session_state.supplier_offers = result.get(
        "offers",
        []
    )

    return st.session_state.supplier_offers


# ==================================================
# 5. Header
# ==================================================

st.title("🛒 ProcureAI")

st.caption(
    "Enterprise Agentic AI Procurement Assistant "
    "— Synthetic Data Demonstration"
)

st.info(
    "Discover materials, compare contracted suppliers, "
    "and validate purchasing requests. "
    "Requisition submission through this web interface "
    "will be added in the next stage."
)


# ==================================================
# 6. Purchasing Workspace
# ==================================================

st.subheader("Procurement Workspace")

with st.container(border=True):

    st.markdown("#### Step 1 — Find and select a material")

    search_col, button_col = st.columns([4, 1])

    with search_col:
        material_query = st.text_input(
            "Search materials",
            key="material_search_query",
            placeholder="e.g. helmet, gloves"
        )

    with button_col:
        st.write("")
        st.write("")
        search_clicked = st.button(
            "Search Catalog",
            use_container_width=True
        )

    if search_clicked:
        try:
            if len(material_query.strip()) < 2:
                st.warning(
                    "Enter at least two characters."
                )
            else:
                search_materials(
                    material_query.strip()
                )
                st.session_state.supplier_offers = []

        except Exception as error:
            logger.exception("Material search failed")
            st.error(str(error))

    materials = st.session_state.material_results

    if st.session_state.material_search_loaded:

        if not materials:
            st.warning("No matching active materials found.")

        else:
            material_lookup = {
                item["material_id"]: item
                for item in materials
            }

            material_ids = list(material_lookup)

            current_material = (
                st.session_state.procurement["material_id"]
            )

            options = [None] + material_ids

            material_index = (
                options.index(current_material)
                if current_material in options
                else 0
            )

            selected_material = st.selectbox(
                "Select material",
                options=options,
                index=material_index,
                format_func=lambda value: (
                    "Choose a material"
                    if value is None
                    else (
                        f"{value} — "
                        f"{material_lookup[value]['material_name']}"
                    )
                )
            )

            select_material(selected_material)

            if selected_material:

                material = material_lookup[
                    selected_material
                ]

                st.caption(
                    f"Category: {material['category']} "
                    f"• UOM: {material['uom']}"
                )

                st.write(
                    material.get("description")
                    or "No description provided."
                )

    st.divider()

    st.markdown(
        "#### Step 2 — Select an eligible supplier"
    )

    procurement = st.session_state.procurement
    material_id = procurement["material_id"]

    if material_id:

        if st.button("Load Eligible Supplier Offers"):

            try:
                load_supplier_offers(material_id)
                select_offer(None)

            except Exception as error:
                logger.exception("Offer retrieval failed")
                st.error(str(error))

        offers = st.session_state.supplier_offers

        if offers:

            st.write("Eligible contracted offers")

            for offer in offers:

                st.write(
                    f"**{offer['supplier_name']}** "
                    f"— {offer['currency']} "
                    f"{offer['unit_price']:.2f} / unit "
                    f"— Lead time: "
                    f"{offer['lead_time_days']} days"
                )

            offer_lookup = {
                offer["offer_id"]: offer
                for offer in offers
            }

            options = [None] + list(offer_lookup)

            selected_offer = st.selectbox(
                "Choose supplier offer",
                options=options,
                format_func=lambda value: (
                    "Choose a supplier"
                    if value is None
                    else (
                        f"{offer_lookup[value]['supplier_name']}"
                        f" — {value}"
                    )
                )
            )

            select_offer(selected_offer)

        else:
            st.caption(
                "Load supplier offers after selecting a material."
            )

    else:
        st.caption(
            "Select a material before choosing a supplier."
        )

    st.divider()

    st.markdown("#### Step 3 — Enter purchase quantity")

    quantity = st.number_input(
        "Quantity",
        min_value=1,
        max_value=10000,
        value=int(
            st.session_state.procurement["quantity"]
        ),
        step=1
    )

    select_quantity(quantity)

    st.divider()

    st.markdown(
        "#### Step 4 — Validate budget and policy"
    )

    procurement = st.session_state.procurement

    can_validate = bool(
        procurement["material_id"]
        and procurement["offer_id"]
        and procurement["quantity"] > 0
    )

    if st.button(
        "Validate Purchase",
        type="primary",
        disabled=not can_validate
    ):

        try:

            result = call_api(
                "/api/v1/procurement/validate",
                method="POST",
                payload={
                    "offer_id": procurement["offer_id"],
                    "quantity": procurement["quantity"]
                }
            )

            st.session_state.procurement[
                "validation"
            ] = result

        except Exception as error:
            clear_validation()
            logger.exception("Purchase validation failed")
            st.error(str(error))


# ==================================================
# 7. Display Authoritative Validation
# ==================================================

validation = st.session_state.procurement["validation"]

if validation:

    st.subheader("Purchase Validation Result")

    with st.container(border=True):

        status = validation["validation_status"]

        if status == "VALIDATION_PASSED":
            st.success(
                "Budget and configured policy checks passed."
            )

        elif status == "APPROVAL_REQUIRED":
            st.warning(
                "Budget check passed. Manager approval required."
            )

        else:
            st.error(
                f"Purchase cannot proceed: {status}"
            )

        purchase = validation["purchase"]
        budget = validation["budget"]
        policy = validation["policy"]

        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric(
                "Purchase Amount",
                f"${purchase['requested_amount_cents'] / 100:,.2f}"
            )

        with col2:
            st.metric(
                "Available Budget",
                f"${budget['available_budget_cents'] / 100:,.2f}"
            )

        with col3:
            st.metric(
                "Budget Check",
                budget["budget_check"]
            )

        st.write(
            f"**Material:** {purchase['material_name']}"
        )

        st.write(
            f"**Supplier:** {purchase['supplier_name']}"
        )

        st.write(
            f"**Quantity:** {purchase['quantity']} "
            f"{purchase['uom']}"
        )

        st.write(
            "**Manager approval required:** "
            + (
                "Yes"
                if policy["manager_approval_required"]
                else "No"
            )
        )

        st.caption(
            "This is read-only validation. "
            "No requisition has been created and "
            "no budget has been reserved."
        )


# ==================================================
# 8. Conversational AI Assistant
# ==================================================

st.divider()

st.subheader("ProcureAI Assistant")

st.caption(
    "Use natural language to search materials, "
    "compare suppliers, and understand purchasing rules."
)

for message in st.session_state.messages:

    with st.chat_message(message["role"]):
        st.markdown(message["content"])


user_prompt = st.chat_input(
    "Ask ProcureAI about your procurement request..."
)

if user_prompt:

    st.session_state.messages.append({
        "role": "user",
        "content": user_prompt
    })

    with st.chat_message("user"):
        st.markdown(user_prompt)

    with st.chat_message("assistant"):

        with st.spinner("ProcureAI is working..."):

            try:

                async def run_agent():
                    return await st.session_state.agent.run(
                        user_prompt,
                        session=st.session_state.agent_session
                    )

                response = asyncio.run(run_agent())
                answer = response.text

            except Exception as error:

                logger.exception("Agent request failed")

                answer = (
                    "ProcureAI couldn't complete this request. "
                    "Please try again."
                )

                # Local development diagnostics only.
                st.error(
                    f"Agent error type: "
                    f"{type(error).__name__}"
                )

        st.markdown(answer)

    st.session_state.messages.append({
        "role": "assistant",
        "content": answer
    })


# ==================================================
# 9. Sidebar — Structured Procurement State
# ==================================================

with st.sidebar:

    st.header("ProcureAI")

    st.write("**Current capabilities**")

    st.write("Material discovery")
    st.write("Supplier comparison")
    st.write("Budget and policy validation")

    st.divider()

    st.write("**Purchasing session**")

    procurement = st.session_state.procurement

    st.write(
        "**Material:**",
        procurement["material_id"] or "Not selected"
    )

    st.write(
        "**Offer:**",
        procurement["offer_id"] or "Not selected"
    )

    st.write(
        "**Quantity:**",
        procurement["quantity"]
    )

    if procurement["validation"]:

        st.write(
            "**Validation:**",
            procurement["validation"][
                "validation_status"
            ]
        )

    else:
        st.write(
            "**Validation:** Not completed"
        )

    st.divider()

    if st.button(
        "Start New Conversation",
        use_container_width=True
    ):

        st.session_state.messages = []

        st.session_state.agent_session = (
            st.session_state.agent.create_session()
        )

        st.session_state.procurement = (
            empty_procurement()
        )

        st.session_state.material_results = []
        st.session_state.supplier_offers = []
        st.session_state.material_search_loaded = False

        st.rerun()

    st.caption(
        "Synthetic procurement sandbox. "
        "Not connected to a production ERP."
    )
