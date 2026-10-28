
import os
import logging

import libsql
from api.db_config import configure_database

# Load and verify the selected environment BEFORE importing routers.
APP_ENV = configure_database()

from api.requisitions import router as requisitions_router
from api.approvals import router as approvals_router
from fastapi import FastAPI, Query, HTTPException


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("procureai.catalog")

app = FastAPI(
    title="ProcureAI Catalog API",
    description="Procurement catalog search with controlled synonym expansion",
    version="0.3.0",
)

app.include_router(requisitions_router)
app.include_router(approvals_router)

# Curated search terms: discovery only, not suitability approval
PRODUCT_SYNONYMS = {
    "safety helmet": ["helmet", "hard hat"],
    "protective gloves": ["gloves", "work gloves"],
}


@app.get("/health")
def health():
    return {"status": "ok", "environment": APP_ENV}


def escape_like(value: str) -> str:
    """Escape special SQL LIKE wildcard characters."""
    return (
        value.replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )


@app.get("/api/v1/materials")
def search_materials(
    search: str = Query(min_length=2, max_length=100)
):
    database_url = os.getenv("TURSO_DATABASE_URL")
    auth_token = os.getenv("TURSO_AUTH_TOKEN")

    if not database_url or not auth_token:
        raise HTTPException(
            status_code=500,
            detail="Database configuration unavailable",
        )

    # Normalize whitespace and capitalization
    normalized = " ".join(search.lower().split())

    if not normalized:
        raise HTTPException(
            status_code=422,
            detail="Search must contain at least one word",
        )

    # Original request plus approved alternative search phrases
    search_queries = [normalized]

    for phrase, alternatives in PRODUCT_SYNONYMS.items():
        if phrase in normalized:
            search_queries.extend(alternatives)

    # Avoid duplicate alternatives
    search_queries = list(dict.fromkeys(search_queries))

    # Each alternative is a group of AND terms.
    # Groups are joined with OR to improve candidate recall.
    groups = []
    parameters = []

    for query in search_queries:
        terms = query.split()
        term_conditions = []

        for term in terms:
            term_conditions.append(
                "(material_name LIKE ? ESCAPE '\\' "
                "OR description LIKE ? ESCAPE '\\')"
            )

            pattern = f"%{escape_like(term)}%"
            parameters.extend([pattern, pattern])

        groups.append("(" + " AND ".join(term_conditions) + ")")

    where_clause = " OR ".join(groups)

    sql = f"""
        SELECT
            material_id,
            material_name,
            category,
            description,
            uom
        FROM materials
        WHERE material_status = 'ACTIVE'
          AND ({where_clause})
        ORDER BY material_name
        LIMIT 50
    """

    connection = None

    try:
        connection = libsql.connect(
            database=database_url,
            auth_token=auth_token,
        )

        rows = connection.execute(
            sql,
            tuple(parameters),
        ).fetchall()

        materials = [
            {
                "material_id": row[0],
                "material_name": row[1],
                "category": row[2],
                "description": row[3],
                "uom": row[4],
            }
            for row in rows
        ]

        logger.info(
            "Catalog search: alternatives=%d results=%d",
            len(search_queries),
            len(materials),
        )

        return {
            "search": search,
            "count": len(materials),
            "materials": materials,
        }

    except Exception:
        logger.exception("Catalog search failed")
        raise HTTPException(
            status_code=503,
            detail="Catalog service temporarily unavailable",
        )

    finally:
        if connection is not None:
            connection.close()



# --------------------------------------------------
# Supplier Offers API
# --------------------------------------------------

@app.get("/api/v1/materials/{material_id}/supplier-offers")
def get_supplier_offers(material_id: str):
    """
    Return eligible contracted offers for an active material.

    Eligibility rules:
    - Material must be active
    - Supplier must be active
    - Contract must be active
    - Contract dates must include today
    """

    database_url = os.getenv("TURSO_DATABASE_URL")
    auth_token = os.getenv("TURSO_AUTH_TOKEN")

    if not database_url or not auth_token:
        raise HTTPException(
            status_code=500,
            detail="Database configuration unavailable"
        )

    connection = None

    try:
        connection = libsql.connect(
            database=database_url,
            auth_token=auth_token
        )

        material = connection.execute(
            """
            SELECT material_id, material_name, uom
            FROM materials
            WHERE material_id = ?
              AND material_status = 'ACTIVE'
            """,
            (material_id,)
        ).fetchone()

        if material is None:
            raise HTTPException(
                status_code=404,
                detail="Active material not found"
            )

        rows = connection.execute(
            """
            SELECT
                sc.offer_id,
                s.supplier_id,
                s.supplier_name,
                c.contract_id,
                sc.unit_price,
                sc.currency,
                sc.lead_time_days
            FROM supplier_catalog sc
            JOIN contracts c
                ON sc.contract_id = c.contract_id
            JOIN suppliers s
                ON c.supplier_id = s.supplier_id
            WHERE sc.material_id = ?
              AND s.supplier_status = 'ACTIVE'
              AND c.contract_status = 'ACTIVE'
              AND c.start_date <= date('now')
              AND c.end_date >= date('now')
            ORDER BY sc.unit_price ASC
            """,
            (material_id,)
        ).fetchall()

        offers = [
            {
                "offer_id": row[0],
                "supplier_id": row[1],
                "supplier_name": row[2],
                "contract_id": row[3],
                "unit_price": row[4],
                "currency": row[5],
                "lead_time_days": row[6]
            }
            for row in rows
        ]

        return {
            "material_id": material[0],
            "material_name": material[1],
            "uom": material[2],
            "eligible_offer_count": len(offers),
            "offers": offers
        }

    except HTTPException:
        raise

    except Exception:
        logger.exception("Supplier offer retrieval failed")
        raise HTTPException(
            status_code=503,
            detail="Supplier service temporarily unavailable"
        )

    finally:
        if connection is not None:
            connection.close()


# ==================================================
# Procurement Budget and Policy Validation API
# ==================================================

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from fastapi import HTTPException
from pydantic import BaseModel, Field


class ProcurementValidationRequest(BaseModel):
    offer_id: str = Field(min_length=1, max_length=50)
    quantity: int = Field(gt=0, le=10000)


@app.post("/api/v1/procurement/validate")
def validate_procurement(
    request: ProcurementValidationRequest
):
    """
    Read-only procurement validation.

    The backend verifies the offer, calculates cost,
    checks employee authorization and budget,
    and evaluates the approval policy.

    No purchase requisition is created.
    No budget is reserved or committed.
    """

    # DEMO ONLY:
    # The server controls the simulated employee identity.
    # The AI model and API request cannot select it.
    requester_id = os.getenv(
        "DEMO_REQUESTER_ID",
        "EMP-1001"
    )

    database_url = os.getenv("TURSO_DATABASE_URL")
    auth_token = os.getenv("TURSO_AUTH_TOKEN")

    if not database_url or not auth_token:
        raise HTTPException(
            status_code=503,
            detail="Database configuration unavailable"
        )

    connection = None

    try:
        connection = libsql.connect(
            database=database_url,
            auth_token=auth_token
        )

        connection.execute("PRAGMA foreign_keys = ON")

        today = datetime.now(
            timezone.utc
        ).date()

        today_text = today.isoformat()
        fiscal_year = today.year

        # ------------------------------------------
        # 1. Verify requester and assigned cost center
        # ------------------------------------------

        employee = connection.execute("""
            SELECT
                e.employee_id,
                e.employee_name,
                e.employee_role,
                e.manager_id,
                e.employee_status,
                cc.cost_center_id,
                cc.cost_center_name,
                cc.currency,
                cc.cost_center_status
            FROM employees e
            JOIN cost_centers cc
                ON e.cost_center_id = cc.cost_center_id
            WHERE e.employee_id = ?
        """, (requester_id,)).fetchone()

        if employee is None:
            raise HTTPException(
                status_code=403,
                detail="Requester or assigned cost center not found"
            )

        (
            employee_id,
            employee_name,
            employee_role,
            manager_id,
            employee_status,
            cost_center_id,
            cost_center_name,
            cost_center_currency,
            cost_center_status
        ) = employee

        if employee_status != "ACTIVE":
            raise HTTPException(
                status_code=403,
                detail="Requester is inactive"
            )

        if employee_role not in (
            "REQUESTER",
            "MANAGER",
            "PROCUREMENT_ADMIN"
        ):
            raise HTTPException(
                status_code=403,
                detail="Requester role is not authorized"
            )

        if cost_center_status != "ACTIVE":
            raise HTTPException(
                status_code=403,
                detail="Assigned cost center is inactive"
            )

        # ------------------------------------------
        # 2. Verify supplier offer and contract
        # ------------------------------------------

        offer = connection.execute("""
            SELECT
                sc.offer_id,
                m.material_id,
                m.material_name,
                m.uom,
                s.supplier_id,
                s.supplier_name,
                c.contract_id,
                sc.unit_price,
                sc.currency,
                sc.lead_time_days
            FROM supplier_catalog sc
            JOIN materials m
                ON sc.material_id = m.material_id
            JOIN contracts c
                ON sc.contract_id = c.contract_id
            JOIN suppliers s
                ON c.supplier_id = s.supplier_id
            WHERE sc.offer_id = ?
              AND m.material_status = 'ACTIVE'
              AND s.supplier_status = 'ACTIVE'
              AND c.contract_status = 'ACTIVE'
              AND c.start_date <= ?
              AND c.end_date >= ?
        """, (
            request.offer_id.strip().upper(),
            today_text,
            today_text
        )).fetchone()

        if offer is None:
            raise HTTPException(
                status_code=422,
                detail=(
                    "Supplier offer not found or "
                    "not currently eligible"
                )
            )

        (
            offer_id,
            material_id,
            material_name,
            uom,
            supplier_id,
            supplier_name,
            contract_id,
            unit_price,
            currency,
            lead_time_days
        ) = offer

        if currency != cost_center_currency:
            raise HTTPException(
                status_code=422,
                detail="Offer and cost center currencies differ"
            )

        # ------------------------------------------
        # 3. Calculate requested amount
        # ------------------------------------------
        # Existing supplier prices use REAL.
        # Decimal avoids additional binary floating-
        # point errors during multiplication.
        # USD values must be whole cents.

        try:
            price = Decimal(str(unit_price))

            if (
                not price.is_finite()
                or price < 0
                or price.as_tuple().exponent < -2
            ):
                raise ValueError("Invalid currency precision")

            unit_price_cents_decimal = (
                price * Decimal("100")
            ).quantize(
                Decimal("1"),
                rounding=ROUND_HALF_UP
            )

            unit_price_cents = int(
                unit_price_cents_decimal
            )

        except (
            InvalidOperation,
            ValueError,
            TypeError,
            OverflowError
        ):
            raise HTTPException(
                status_code=422,
                detail="Supplier price cannot be validated"
            )

        requested_amount_cents = (
            unit_price_cents * request.quantity
        )

        # ------------------------------------------
        # 4. Check current fiscal year budget
        # ------------------------------------------

        budget = connection.execute("""
            SELECT
                budget_id,
                allocated_amount_cents,
                committed_amount_cents,
                spent_amount_cents
            FROM budgets
            WHERE cost_center_id = ?
              AND fiscal_year = ?
              AND currency = ?
        """, (
            cost_center_id,
            fiscal_year,
            currency
        )).fetchone()

        if budget is None:
            raise HTTPException(
                status_code=422,
                detail="No matching current-year budget"
            )

        (
            budget_id,
            allocated_cents,
            committed_cents,
            spent_cents
        ) = budget

        available_budget_cents = (
            allocated_cents
            - committed_cents
            - spent_cents
        )

        budget_passed = (
            requested_amount_cents
            <= available_budget_cents
        )

        # ------------------------------------------
        # 5. Find applicable purchasing policy
        # ------------------------------------------

        policies = connection.execute("""
            SELECT
                policy_id,
                policy_name,
                manager_approval_threshold_cents
            FROM procurement_policies
            WHERE currency = ?
              AND policy_status = 'ACTIVE'
              AND effective_from <= ?
              AND effective_to >= ?
        """, (
            currency,
            today_text,
            today_text
        )).fetchall()

        # Fail closed rather than arbitrarily choose
        # a policy when none or multiple are applicable.
        if len(policies) != 1:
            raise HTTPException(
                status_code=422,
                detail=(
                    "Exactly one applicable purchasing "
                    "policy is required"
                )
            )

        (
            policy_id,
            policy_name,
            approval_threshold_cents
        ) = policies[0]

        approval_required = (
            requested_amount_cents
            > approval_threshold_cents
        )

        # ------------------------------------------
        # 6. Verify available approval path
        # ------------------------------------------

        approval_route_available = True

        if approval_required and employee_role == "REQUESTER":
            if not manager_id:
                approval_route_available = False
            else:
                manager = connection.execute("""
                    SELECT employee_id
                    FROM employees
                    WHERE employee_id = ?
                      AND employee_role = 'MANAGER'
                      AND employee_status = 'ACTIVE'
                """, (manager_id,)).fetchone()

                approval_route_available = (
                    manager is not None
                )

        # ------------------------------------------
        # 7. Return deterministic decision
        # ------------------------------------------

        if not budget_passed:
            decision = "BUDGET_INSUFFICIENT"

        elif not approval_route_available:
            decision = "APPROVAL_ROUTE_UNAVAILABLE"

        elif approval_required:
            decision = "APPROVAL_REQUIRED"

        else:
            decision = "VALIDATION_PASSED"

        return {
            "validation_status": decision,
            "validation_passed": (
                budget_passed
                and approval_route_available
            ),
            "requester": {
                "employee_id": employee_id,
                "employee_name": employee_name,
                "role": employee_role,
                "cost_center_id": cost_center_id,
                "cost_center_name": cost_center_name
            },
            "purchase": {
                "offer_id": offer_id,
                "material_id": material_id,
                "material_name": material_name,
                "supplier_id": supplier_id,
                "supplier_name": supplier_name,
                "contract_id": contract_id,
                "quantity": request.quantity,
                "uom": uom,
                "unit_price_cents": unit_price_cents,
                "requested_amount_cents": (
                    requested_amount_cents
                ),
                "currency": currency,
                "lead_time_days": lead_time_days
            },
            "budget": {
                "budget_id": budget_id,
                "fiscal_year": fiscal_year,
                "available_budget_cents": (
                    available_budget_cents
                ),
                "budget_check": (
                    "PASSED"
                    if budget_passed
                    else "FAILED"
                )
            },
            "policy": {
                "policy_id": policy_id,
                "policy_name": policy_name,
                "manager_approval_threshold_cents": (
                    approval_threshold_cents
                ),
                "manager_approval_required": (
                    approval_required
                ),
                "manager_id": (
                    manager_id
                    if approval_required
                    else None
                ),
                "approval_route_available": (
                    approval_route_available
                )
            },
            "budget_reserved": False,
            "purchase_requisition_created": False
        }

    except HTTPException:
        raise

    except Exception:
        logger.exception(
            "Procurement validation service failed"
        )

        raise HTTPException(
            status_code=503,
            detail="Procurement validation service unavailable"
        )

    finally:
        if connection is not None:
            connection.close()
