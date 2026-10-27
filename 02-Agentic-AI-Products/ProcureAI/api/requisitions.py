
import hashlib
import json
import os
import uuid

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

import libsql

from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field


# --------------------------------------------------
# 1. Configuration
# --------------------------------------------------

project_root = Path(__file__).resolve().parent.parent
load_dotenv(project_root / ".env", override=True)

router = APIRouter(prefix="/api/v1", tags=["Requisitions"])


class RequisitionRequest(BaseModel):
    offer_id: str = Field(
        min_length=1,
        max_length=50,
        pattern=r"^OFF-[0-9]+$"
    )
    quantity: int = Field(gt=0, le=10000, strict=True)
    idempotency_key: str = Field(
        min_length=8,
        max_length=128
    )
    confirmed: bool


def new_id(prefix):
    return f"{prefix}-{uuid.uuid4().hex[:16].upper()}"


def fingerprint(requester_id, offer_id, quantity):
    payload = json.dumps(
        {
            "requester_id": requester_id,
            "offer_id": offer_id,
            "quantity": quantity
        },
        sort_keys=True
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def get_connection():
    database_url = os.getenv("TURSO_DATABASE_URL")
    auth_token = os.getenv("TURSO_AUTH_TOKEN")

    if not database_url or not auth_token:
        raise HTTPException(
            status_code=503,
            detail="Database configuration missing"
        )

    return libsql.connect(
        database=database_url,
        auth_token=auth_token
    )


# --------------------------------------------------
# 2. Create a requisition
# --------------------------------------------------

@router.post("/requisitions", status_code=201)
def create_requisition(request: RequisitionRequest):

    # This feature must be explicitly enabled.
    if os.getenv("ENABLE_DEMO_WRITES") != "true":
        raise HTTPException(
            status_code=403,
            detail="Demo requisition writes are disabled"
        )

    # Demo identity only. Replace with authenticated
    # server-side identity before public deployment.
    requester_id = os.getenv(
        "DEMO_REQUESTER_ID", "EMP-1001"
    )

    if not request.confirmed:
        raise HTTPException(
            status_code=400,
            detail="Explicit submission confirmation required"
        )

    connection = None
    transaction_started = False

    try:
        connection = get_connection()
        connection.execute("PRAGMA foreign_keys = ON")

        # Keep all database reads and writes for this
        # operation in one transaction.
        connection.execute("BEGIN IMMEDIATE")
        transaction_started = True

        today = datetime.now(timezone.utc).date()
        today_text = today.isoformat()
        fiscal_year = today.year

        request_hash = fingerprint(
            requester_id,
            request.offer_id,
            request.quantity
        )

        # ------------------------------------------
        # 3. Idempotency verification
        # ------------------------------------------

        existing = connection.execute("""
            SELECT
                requisition_id,
                request_fingerprint,
                requisition_status,
                total_amount_cents
            FROM purchase_requisitions
            WHERE idempotency_key = ?
        """, (request.idempotency_key,)).fetchone()

        if existing:
            if existing[1] != request_hash:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "Idempotency key already used "
                        "for a different request"
                    )
                )

            connection.commit()
            transaction_started = False

            return {
                "requisition_id": existing[0],
                "status": existing[2],
                "total_amount_cents": existing[3],
                "duplicate_request": True,
                "message": "Existing requisition returned"
            }

        # ------------------------------------------
        # 4. Verify employee and cost center
        # ------------------------------------------

        employee = connection.execute("""
            SELECT
                e.employee_id,
                e.employee_role,
                e.manager_id,
                e.cost_center_id,
                cc.currency
            FROM employees e
            JOIN cost_centers cc
                ON cc.cost_center_id = e.cost_center_id
            WHERE e.employee_id = ?
              AND e.employee_status = 'ACTIVE'
              AND cc.cost_center_status = 'ACTIVE'
              AND e.employee_role IN (
                  'REQUESTER',
                  'MANAGER',
                  'PROCUREMENT_ADMIN'
              )
        """, (requester_id,)).fetchone()

        if not employee:
            raise HTTPException(
                status_code=403,
                detail="Requester is not authorized"
            )

        (
            employee_id,
            employee_role,
            manager_id,
            cost_center_id,
            cost_center_currency
        ) = employee

        # ------------------------------------------
        # 5. Verify offer, material, and contract
        # ------------------------------------------

        offer = connection.execute("""
            SELECT
                sc.offer_id,
                sc.unit_price,
                sc.currency,
                m.material_id
            FROM supplier_catalog sc
            JOIN materials m
                ON m.material_id = sc.material_id
            JOIN contracts c
                ON c.contract_id = sc.contract_id
            JOIN suppliers s
                ON s.supplier_id = c.supplier_id
            WHERE sc.offer_id = ?
              AND m.material_status = 'ACTIVE'
              AND s.supplier_status = 'ACTIVE'
              AND c.contract_status = 'ACTIVE'
              AND c.start_date <= ?
              AND c.end_date >= ?
        """, (
            request.offer_id,
            today_text,
            today_text
        )).fetchone()

        if not offer:
            raise HTTPException(
                status_code=422,
                detail="Offer is not currently eligible"
            )

        offer_id, raw_price, currency, material_id = offer

        if currency != cost_center_currency:
            raise HTTPException(
                status_code=422,
                detail="Currency mismatch"
            )

        if currency != "USD":
            raise HTTPException(
                status_code=422,
                detail="Demo currently supports USD only"
            )

        # ------------------------------------------
        # 6. Calculate authoritative amount
        # ------------------------------------------

        try:
            price = Decimal(str(raw_price))

            if (
                not price.is_finite()
                or price < 0
                or price.as_tuple().exponent < -2
            ):
                raise ValueError("Invalid unit price")

            unit_cents = int(price * 100)

        except (
            InvalidOperation,
            ValueError,
            TypeError,
            OverflowError
        ):
            raise HTTPException(
                status_code=422,
                detail="Contract price has invalid precision"
            )

        total_cents = unit_cents * request.quantity

        # ------------------------------------------
        # 7. Verify effective procurement policy
        # ------------------------------------------

        policies = connection.execute("""
            SELECT
                policy_id,
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

        if len(policies) != 1:
            raise HTTPException(
                status_code=422,
                detail="Exactly one active policy required"
            )

        policy_id, threshold_cents = policies[0]

        approval_required = total_cents > threshold_cents

        # ------------------------------------------
        # 8. Verify manager approval route
        # ------------------------------------------

        if approval_required:
            if not manager_id or manager_id == employee_id:
                raise HTTPException(
                    status_code=422,
                    detail="Valid manager approval route missing"
                )

            manager = connection.execute("""
                SELECT employee_id
                FROM employees
                WHERE employee_id = ?
                  AND employee_role = 'MANAGER'
                  AND employee_status = 'ACTIVE'
                  AND cost_center_id = ?
            """, (
                manager_id,
                cost_center_id
            )).fetchone()

            if not manager:
                raise HTTPException(
                    status_code=422,
                    detail="Active authorized manager not found"
                )

        # ------------------------------------------
        # 9. Atomically reserve the budget
        # ------------------------------------------

        budget = connection.execute("""
            SELECT budget_id
            FROM budgets
            WHERE cost_center_id = ?
              AND fiscal_year = ?
              AND currency = ?
        """, (
            cost_center_id,
            fiscal_year,
            currency
        )).fetchone()

        if not budget:
            raise HTTPException(
                status_code=422,
                detail="Current-year budget not found"
            )

        budget_id = budget[0]

        connection.execute("""
            UPDATE budgets
            SET committed_amount_cents =
                committed_amount_cents + ?
            WHERE budget_id = ?
              AND allocated_amount_cents
                  - committed_amount_cents
                  - spent_amount_cents >= ?
        """, (
            total_cents,
            budget_id,
            total_cents
        ))

        updated = connection.execute(
            "SELECT changes()"
        ).fetchone()[0]

        if updated != 1:
            raise HTTPException(
                status_code=409,
                detail="Insufficient available budget"
            )

        # ------------------------------------------
        # 10. Create requisition
        # ------------------------------------------

        requisition_id = new_id("PR")

        status = (
            "PENDING_APPROVAL"
            if approval_required
            else "APPROVED"
        )

        connection.execute("""
            INSERT INTO purchase_requisitions (
                requisition_id,
                idempotency_key,
                requester_id,
                cost_center_id,
                budget_id,
                offer_id,
                quantity,
                unit_price_cents,
                total_amount_cents,
                currency,
                requisition_status,
                approval_required,
                policy_id,
                request_fingerprint
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            requisition_id,
            request.idempotency_key,
            requester_id,
            cost_center_id,
            budget_id,
            offer_id,
            request.quantity,
            unit_cents,
            total_cents,
            currency,
            status,
            int(approval_required),
            policy_id,
            request_hash
        ))

        # ------------------------------------------
        # 11. Create approval request if needed
        # ------------------------------------------

        if approval_required:
            connection.execute("""
                INSERT INTO approval_requests (
                    approval_id,
                    requisition_id,
                    approver_id,
                    approval_status
                )
                VALUES (?, ?, ?, 'PENDING')
            """, (
                new_id("APR"),
                requisition_id,
                manager_id
            ))

        # ------------------------------------------
        # 12. Record audit event
        # ------------------------------------------

        audit_details = json.dumps({
            "offer_id": offer_id,
            "material_id": material_id,
            "quantity": request.quantity,
            "currency": currency,
            "total_amount_cents": total_cents,
            "policy_id": policy_id,
            "approval_required": approval_required,
            "budget_committed": True
        })

        connection.execute("""
            INSERT INTO audit_logs (
                audit_id,
                requisition_id,
                actor_id,
                actor_type,
                action,
                previous_status,
                new_status,
                details_json
            )
            VALUES (?, ?, ?, 'EMPLOYEE', ?, NULL, ?, ?)
        """, (
            new_id("AUD"),
            requisition_id,
            requester_id,
            "REQUISITION_CREATED",
            status,
            audit_details
        ))

        # ------------------------------------------
        # 13. Commit all changes together
        # ------------------------------------------

        connection.commit()
        transaction_started = False

        return {
            "requisition_id": requisition_id,
            "status": status,
            "requester_id": requester_id,
            "offer_id": offer_id,
            "material_id": material_id,
            "quantity": request.quantity,
            "unit_price_cents": unit_cents,
            "total_amount_cents": total_cents,
            "currency": currency,
            "manager_approval_required": approval_required,
            "approver_id": (
                manager_id if approval_required else None
            ),
            "budget_committed": True,
            "duplicate_request": False,
            "message": (
                "Requisition created in demo database"
            )
        }

    except HTTPException:
        if transaction_started and connection:
            connection.rollback()
        raise

    except Exception as error:
        if transaction_started and connection:
            connection.rollback()

        # Do not expose database errors or credentials.
        print(
            "[REQUISITION ERROR]",
            type(error).__name__,
            str(error)
        )

        raise HTTPException(
            status_code=503,
            detail=(
                "Requisition service failed. "
                "Check database transaction support."
            )
        )

    finally:
        if connection:
            connection.close()
