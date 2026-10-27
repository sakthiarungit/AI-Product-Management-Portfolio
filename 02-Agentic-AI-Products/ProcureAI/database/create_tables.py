
import os
import libsql

from pathlib import Path
from dotenv import load_dotenv


# ==================================================
# 1. Load Turso Database Configuration
# ==================================================

project_root = Path(__file__).resolve().parent.parent

load_dotenv(
    project_root / ".env",
    override=True
)

database_url = os.getenv("TURSO_DATABASE_URL")
auth_token = os.getenv("TURSO_AUTH_TOKEN")

if not database_url or not auth_token:
    raise ValueError(
        "Missing TURSO_DATABASE_URL or TURSO_AUTH_TOKEN"
    )


# ==================================================
# 2. Connect to Turso Cloud
# ==================================================

connection = libsql.connect(
    database=database_url,
    auth_token=auth_token
)

try:
    connection.execute("PRAGMA foreign_keys = ON")

    # ==================================================
    # EXISTING PROCUREMENT MASTER DATA
    # ==================================================

    # --------------------------------------------------
    # 3. Materials
    # --------------------------------------------------

    connection.execute("""
        CREATE TABLE IF NOT EXISTS materials (
            material_id TEXT PRIMARY KEY,
            material_name TEXT NOT NULL,
            category TEXT NOT NULL,
            description TEXT,
            uom TEXT NOT NULL,

            material_status TEXT NOT NULL
                DEFAULT 'ACTIVE'
                CHECK (
                    material_status IN (
                        'ACTIVE', 'INACTIVE'
                    )
                ),

            created_at TEXT NOT NULL
                DEFAULT CURRENT_TIMESTAMP
        )
    """)

    print("Materials table ready.")

    # --------------------------------------------------
    # 4. Suppliers
    # --------------------------------------------------

    connection.execute("""
        CREATE TABLE IF NOT EXISTS suppliers (
            supplier_id TEXT PRIMARY KEY,
            supplier_name TEXT NOT NULL,

            supplier_status TEXT NOT NULL
                DEFAULT 'ACTIVE'
                CHECK (
                    supplier_status IN (
                        'ACTIVE', 'INACTIVE'
                    )
                )
        )
    """)

    print("Suppliers table ready.")

    # --------------------------------------------------
    # 5. Contracts
    # --------------------------------------------------

    connection.execute("""
        CREATE TABLE IF NOT EXISTS contracts (
            contract_id TEXT PRIMARY KEY,

            supplier_id TEXT NOT NULL,

            contract_status TEXT NOT NULL
                CHECK (
                    contract_status IN (
                        'ACTIVE',
                        'EXPIRED',
                        'SUSPENDED'
                    )
                ),

            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL,

            CHECK (end_date >= start_date),

            FOREIGN KEY (supplier_id)
                REFERENCES suppliers(supplier_id)
        )
    """)

    print("Contracts table ready.")

    # --------------------------------------------------
    # 6. Supplier Catalog
    # --------------------------------------------------

    connection.execute("""
        CREATE TABLE IF NOT EXISTS supplier_catalog (
            offer_id TEXT PRIMARY KEY,

            contract_id TEXT NOT NULL,
            material_id TEXT NOT NULL,

            unit_price REAL NOT NULL
                CHECK (unit_price >= 0),

            currency TEXT NOT NULL,

            lead_time_days INTEGER NOT NULL
                CHECK (lead_time_days >= 0),

            FOREIGN KEY (contract_id)
                REFERENCES contracts(contract_id),

            FOREIGN KEY (material_id)
                REFERENCES materials(material_id)
        )
    """)

    print("Supplier catalog table ready.")

    # ==================================================
    # EXISTING IDENTITY, BUDGET AND POLICY DATA
    # ==================================================

    # --------------------------------------------------
    # 7. Cost Centers
    # --------------------------------------------------

    connection.execute("""
        CREATE TABLE IF NOT EXISTS cost_centers (
            cost_center_id TEXT PRIMARY KEY,

            cost_center_name TEXT NOT NULL,
            department TEXT NOT NULL,

            currency TEXT NOT NULL DEFAULT 'USD',

            cost_center_status TEXT NOT NULL
                DEFAULT 'ACTIVE'
                CHECK (
                    cost_center_status IN (
                        'ACTIVE', 'INACTIVE'
                    )
                )
        )
    """)

    print("Cost centers table ready.")

    # --------------------------------------------------
    # 8. Employees
    # --------------------------------------------------

    connection.execute("""
        CREATE TABLE IF NOT EXISTS employees (
            employee_id TEXT PRIMARY KEY,

            employee_name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,

            employee_role TEXT NOT NULL
                CHECK (
                    employee_role IN (
                        'REQUESTER',
                        'MANAGER',
                        'PROCUREMENT_ADMIN'
                    )
                ),

            cost_center_id TEXT NOT NULL,
            manager_id TEXT,

            employee_status TEXT NOT NULL
                DEFAULT 'ACTIVE'
                CHECK (
                    employee_status IN (
                        'ACTIVE', 'INACTIVE'
                    )
                ),

            FOREIGN KEY (cost_center_id)
                REFERENCES cost_centers(cost_center_id),

            FOREIGN KEY (manager_id)
                REFERENCES employees(employee_id)
        )
    """)

    print("Employees table ready.")

    # --------------------------------------------------
    # 9. Budgets
    # --------------------------------------------------

    connection.execute("""
        CREATE TABLE IF NOT EXISTS budgets (
            budget_id TEXT PRIMARY KEY,

            cost_center_id TEXT NOT NULL,
            fiscal_year INTEGER NOT NULL,

            currency TEXT NOT NULL DEFAULT 'USD',

            allocated_amount_cents INTEGER NOT NULL
                CHECK (allocated_amount_cents >= 0),

            committed_amount_cents INTEGER NOT NULL
                DEFAULT 0
                CHECK (committed_amount_cents >= 0),

            spent_amount_cents INTEGER NOT NULL
                DEFAULT 0
                CHECK (spent_amount_cents >= 0),

            FOREIGN KEY (cost_center_id)
                REFERENCES cost_centers(cost_center_id),

            UNIQUE (
                cost_center_id,
                fiscal_year,
                currency
            ),

            CHECK (
                committed_amount_cents
                + spent_amount_cents
                <= allocated_amount_cents
            )
        )
    """)

    print("Budgets table ready.")

    # --------------------------------------------------
    # 10. Procurement Policies
    # --------------------------------------------------

    connection.execute("""
        CREATE TABLE IF NOT EXISTS procurement_policies (
            policy_id TEXT PRIMARY KEY,

            policy_name TEXT NOT NULL,
            currency TEXT NOT NULL DEFAULT 'USD',

            manager_approval_threshold_cents
                INTEGER NOT NULL
                CHECK (
                    manager_approval_threshold_cents >= 0
                ),

            effective_from TEXT NOT NULL,
            effective_to TEXT NOT NULL,

            policy_status TEXT NOT NULL
                DEFAULT 'ACTIVE'
                CHECK (
                    policy_status IN (
                        'ACTIVE', 'INACTIVE'
                    )
                ),

            CHECK (effective_to >= effective_from)
        )
    """)

    print("Procurement policies table ready.")

    # ==================================================
    # NEW: REQUISITION AND APPROVAL WORKFLOW
    # ==================================================

    # --------------------------------------------------
    # 11. Purchase Requisitions
    # --------------------------------------------------

    connection.execute("""
        CREATE TABLE IF NOT EXISTS purchase_requisitions (
            requisition_id TEXT PRIMARY KEY,

            idempotency_key TEXT NOT NULL UNIQUE,

            requester_id TEXT NOT NULL,
            cost_center_id TEXT NOT NULL,
            budget_id TEXT NOT NULL,

            offer_id TEXT NOT NULL,

            quantity INTEGER NOT NULL
                CHECK (quantity > 0),

            unit_price_cents INTEGER NOT NULL
                CHECK (unit_price_cents >= 0),

            total_amount_cents INTEGER NOT NULL
                CHECK (total_amount_cents >= 0),

            currency TEXT NOT NULL,

            requisition_status TEXT NOT NULL
                CHECK (
                    requisition_status IN (
                        'PENDING_APPROVAL',
                        'APPROVED',
                        'REJECTED',
                        'CANCELLED'
                    )
                ),

            approval_required INTEGER NOT NULL
                CHECK (approval_required IN (0, 1)),

            policy_id TEXT NOT NULL,

            request_fingerprint TEXT NOT NULL,

            created_at TEXT NOT NULL
                DEFAULT CURRENT_TIMESTAMP,

            updated_at TEXT NOT NULL
                DEFAULT CURRENT_TIMESTAMP,

            CHECK (
                total_amount_cents =
                quantity * unit_price_cents
            ),

            FOREIGN KEY (requester_id)
                REFERENCES employees(employee_id),

            FOREIGN KEY (cost_center_id)
                REFERENCES cost_centers(cost_center_id),

            FOREIGN KEY (budget_id)
                REFERENCES budgets(budget_id),

            FOREIGN KEY (offer_id)
                REFERENCES supplier_catalog(offer_id),

            FOREIGN KEY (policy_id)
                REFERENCES procurement_policies(policy_id)
        )
    """)

    print("Purchase requisitions table ready.")

    # --------------------------------------------------
    # 12. Approval Requests
    # --------------------------------------------------

    connection.execute("""
        CREATE TABLE IF NOT EXISTS approval_requests (
            approval_id TEXT PRIMARY KEY,

            requisition_id TEXT NOT NULL UNIQUE,

            approver_id TEXT NOT NULL,

            approval_status TEXT NOT NULL
                DEFAULT 'PENDING'
                CHECK (
                    approval_status IN (
                        'PENDING',
                        'APPROVED',
                        'REJECTED',
                        'CANCELLED'
                    )
                ),

            approval_comment TEXT,

            created_at TEXT NOT NULL
                DEFAULT CURRENT_TIMESTAMP,

            decided_at TEXT,

            FOREIGN KEY (requisition_id)
                REFERENCES purchase_requisitions(
                    requisition_id
                ),

            FOREIGN KEY (approver_id)
                REFERENCES employees(employee_id),

            CHECK (
                (approval_status = 'PENDING'
                    AND decided_at IS NULL)
                OR
                (approval_status = 'CANCELLED')
                OR
                (approval_status IN ('APPROVED', 'REJECTED')
                    AND decided_at IS NOT NULL)
            )
        )
    """)

    print("Approval requests table ready.")

    # --------------------------------------------------
    # 13. Audit Logs
    # --------------------------------------------------

    connection.execute("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            audit_id TEXT PRIMARY KEY,

            requisition_id TEXT,

            actor_id TEXT,
            actor_type TEXT NOT NULL
                CHECK (
                    actor_type IN (
                        'EMPLOYEE',
                        'SYSTEM',
                        'AGENT'
                    )
                ),

            action TEXT NOT NULL,

            previous_status TEXT,
            new_status TEXT,

            details_json TEXT NOT NULL DEFAULT '{}'
                CHECK (json_valid(details_json)),

            created_at TEXT NOT NULL
                DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (requisition_id)
                REFERENCES purchase_requisitions(
                    requisition_id
                )
        )
    """)

    print("Audit logs table ready.")

    # ==================================================
    # 14. Database Indexes
    # ==================================================

    connection.execute("""
        CREATE INDEX IF NOT EXISTS idx_contracts_supplier
        ON contracts(supplier_id)
    """)

    connection.execute("""
        CREATE INDEX IF NOT EXISTS idx_supplier_catalog_material
        ON supplier_catalog(material_id)
    """)

    connection.execute("""
        CREATE INDEX IF NOT EXISTS idx_supplier_catalog_contract
        ON supplier_catalog(contract_id)
    """)

    connection.execute("""
        CREATE INDEX IF NOT EXISTS idx_employees_cost_center
        ON employees(cost_center_id)
    """)

    connection.execute("""
        CREATE INDEX IF NOT EXISTS idx_employees_manager
        ON employees(manager_id)
    """)

    connection.execute("""
        CREATE INDEX IF NOT EXISTS idx_budgets_cost_center
        ON budgets(cost_center_id)
    """)

    connection.execute("""
        CREATE INDEX IF NOT EXISTS idx_policies_status_dates
        ON procurement_policies(
            policy_status,
            effective_from,
            effective_to
        )
    """)

    connection.execute("""
        CREATE INDEX IF NOT EXISTS idx_requisitions_requester
        ON purchase_requisitions(requester_id)
    """)

    connection.execute("""
        CREATE INDEX IF NOT EXISTS idx_requisitions_status
        ON purchase_requisitions(requisition_status)
    """)

    connection.execute("""
        CREATE INDEX IF NOT EXISTS idx_requisitions_budget
        ON purchase_requisitions(budget_id)
    """)

    connection.execute("""
        CREATE INDEX IF NOT EXISTS idx_approvals_approver_status
        ON approval_requests(
            approver_id,
            approval_status
        )
    """)

    connection.execute("""
        CREATE INDEX IF NOT EXISTS idx_audit_requisition
        ON audit_logs(
            requisition_id,
            created_at
        )
    """)

    print("Database indexes ready.")

    # ==================================================
    # 15. Commit Schema Changes
    # ==================================================

    connection.commit()

    print(
        "\nAll ProcureAI database tables are ready!"
    )

    # ==================================================
    # 16. Verify All 11 Tables
    # ==================================================

    expected_tables = {
        "materials",
        "suppliers",
        "contracts",
        "supplier_catalog",
        "cost_centers",
        "employees",
        "budgets",
        "procurement_policies",
        "purchase_requisitions",
        "approval_requests",
        "audit_logs"
    }

    rows = connection.execute("""
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
        ORDER BY name
    """).fetchall()

    existing_tables = {
        row[0] for row in rows
    }

    print("\nVerified tables:")

    for table_name in sorted(expected_tables):

        if table_name in existing_tables:
            print(f"  [OK] {table_name}")
        else:
            print(f"  [MISSING] {table_name}")

    missing_tables = (
        expected_tables - existing_tables
    )

    if missing_tables:
        raise RuntimeError(
            "Database setup incomplete. "
            f"Missing: {sorted(missing_tables)}"
        )

    print(
        "\nSUCCESS: All 11 ProcureAI tables verified."
    )

    # ==================================================
    # 17. Display Record Counts
    # ==================================================

    print("\nCurrent database record counts:")

    for table_name in sorted(expected_tables):

        count = connection.execute(
            f"SELECT COUNT(*) FROM {table_name}"
        ).fetchone()[0]

        print(
            f"  {table_name}: {count}"
        )

except Exception as error:

    print(
        "\nDatabase setup failed: "
        f"{type(error).__name__}: {error}"
    )

    raise

finally:
    connection.close()
