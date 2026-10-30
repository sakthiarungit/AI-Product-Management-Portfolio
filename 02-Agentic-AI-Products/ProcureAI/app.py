"""ProcureAI V1 — conversation-first procurement and manager demo.

Run from ProcureAI project root:
    python -m streamlit run app.py

Requires the existing local FastAPI backend at 127.0.0.1:8000.
Only intended for a local, synthetic-data demonstration. It is NOT an
internet-facing purchasing application or an authentication mechanism.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import uuid
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(page_title="ProcureAI", page_icon="🛒", layout="centered")

LOGGER = logging.getLogger("procureai.streamlit")
API_BASE = os.getenv("CATALOG_API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
DEMO_WRITES_ENABLED = os.getenv("ENABLE_DEMO_WRITES", "false").lower() == "true"


def api(path: str, *, method: str = "GET", payload: dict | None = None) -> dict:
    headers = {"Accept": "application/json"}
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = Request(API_BASE + path, data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=25) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        try:
            body = json.loads(exc.read().decode("utf-8"))
            detail = body.get("detail", body)
        except (ValueError, UnicodeError):
            detail = f"HTTP {exc.code}"
        raise RuntimeError(f"Backend rejected request ({exc.code}): {detail}") from exc
    except (URLError, TimeoutError) as exc:
        raise RuntimeError("Cannot reach FastAPI at " + API_BASE) from exc


def rows(response: dict, key: str) -> list[dict]:
    """Accept the collection shape used in the existing FastAPI project."""
    value = response.get(key, [])
    if not isinstance(value, list):
        raise ValueError(f"Unexpected {key} response from backend")
    return value


def state_init() -> None:
    if "events" not in st.session_state:
        st.session_state.events = []
    if "step" not in st.session_state:
        st.session_state.step = "chat"
    if "materials" not in st.session_state:
        st.session_state.materials = []
    if "offers" not in st.session_state:
        st.session_state.offers = []
    if "material" not in st.session_state:
        st.session_state.material = None
    if "offer" not in st.session_state:
        st.session_state.offer = None
    if "purchase_quantity" not in st.session_state:
        st.session_state.purchase_quantity = 1
    if "reviewed_request" not in st.session_state:
        st.session_state.reviewed_request = None
    if "validation" not in st.session_state:
        st.session_state.validation = None
    if "submit_key" not in st.session_state:
        st.session_state.submit_key = None
    if "submission_result" not in st.session_state:
        st.session_state.submission_result = None
    if "agent_session" not in st.session_state:
        st.session_state.agent_session = None
    if "agent" not in st.session_state:
        st.session_state.agent = None
    if "manager_result" not in st.session_state:
        st.session_state.manager_result = None
    if "manager_approval_id" not in st.session_state:
        st.session_state.manager_approval_id = ""


def message(role: str, text: str) -> None:
    st.session_state.events.append({"role": role, "text": text})


def reset_purchase() -> None:
    st.session_state.step = "chat"
    st.session_state.materials = []
    st.session_state.offers = []
    st.session_state.material = None
    st.session_state.offer = None
    st.session_state.purchase_quantity = 1
    st.session_state.reviewed_request = None
    st.session_state.validation = None
    st.session_state.submit_key = None
    st.session_state.submission_result = None


def invalidate_validation() -> None:
    st.session_state.reviewed_request = None
    st.session_state.validation = None
    st.session_state.submit_key = None
    st.session_state.submission_result = None


def search_term(prompt: str) -> str:
    """Simple deterministic demo search intent, not an LLM purchase decision."""
    lower = prompt.lower()
    # Known seed-catalog vocabulary; users can always use the search control.
    for keyword in ("helmet", "glove", "safety", "industrial", "electrical"):
        if keyword in lower:
            return keyword
    return ""


def requested_quantity(prompt: str) -> int:
    match = re.search(r"\b(\d{1,5})\s+(?:(?:industrial|electrical|safety)\s+)*(?:helmets?|gloves?)\b", prompt, re.I)
    if not match:
        return 1
    return max(1, min(10000, int(match.group(1))))


def start_search(term: str, quantity: int | None = None) -> None:
    result = api("/api/v1/materials?" + urlencode({"search": term}))
    matches = rows(result, "materials")
    reset_purchase()
    if quantity is not None:
        st.session_state.purchase_quantity = quantity
    st.session_state.materials = matches
    if matches:
        st.session_state.step = "material"
        message("assistant", f"I found **{len(matches)}** active material(s) for **{term}**. Select one below.")
    else:
        message("assistant", f"No active materials found for **{term}**. Try another description.")


def choose_material(material_id: str) -> None:
    material = next((m for m in st.session_state.materials if m.get("material_id") == material_id), None)
    if material is None:
        st.error("Material selection has expired. Search again.")
        return
    result = api("/api/v1/materials/" + quote(material_id, safe="") + "/supplier-offers")
    offers = rows(result, "offers")
    st.session_state.material = material
    st.session_state.offers = offers
    st.session_state.offer = None
    invalidate_validation()
    message("user", f"Select {material.get('material_name', material_id)} ({material_id})")
    if offers:
        st.session_state.step = "offer"
        message("assistant", f"I found **{len(offers)} eligible contracted supplier offer(s)**. Choose a supplier below.")
    else:
        st.session_state.step = "chat"
        message("assistant", "There are no currently eligible supplier offers for that material.")


def choose_offer(offer_id: str) -> None:
    offer = next((o for o in st.session_state.offers if o.get("offer_id") == offer_id), None)
    if offer is None:
        st.error("Offer selection has expired. Load offers again.")
        return
    st.session_state.offer = offer
    invalidate_validation()
    st.session_state.step = "quantity"
    message("user", f"Select {offer.get('supplier_name', offer_id)} ({offer_id})")
    message("assistant", "Enter the quantity, then I'll check the authoritative budget and approval policy.")


def validate() -> None:
    offer = st.session_state.offer
    if not offer:
        st.error("Choose an offer first.")
        return
    quantity = int(st.session_state.purchase_quantity)
    result = api("/api/v1/procurement/validate", method="POST", payload={
        "offer_id": offer["offer_id"], "quantity": quantity
    })
    st.session_state.validation = result
    st.session_state.reviewed_request = {
        "offer_id": offer["offer_id"],
        "quantity": quantity,
        "amount_cents": (result.get("purchase") or {}).get("requested_amount_cents"),
        "manager_approval_required": (result.get("policy") or {}).get("manager_approval_required"),
    }
    st.session_state.submit_key = None
    st.session_state.step = "review"
    message("assistant", "The backend has checked the supplier, contract, budget and policy. Review the result below.")


def requisition_status(result: dict) -> str:
    """Read only an explicit status supplied by FastAPI; never infer approval."""
    for source in (result, result.get("requisition"), result.get("data")):
        if not isinstance(source, dict):
            continue
        for key in ("requisition_status", "status"):
            value = source.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return "Not returned by backend"


def submit() -> None:
    """Submit only the immutable offer/quantity snapshot the employee reviewed."""
    validation = st.session_state.validation or {}
    reviewed = st.session_state.reviewed_request
    if validation.get("validation_status") not in ("VALIDATION_PASSED", "APPROVAL_REQUIRED") or not reviewed:
        raise RuntimeError("No valid reviewed transaction is available; validate again.")
    if not DEMO_WRITES_ENABLED:
        raise RuntimeError("Demo writes are disabled.")
    if not st.session_state.offer or reviewed["offer_id"] != st.session_state.offer.get("offer_id"):
        raise RuntimeError("Selected offer changed; validate again.")
    if reviewed["quantity"] != int(st.session_state.purchase_quantity):
        raise RuntimeError("Quantity changed after review; validate again.")

    offer_id = reviewed["offer_id"]
    quantity = reviewed["quantity"]
    # Recheck authoritative price, policy and eligibility before performing a write.
    fresh = api("/api/v1/procurement/validate", method="POST", payload={
        "offer_id": offer_id, "quantity": quantity
    })
    fresh_purchase = fresh.get("purchase") or {}
    fresh_policy = fresh.get("policy") or {}
    if (fresh.get("validation_status") not in ("VALIDATION_PASSED", "APPROVAL_REQUIRED")
            or fresh_purchase.get("requested_amount_cents") != reviewed["amount_cents"]
            or fresh_policy.get("manager_approval_required") != reviewed["manager_approval_required"]):
        invalidate_validation()
        st.session_state.step = "quantity"
        raise RuntimeError("Price, eligibility, or approval policy changed. Revalidate and review before submission.")

    if not st.session_state.submit_key:
        st.session_state.submit_key = str(uuid.uuid4())
    # Keep the same key if a network error leaves the outcome uncertain.
    result = api("/api/v1/requisitions", method="POST", payload={
        "offer_id": offer_id,
        "quantity": quantity,
        "idempotency_key": st.session_state.submit_key,
        "confirmed": True,
    })
    st.session_state.submission_result = result
    st.session_state.step = "submitted"
    pr_id = result.get("requisition_id", "(ID not returned)")
    status = requisition_status(result)
    if (result.get("quantity") != quantity
            or result.get("offer_id") != offer_id
            or result.get("total_amount_cents") != reviewed["amount_cents"]
            or result.get("manager_approval_required") != reviewed["manager_approval_required"]):
        message("assistant", f"**Warning:** The backend created `{pr_id}`, but the returned purchasing details do not match the reviewed request. Stop and investigate; do not retry as a new purchase.")
    else:
        message("assistant", f"**Requisition created:** `{pr_id}` — **{status}**. Confirmed quantity: **{quantity}**. This result comes from FastAPI, not from the AI model.")


def agent_reply(prompt: str) -> str:
    # Lazy loading keeps the procurement controls usable when Azure is unavailable.
    if st.session_state.agent is None:
        from agents.procurement_agent import create_procurement_agent
        st.session_state.agent = create_procurement_agent()
    if st.session_state.agent_session is None:
        st.session_state.agent_session = st.session_state.agent.create_session()

    async def invoke():
        return await st.session_state.agent.run(prompt, session=st.session_state.agent_session)

    return asyncio.run(invoke()).text


def display_material_choice() -> None:
    st.markdown("**Select a material**")
    for m in st.session_state.materials:
        mid = m.get("material_id", "")
        title = m.get("material_name", mid)
        with st.container(border=True):
            st.write(f"**{title}**")
            st.caption(f"Material: {mid} · {m.get('description', '')}")
            if st.button("Select material", key=f"mat_{mid}", use_container_width=True):
                try:
                    choose_material(mid)
                    st.rerun()
                except Exception:
                    LOGGER.exception("Failed selecting material")
                    st.error("Unable to retrieve eligible supplier offers. See terminal logs.")


def display_offer_choice() -> None:
    st.markdown("**Compare and select a supplier**")
    for o in st.session_state.offers:
        oid = o.get("offer_id", "")
        price = o.get("unit_price")
        cost = f"{price:,.2f}" if isinstance(price, (float, int)) else str(price)
        with st.container(border=True):
            st.write(f"**{o.get('supplier_name', 'Supplier')}**")
            st.caption(f"Offer {oid} · {o.get('currency', 'USD')} {cost} per unit · {o.get('lead_time_days', '?')} days")
            if st.button("Choose this offer", key=f"offer_{oid}", use_container_width=True):
                choose_offer(oid)
                st.rerun()


def quantity_changed() -> None:
    st.session_state.purchase_quantity = int(st.session_state.quantity_input)
    invalidate_validation()


def display_quantity() -> None:
    # Widget keys may be removed when hidden; purchase_quantity persists independently.
    st.number_input("Quantity", min_value=1, max_value=10000,
                    value=int(st.session_state.purchase_quantity),
                    step=1, key="quantity_input", on_change=quantity_changed)
    if st.button("Check budget and policy", type="primary"):
        try:
            validate()
            st.rerun()
        except Exception:
            LOGGER.exception("Validation failed")
            st.error("Validation failed. Check FastAPI and the Streamlit terminal.")


def display_review() -> None:
    v = st.session_state.validation or {}
    status = v.get("validation_status", "UNKNOWN")
    purchase = v.get("purchase") or {}
    budget = v.get("budget") or {}
    policy = v.get("policy") or {}
    with st.container(border=True):
        st.markdown("**Purchase review — verified by backend**")
        st.write("Material:", purchase.get("material_name", st.session_state.material.get("material_name", "")))
        st.write("Supplier:", purchase.get("supplier_name", st.session_state.offer.get("supplier_name", "")))
        st.write("Quantity:", purchase.get("quantity", (st.session_state.reviewed_request or {}).get("quantity", st.session_state.purchase_quantity)))
        amount = purchase.get("requested_amount_cents")
        if isinstance(amount, (float, int)):
            st.metric("Validated amount", f"${amount / 100:,.2f}")
        available = budget.get("available_budget_cents")
        if isinstance(available, (float, int)):
            st.caption(f"Available budget at validation: ${available / 100:,.2f}")
        st.write("Validation status:", status)
        st.write("Manager approval required:", "Yes" if policy.get("manager_approval_required") else "No")
        if status in ("VALIDATION_PASSED", "APPROVAL_REQUIRED"):
            st.success("Eligible to request submission; backend will recheck on submit.")
        else:
            st.error("This purchase cannot be submitted in its current state.")
        a, b = st.columns(2)
        with a:
            if st.button("Cancel purchase", use_container_width=True):
                reset_purchase()
                message("assistant", "Purchase cancelled. No requisition was created.")
                st.rerun()
        with b:
            if st.button("Confirm requisition", type="primary", use_container_width=True,
                         disabled=(status not in ("VALIDATION_PASSED", "APPROVAL_REQUIRED") or not DEMO_WRITES_ENABLED)):
                try:
                    submit()
                    st.rerun()
                except Exception:
                    LOGGER.exception("Requisition submission failed; do not change idempotency key")
                    st.error("Submission outcome is uncertain. Do not create a new request; inspect backend records before retrying. The same idempotency key is retained.")
        if not DEMO_WRITES_ENABLED:
            st.caption("Local demo writes are disabled; set ENABLE_DEMO_WRITES=true to enable confirmation.")


def display_submitted() -> None:
    result = st.session_state.submission_result or {}
    with st.container(border=True):
        st.success("Backend requisition response received")
        with st.expander("Backend response — local development only"):
            st.json(result)
        st.write("PR:", result.get("requisition_id", "Not returned"))
        status = requisition_status(result)
        st.write("Status:", status)
        if status == "Not returned by backend":
            st.warning(
                "FastAPI returned a requisition ID but no recognized status field. "
                "Check the backend response below or look up the PR in Turso. "
                "Do not submit another purchase to determine its status."
            )
        st.write("Duplicate request:", result.get("duplicate_request", False))
        approval_id = approval_id_from_response(result)
        if status == "PENDING_APPROVAL":
            st.info("Manager approval is required before this requisition is approved.")
            if approval_id:
                st.code(approval_id, language=None)
                if st.button("Prepare approval ID for manager demo"):
                    st.session_state.manager_approval_id = approval_id
                    st.info("Approval ID prepared. Select Manager demo in the sidebar.")
            else:
                st.caption("Approval ID was not included in the API response. Look it up in Turso before using the manager demo.")
        if st.button("Start another purchase"):
            reset_purchase()
            message("assistant", "Ready for your next procurement request.")
            st.rerun()


def approval_id_from_response(result: dict) -> str | None:
    """Only surface an ID explicitly returned by the backend."""
    candidates = [result, result.get("approval"), result.get("requisition"), result.get("data")]
    for source in candidates:
        if not isinstance(source, dict):
            continue
        value = source.get("approval_id")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def display_manager_demo() -> None:
    """Explicit local-only manager action; never invoked by generated agent text."""
    st.subheader("Manager approval — local demonstration")
    st.warning(
        "Demo-only manager identity from backend configuration. "
        "This screen does not authenticate a user. Do not expose it publicly."
    )
    st.write(
        "The approving manager can enter an approval request ID obtained from "
        "the requester response or the Turso approval_requests table. "
        "The backend must verify the assigned approver and pending status."
    )

    with st.form("manager_decision_form", clear_on_submit=False):
        approval_id = st.text_input(
            "Approval request ID", key="manager_approval_id", placeholder="APR-..."
        ).strip()
        decision = st.radio("Decision", ["Approve", "Reject"], horizontal=True)
        comment = st.text_area("Manager comment", placeholder="Reason for decision")
        confirmed = st.checkbox("I have reviewed the requisition and confirm this decision")
        action = st.form_submit_button(
            "Submit manager decision", type="primary",
            disabled=not DEMO_WRITES_ENABLED
        )

    if not DEMO_WRITES_ENABLED:
        st.info("To test locally, ENABLE_DEMO_WRITES=true must be set on the backend and UI.")

    if action:
        if not approval_id or not re.fullmatch(r"APR-[A-Za-z0-9-]+", approval_id):
            st.error("Enter a valid approval request ID beginning with APR-.")
        elif not confirmed:
            st.error("Explicit manager confirmation is required.")
        elif decision == "Reject" and not comment.strip():
            st.error("A rejection reason is required in this demo UI.")
        else:
            # Backend, not UI or LLM, checks assigned manager, state and writes audit.
            path = "/api/v1/approvals/" + quote(approval_id, safe="")
            path += "/approve" if decision == "Approve" else "/reject"
            try:
                result = api(path, method="POST", payload={
                    "comment": comment.strip(), "confirmed": True
                })
                st.session_state.manager_result = result
                st.success("Backend processed the manager decision.")
            except Exception:
                LOGGER.exception("Manager decision failed for %s", approval_id)
                st.error(
                    "Decision was not confirmed. Check backend records before retrying, "
                    "especially after a timeout. See terminal logs."
                )

    result = st.session_state.manager_result
    if isinstance(result, dict):
        with st.container(border=True):
            st.markdown("**Manager decision response**")
            st.write("Approval ID:", result.get("approval_id", "Not returned"))
            st.write("Approval status:", result.get("approval_status", "Not returned"))
            st.write("Requisition status:", requisition_status(result))
            with st.expander("Backend response — local development only"):
                st.json(result)
            st.caption("Verify the final requisition and audit state in Turso.")


state_init()
st.title("🛒 ProcureAI")
st.caption("Conversational procurement • contracted suppliers • controlled execution • synthetic data")

with st.sidebar:
    st.subheader("ProcureAI")
    st.caption("ProcureAI V1 · Local PoC")
    view = st.radio("Demo view", ["Requester chat", "Manager demo"], key="view")
    st.write("**Current journey**", st.session_state.step.replace("_", " ").title())
    st.write("**Material**", (st.session_state.material or {}).get("material_id", "Not selected"))
    st.write("**Offer**", (st.session_state.offer or {}).get("offer_id", "Not selected"))
    st.write("**Quantity**", st.session_state.purchase_quantity)
    st.caption("AI suggests. The application and backend validate and execute.")
    st.divider()
    if st.button("New conversation", use_container_width=True):
        st.session_state.events = []
        reset_purchase()
        st.session_state.agent_session = None
        st.rerun()
    if st.button("Cancel current purchase", use_container_width=True):
        reset_purchase()
        message("assistant", "Current purchase cleared without submitting a requisition.")
        st.rerun()

if st.session_state.view == "Manager demo":
    display_manager_demo()
else:
    if not st.session_state.events:
        with st.chat_message("assistant"):
            st.markdown("Hi! Tell me what you need to purchase, for example: **I need 10 industrial safety helmets.**")

    for event in st.session_state.events:
        with st.chat_message(event["role"]):
            st.markdown(event["text"])

    # Only the latest workflow card is active. Old selections are plain chat history.
    if st.session_state.step != "chat":
        with st.chat_message("assistant"):
            if st.session_state.step == "material":
                display_material_choice()
            elif st.session_state.step == "offer":
                display_offer_choice()
            elif st.session_state.step == "quantity":
                display_quantity()
            elif st.session_state.step == "review":
                display_review()
            elif st.session_state.step == "submitted":
                display_submitted()

    # A deterministic fallback search box also handles requests with no known keyword.
    with st.expander("Search the catalog directly", expanded=False):
        with st.form("catalog_search"):
            direct_query = st.text_input("Material description", placeholder="helmet or gloves")
            direct_qty = st.number_input("Requested quantity", min_value=1, max_value=10000, value=1)
            direct_submit = st.form_submit_button("Find materials")
        if direct_submit:
            if len(direct_query.strip()) < 2:
                st.warning("Enter at least two characters.")
            else:
                try:
                    message("user", f"Search for {direct_query}; quantity {direct_qty}")
                    start_search(direct_query.strip(), int(direct_qty))
                    st.rerun()
                except Exception:
                    LOGGER.exception("Catalog lookup failed")
                    st.error("Catalog search failed. Check FastAPI and Streamlit logs.")

    prompt = st.chat_input("What would you like to purchase?")
    if prompt:
        message("user", prompt)
        term = search_term(prompt)
        if term:
            try:
                start_search(term, requested_quantity(prompt))
            except Exception:
                LOGGER.exception("Conversation catalog search failed")
                message("assistant", "I couldn't retrieve the catalog. Please check the FastAPI backend.")
        else:
            # Questions without a catalog keyword are answered conversationally.
            # The model has read-only tools only and cannot submit requisitions.
            try:
                reply = agent_reply(prompt)
                message("assistant", reply or "I couldn't form a response. Please try another question.")
            except Exception:
                LOGGER.exception("Agent invocation failed")
                message("assistant", "The AI assistant is temporarily unavailable. You can still search the catalog directly.")
        st.rerun()
