"""Seed ProcureAI identity, budgets, and policy into the TEST database only.

Run from ProcureAI root:
    python database/seed_budget_policy.py --test --seed

Requires database/db_target.py and .env.test. This script never reads .env.
It refuses to overwrite existing business data or touch a non-test Turso DB.
"""

from __future__ import annotations

import argparse
from datetime import date, timedelta

import libsql

try:
    from database.db_target import test_credentials
except ModuleNotFoundError:
    from db_target import test_credentials


SEED_TABLES = (
    "cost_centers",
    "employees",
    "budgets",
    "procurement_policies",
)
TRANSACTION_TABLES = (
    "purchase_requisitions",
    "approval_requests",
    "audit_logs",
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed ProcureAI TEST business data")
    parser.add_argument("--test", action="store_true", help="Required test target opt-in")
    parser.add_argument("--seed", action="store_true", help="Required seed opt-in")
    args = parser.parse_args()
    if not (args.test and args.seed):
        parser.error("Refusing to run. Use: python database/seed_budget_policy.py --test --seed")

    # Fail closed before opening a database connection.
    database_url, auth_token = test_credentials()
    print("Verified target: procureai-test")

    fiscal_year = date.today().year
    today = date.today()

    cost_centers = [
        ("CC-MAINT-SEA", "Seattle Maintenance", "Maintenance", "USD", "ACTIVE"),
        ("CC-IT-SEA", "Seattle IT", "Information Technology", "USD", "ACTIVE"),
    ]
    employees = [
        ("EMP-1002", "Maria Chen", "maria.chen@example.com", "MANAGER", "CC-MAINT-SEA", None, "ACTIVE"),
        ("EMP-1001", "Alex Johnson", "alex.johnson@example.com", "REQUESTER", "CC-MAINT-SEA", "EMP-1002", "ACTIVE"),
        ("EMP-1003", "David Lee", "david.lee@example.com", "REQUESTER", "CC-IT-SEA", None, "ACTIVE"),
        ("EMP-1004", "Jordan Smith", "jordan.smith@example.com", "REQUESTER", "CC-MAINT-SEA", "EMP-1002", "INACTIVE"),
    ]
    budgets = [
        (f"BUD-MAINT-{fiscal_year}", "CC-MAINT-SEA", fiscal_year, "USD", 1_000_000, 200_000, 300_000),
        (f"BUD-IT-{fiscal_year}", "CC-IT-SEA", fiscal_year, "USD", 2_000_000, 500_000, 800_000),
    ]
    policies = [
        ("POL-1001", "Standard Purchasing Approval Policy", "USD", 50_000,
         (today - timedelta(days=30)).isoformat(),
         (today + timedelta(days=365)).isoformat(), "ACTIVE")
    ]

    conn = libsql.connect(database=database_url, auth_token=auth_token)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        required = set(SEED_TABLES + TRANSACTION_TABLES)
        existing = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()}
        missing = sorted(required - existing)
        if missing:
            raise RuntimeError(f"Missing required tables: {missing}. Run create_tables.py --test first.")

        # Do not overwrite existing seeds, changed budgets, or any prior test transactions.
        for table in SEED_TABLES + TRANSACTION_TABLES:
            count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            if count:
                raise RuntimeError(
                    f"Refusing to seed: {table} already contains {count} record(s). "
                    "This operation must run against a fresh, empty business dataset."
                )

        conn.execute("BEGIN IMMEDIATE")
        try:
            for row in cost_centers:
                conn.execute("""
                    INSERT INTO cost_centers (
                        cost_center_id, cost_center_name, department,
                        currency, cost_center_status
                    ) VALUES (?, ?, ?, ?, ?)
                """, row)
            for row in employees:
                conn.execute("""
                    INSERT INTO employees (
                        employee_id, employee_name, email, employee_role,
                        cost_center_id, manager_id, employee_status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """, row)
            for row in budgets:
                conn.execute("""
                    INSERT INTO budgets (
                        budget_id, cost_center_id, fiscal_year, currency,
                        allocated_amount_cents, committed_amount_cents, spent_amount_cents
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """, row)
            for row in policies:
                conn.execute("""
                    INSERT INTO procurement_policies (
                        policy_id, policy_name, currency,
                        manager_approval_threshold_cents,
                        effective_from, effective_to, policy_status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """, row)
            conn.commit()
        except Exception:
            conn.rollback()
            raise

        print("Synthetic test business data seeded successfully.")
        for table in SEED_TABLES:
            count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            print(f"{table}: {count}")
        print(f"Manager approval threshold: $500.00; fiscal year: {fiscal_year}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
