
import os
import sys
from pathlib import Path
from datetime import date, timedelta
from urllib.parse import urlparse

import libsql
from dotenv import load_dotenv


# --------------------------------------------------
# 1. Load configuration
# --------------------------------------------------

project_root = Path(__file__).resolve().parent.parent
load_dotenv(project_root / ".env", override=True)

database_url = os.getenv("TURSO_DATABASE_URL")
auth_token = os.getenv("TURSO_AUTH_TOKEN")

if not database_url or not auth_token:
    raise ValueError("Missing Turso database configuration")


# --------------------------------------------------
# 2. Safety checks
# --------------------------------------------------

if "--reset" not in sys.argv:
    print("This script deletes and reloads sample data.")
    print("Run with: python database/reset_and_seed.py --reset")
    sys.exit(1)

database_host = urlparse(database_url).hostname or ""

if not database_host.startswith("procureai-dev-"):
    raise RuntimeError(
        "Reset blocked: expected dedicated procureai-dev database."
    )


# --------------------------------------------------
# 3. Synthetic Material Master
# --------------------------------------------------

materials = [
    (
        "MAT-1001",
        "Industrial Safety Helmet, Type I",
        "PPE",
        "General industrial head protection",
        "EA",
        "ACTIVE"
    ),
    (
        "MAT-1002",
        "Electrical Insulating Helmet, Class E",
        "PPE",
        "Head protection rated for electrical work",
        "EA",
        "ACTIVE"
    ),
    (
        "MAT-1003",
        "Safety Helmet with Face Shield",
        "PPE",
        "Head and face protection combination",
        "EA",
        "ACTIVE"
    ),
    (
        "MAT-1004",
        "General Protective Gloves",
        "PPE",
        "General-purpose work gloves",
        "PAIR",
        "ACTIVE"
    ),
    (
        "MAT-1005",
        "Electrical Insulating Gloves",
        "PPE",
        "Protective gloves for appropriate electrical applications",
        "PAIR",
        "ACTIVE"
    ),
    (
        "MAT-1006",
        "Standard Safety Helmet, Legacy",
        "PPE",
        "Discontinued legacy helmet",
        "EA",
        "INACTIVE"
    )
]


# --------------------------------------------------
# 4. Synthetic Supplier Master
# --------------------------------------------------

suppliers = [
    ("SUP-1001", "SafeGuard Supplies", "ACTIVE"),
    ("SUP-1002", "IndustrialSource", "ACTIVE"),
    ("SUP-1003", "Legacy Safety Co.", "ACTIVE"),
    ("SUP-1004", "Inactive Industrial Supplier", "INACTIVE")
]


# --------------------------------------------------
# 5. Synthetic Supplier Contracts
# --------------------------------------------------

today = date.today()

active_start = (today - timedelta(days=30)).isoformat()
active_end = (today + timedelta(days=365)).isoformat()

expired_start = (today - timedelta(days=730)).isoformat()
expired_end = (today - timedelta(days=30)).isoformat()

contracts = [
    (
        "CON-1001",
        "SUP-1001",
        "ACTIVE",
        active_start,
        active_end
    ),
    (
        "CON-1002",
        "SUP-1002",
        "ACTIVE",
        active_start,
        active_end
    ),
    (
        "CON-1003",
        "SUP-1003",
        "EXPIRED",
        expired_start,
        expired_end
    ),
    (
        "CON-1004",
        "SUP-1004",
        "ACTIVE",
        active_start,
        active_end
    )
]


# --------------------------------------------------
# 6. Synthetic Supplier Catalog and Contract Prices
# --------------------------------------------------

offers = [
    # Industrial Safety Helmet
    ("OFF-1001", "CON-1001", "MAT-1001", 25.00, "USD", 5),
    ("OFF-1002", "CON-1002", "MAT-1001", 23.50, "USD", 7),
    ("OFF-1003", "CON-1003", "MAT-1001", 21.00, "USD", 3),

    # Electrical Insulating Helmet
    ("OFF-1004", "CON-1001", "MAT-1002", 38.00, "USD", 6),
    ("OFF-1005", "CON-1002", "MAT-1002", 36.50, "USD", 8),

    # Safety Helmet with Face Shield
    ("OFF-1006", "CON-1001", "MAT-1003", 45.00, "USD", 5),

    # General Protective Gloves
    ("OFF-1007", "CON-1001", "MAT-1004", 8.50, "USD", 4),
    ("OFF-1008", "CON-1002", "MAT-1004", 7.75, "USD", 6),

    # Electrical Insulating Gloves
    ("OFF-1009", "CON-1001", "MAT-1005", 32.00, "USD", 6),

    # Deliberately ineligible offer from inactive supplier
    ("OFF-1010", "CON-1004", "MAT-1001", 19.00, "USD", 2)
]


# --------------------------------------------------
# 7. Connect to Turso Cloud
# --------------------------------------------------

connection = libsql.connect(
    database=database_url,
    auth_token=auth_token
)

try:
    connection.execute("PRAGMA foreign_keys = ON")

    # Verify the expected schema exists
    required_tables = {
        "materials",
        "suppliers",
        "contracts",
        "supplier_catalog"
    }

    rows = connection.execute("""
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
    """).fetchall()

    existing_tables = {row[0] for row in rows}
    missing_tables = required_tables - existing_tables

    if missing_tables:
        raise RuntimeError(
            f"Missing database tables: {sorted(missing_tables)}. "
            "Run create_tables.py first."
        )

    print("Starting ProcureAI database reset...")

    # --------------------------------------------------
    # 8. Delete existing sample records
    # --------------------------------------------------

    # Children first, then parent records
    connection.execute("DELETE FROM supplier_catalog")
    connection.execute("DELETE FROM contracts")
    connection.execute("DELETE FROM suppliers")
    connection.execute("DELETE FROM materials")

    print("Existing sample data cleared.")

    # --------------------------------------------------
    # 9. Insert Material Master
    # --------------------------------------------------

    for material in materials:
        connection.execute("""
            INSERT INTO materials (
                material_id,
                material_name,
                category,
                description,
                uom,
                material_status
            )
            VALUES (?, ?, ?, ?, ?, ?)
        """, material)

    print("Materials inserted.")

    # --------------------------------------------------
    # 10. Insert Suppliers
    # --------------------------------------------------

    for supplier in suppliers:
        connection.execute("""
            INSERT INTO suppliers (
                supplier_id,
                supplier_name,
                supplier_status
            )
            VALUES (?, ?, ?)
        """, supplier)

    print("Suppliers inserted.")

    # --------------------------------------------------
    # 11. Insert Contracts
    # --------------------------------------------------

    for contract in contracts:
        connection.execute("""
            INSERT INTO contracts (
                contract_id,
                supplier_id,
                contract_status,
                start_date,
                end_date
            )
            VALUES (?, ?, ?, ?, ?)
        """, contract)

    print("Contracts inserted.")

    # --------------------------------------------------
    # 12. Insert Supplier Offers
    # --------------------------------------------------

    for offer in offers:
        connection.execute("""
            INSERT INTO supplier_catalog (
                offer_id,
                contract_id,
                material_id,
                unit_price,
                currency,
                lead_time_days
            )
            VALUES (?, ?, ?, ?, ?, ?)
        """, offer)

    # --------------------------------------------------
    # 13. Commit all database changes
    # --------------------------------------------------

    connection.commit()

    print("\nDatabase reset and seed completed.")

    # --------------------------------------------------
    # 14. Verify record counts
    # --------------------------------------------------

    print("\nRecord counts:")

    for table in [
        "materials",
        "suppliers",
        "contracts",
        "supplier_catalog"
    ]:
        count = connection.execute(
            f"SELECT COUNT(*) FROM {table}"
        ).fetchone()[0]

        print(f"  {table}: {count}")

except Exception:
    connection.rollback()
    print("Database reset failed.")
    raise

finally:
    connection.close()
