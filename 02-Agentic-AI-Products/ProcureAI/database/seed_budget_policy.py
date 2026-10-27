
import os
from datetime import date, timedelta
from pathlib import Path

import libsql
from dotenv import load_dotenv


# --------------------------------------------------
# 1. Load Turso configuration
# --------------------------------------------------

project_root = Path(__file__).resolve().parent.parent
load_dotenv(project_root / ".env", override=True)

database_url = os.getenv("TURSO_DATABASE_URL")
auth_token = os.getenv("TURSO_AUTH_TOKEN")

if not database_url or not auth_token:
    raise ValueError("Missing Turso database configuration")


# --------------------------------------------------
# 2. Synthetic cost centers
# --------------------------------------------------

cost_centers = [
    (
        "CC-MAINT-SEA",
        "Seattle Maintenance",
        "Maintenance",
        "USD",
        "ACTIVE"
    ),
    (
        "CC-IT-SEA",
        "Seattle IT",
        "Information Technology",
        "USD",
        "ACTIVE"
    )
]


# --------------------------------------------------
# 3. Synthetic employees
# --------------------------------------------------

employees = [
    # Manager first
    (
        "EMP-1002", "Maria Chen",
        "maria.chen@example.com",
        "MANAGER", "CC-MAINT-SEA", None, "ACTIVE"
    ),
    (
        "EMP-1001", "Alex Johnson",
        "alex.johnson@example.com",
        "REQUESTER", "CC-MAINT-SEA", "EMP-1002", "ACTIVE"
    ),
    (
        "EMP-1003", "David Lee",
        "david.lee@example.com",
        "REQUESTER", "CC-IT-SEA", None, "ACTIVE"
    ),
    (
        "EMP-1004", "Jordan Smith",
        "jordan.smith@example.com",
        "REQUESTER", "CC-MAINT-SEA", "EMP-1002", "INACTIVE"
    )
]


# --------------------------------------------------
# 4. Synthetic budgets (integer cents)
# --------------------------------------------------

fiscal_year = date.today().year

budgets = [
    (
        f"BUD-MAINT-{fiscal_year}",
        "CC-MAINT-SEA",
        fiscal_year,
        "USD",
        1_000_000,  # $10,000 allocated
        200_000,    # $2,000 committed
        300_000     # $3,000 spent
    ),
    (
        f"BUD-IT-{fiscal_year}",
        "CC-IT-SEA",
        fiscal_year,
        "USD",
        2_000_000,  # $20,000 allocated
        500_000,    # $5,000 committed
        800_000     # $8,000 spent
    )
]


# --------------------------------------------------
# 5. Procurement policy
# --------------------------------------------------

today = date.today()

policies = [
    (
        "POL-1001",
        "Standard Purchasing Approval Policy",
        "USD",
        50_000,  # $500; amounts above need approval
        (today - timedelta(days=30)).isoformat(),
        (today + timedelta(days=365)).isoformat(),
        "ACTIVE"
    )
]


# --------------------------------------------------
# 6. Connect and seed
# --------------------------------------------------

connection = libsql.connect(
    database=database_url,
    auth_token=auth_token
)

try:
    connection.execute("PRAGMA foreign_keys = ON")

    # Insert parent records first
    for row in cost_centers:
        connection.execute("""
            INSERT INTO cost_centers (
                cost_center_id, cost_center_name,
                department, currency, cost_center_status
            )
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(cost_center_id) DO NOTHING
        """, row)

    for row in employees:
        connection.execute("""
            INSERT INTO employees (
                employee_id, employee_name, email,
                employee_role, cost_center_id,
                manager_id, employee_status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(employee_id) DO NOTHING
        """, row)

    for row in budgets:
        connection.execute("""
            INSERT INTO budgets (
                budget_id, cost_center_id, fiscal_year,
                currency, allocated_amount_cents,
                committed_amount_cents, spent_amount_cents
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(budget_id) DO NOTHING
        """, row)

    for row in policies:
        connection.execute("""
            INSERT INTO procurement_policies (
                policy_id, policy_name, currency,
                manager_approval_threshold_cents,
                effective_from, effective_to, policy_status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(policy_id) DO NOTHING
        """, row)

    connection.commit()

    print("\nProcureAI budget and policy data loaded.")

    allowed_tables = [
        "cost_centers",
        "employees",
        "budgets",
        "procurement_policies"
    ]

    for table in allowed_tables:
        count = connection.execute(
            f"SELECT COUNT(*) FROM {table}"
        ).fetchone()[0]
        print(f"{table}: {count} records")

finally:
    connection.close()
