
import json
import logging
import os
import uuid

from typing import Literal

import libsql

from api.db_config import configure_database
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field


# ==================================================
# 1. Configuration
# ==================================================


logger = logging.getLogger("procureai.approvals")

configure_database()

router = APIRouter(
    prefix="/api/v1/approvals",
    tags=["Manager Approvals"]
)


class ApprovalDecisionRequest(BaseModel):
    comment: str = Field(
        default="",
        max_length=1000
    )
    confirmed: Literal[True]


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:16].upper()}"


def get_connection():
    url = os.getenv("TURSO_DATABASE_URL")
    token = os.getenv("TURSO_AUTH_TOKEN")

    if not url or not token:
        raise HTTPException(
            status_code=503,
            detail="Turso configuration unavailable"
        )

    return libsql.connect(
        database=url,
        auth_token=token
    )


# ==================================================
# 2. Shared approval decision logic
# ==================================================

def process_approval_decision(
    approval_id: str,
    decision: str,
    comment: str
):
    """
    Apply APPROVED or REJECTED to a pending approval.

    IMPORTANT:
    - Uses simulated trusted manager identity.
    - Requires explicit BEGIN IMMEDIATE transaction.
    - Rejection releases committed budget.
    - Approval retains the budget commitment.
    - Writes an audit record in the transaction.
    """

    if os.getenv("ENABLE_DEMO_WRITES") != "true":
        raise HTTPException(
            status_code=403,
            detail="Demo write operations are disabled"
        )

    # DEMO ONLY:
    # In a real application, this must come from
    # authenticated server-side identity.
    actor_id = os.getenv(
        "DEMO_APPROVER_ID",
        "EMP-1002"
    )

    connection = None
    transaction_started = False

    try:
        connection = get_connection()
        connection.execute("PRAGMA foreign_keys = ON")

        connection.execute("BEGIN IMMEDIATE")
        transaction_started = True

        # ------------------------------------------
        # 3. Verify assigned active manager
        # ------------------------------------------

        row = connection.execute("""
            SELECT
                ar.approval_id,
                ar.requisition_id,
                ar.approver_id,
                ar.approval_status,
                pr.requisition_status,
                pr.budget_id,
                pr.total_amount_cents,
                e.employee_status,
                e.employee_role,
                pr.requester_id,
                pr.approval_required
            FROM approval_requests ar
            JOIN purchase_requisitions pr
              ON pr.requisition_id = ar.requisition_id
            JOIN employees e
              ON e.employee_id = ar.approver_id
            WHERE ar.approval_id = ?
        """, (approval_id,)).fetchone()

        if row is None:
            raise HTTPException(
                status_code=404,
                detail="Approval request not found"
            )

        (
            stored_approval_id,
            requisition_id,
            assigned_approver_id,
            current_approval_status,
            current_pr_status,
            budget_id,
            amount_cents,
            manager_status,
            manager_role,
            requester_id,
            approval_required
        ) = row

        # Authorization is checked before
        # revealing the existing decision.
        if (
            actor_id != assigned_approver_id
            or actor_id == requester_id
            or manager_status != "ACTIVE"
            or manager_role != "MANAGER"
        ):
            raise HTTPException(
                status_code=403,
                detail="Manager not authorized for this approval"
            )

        # ------------------------------------------
        # 4. Handle repeated decisions safely
        # ------------------------------------------

        if current_approval_status == decision:
            if current_pr_status != decision:
                raise HTTPException(
                    status_code=409,
                    detail="Approval and requisition states disagree"
                )

            connection.commit()
            transaction_started = False

            return {
                "approval_id": stored_approval_id,
                "requisition_id": requisition_id,
                "approval_status": current_approval_status,
                "requisition_status": current_pr_status,
                "already_decided": True,
                "budget_released": False,
                "message": "Existing decision returned"
            }

        if (
            current_approval_status != "PENDING"
            or current_pr_status != "PENDING_APPROVAL"
            or approval_required != 1
        ):
            raise HTTPException(
                status_code=409,
                detail="Approval is no longer pending"
            )

        # ------------------------------------------
        # 5. Release budget if rejected
        # ------------------------------------------

        budget_released = False

        if decision == "REJECTED":

            connection.execute("""
                UPDATE budgets
                SET committed_amount_cents =
                    committed_amount_cents - ?
                WHERE budget_id = ?
                  AND committed_amount_cents >= ?
            """, (
                amount_cents,
                budget_id,
                amount_cents
            ))

            changes = connection.execute(
                "SELECT changes()"
            ).fetchone()[0]

            if changes != 1:
                raise HTTPException(
                    status_code=409,
                    detail="Budget commitment cannot be released"
                )

            budget_released = True

        # ------------------------------------------
        # 6. Update requisition state
        # ------------------------------------------

        connection.execute("""
            UPDATE purchase_requisitions
            SET requisition_status = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE requisition_id = ?
              AND requisition_status = 'PENDING_APPROVAL'
        """, (
            decision,
            requisition_id
        ))

        changes = connection.execute(
            "SELECT changes()"
        ).fetchone()[0]

        if changes != 1:
            raise HTTPException(
                status_code=409,
                detail="Requisition state transition failed"
            )

        # ------------------------------------------
        # 7. Update approval decision
        # ------------------------------------------

        connection.execute("""
            UPDATE approval_requests
            SET approval_status = ?,
                approval_comment = ?,
                decided_at = CURRENT_TIMESTAMP
            WHERE approval_id = ?
              AND approval_status = 'PENDING'
        """, (
            decision,
            comment,
            approval_id
        ))

        changes = connection.execute(
            "SELECT changes()"
        ).fetchone()[0]

        if changes != 1:
            raise HTTPException(
                status_code=409,
                detail="Approval state transition failed"
            )

        # ------------------------------------------
        # 8. Record the audit event
        # ------------------------------------------

        action = (
            "REQUISITION_APPROVED"
            if decision == "APPROVED"
            else "REQUISITION_REJECTED"
        )

        details = json.dumps({
            "approval_id": approval_id,
            "decision": decision,
            "comment": comment,
            "amount_cents": amount_cents,
            "budget_released": budget_released
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
            VALUES (
                ?, ?, ?, 'EMPLOYEE',
                ?, 'PENDING_APPROVAL', ?, ?
            )
        """, (
            new_id("AUD"),
            requisition_id,
            actor_id,
            action,
            decision,
            details
        ))

        # ------------------------------------------
        # 9. Commit everything together
        # ------------------------------------------

        connection.commit()
        transaction_started = False

        return {
            "approval_id": approval_id,
            "requisition_id": requisition_id,
            "approval_status": decision,
            "requisition_status": decision,
            "approver_id": actor_id,
            "already_decided": False,
            "budget_released": budget_released,
            "released_amount_cents": (
                amount_cents if budget_released else 0
            ),
            "message": (
                "Manager decision recorded successfully"
            )
        }

    except HTTPException:
        if transaction_started and connection:
            connection.rollback()
        raise

    except Exception:
        if transaction_started and connection:
            try:
                connection.rollback()
            except Exception:
                logger.exception("Rollback failed")

        logger.exception("Manager approval operation failed")

        raise HTTPException(
            status_code=503,
            detail="Approval service unavailable"
        )

    finally:
        if connection is not None:
            connection.close()


# ==================================================
# 10. Approve endpoint
# ==================================================

@router.post("/{approval_id}/approve")
def approve_requisition(
    approval_id: str,
    request: ApprovalDecisionRequest
):
    return process_approval_decision(
        approval_id=approval_id,
        decision="APPROVED",
        comment=request.comment
    )


# ==================================================
# 11. Reject endpoint
# ==================================================

@router.post("/{approval_id}/reject")
def reject_requisition(
    approval_id: str,
    request: ApprovalDecisionRequest
):
    return process_approval_decision(
        approval_id=approval_id,
        decision="REJECTED",
        comment=request.comment
    )
