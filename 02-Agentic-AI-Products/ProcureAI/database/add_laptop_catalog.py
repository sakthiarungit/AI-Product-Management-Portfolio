
"""Add synthetic laptop catalog data to ProcureAI DEVELOPMENT only.

Run from the ProcureAI project root:
    python database/add_laptop_catalog.py

Does not reset tables, update budgets, or modify requisitions.
"""

from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlparse

import libsql
from dotenv import dotenv_values


ROOT = Path(__file__).resolve().parent.parent
config = dotenv_values(ROOT / ".env")

database_url = (config.get("TURSO_DATABASE_URL") or "").strip()
auth_token = (config.get("TURSO_AUTH_TOKEN") or "").strip()

if not database_url or not auth_token:
    raise SystemExit("Missing development database credentials in .env")

host = (urlparse(database_url).hostname or "").lower()

if (
    urlparse(database_url).scheme != "libsql"
    or not host.startswith("procureai-dev-")
    or not host.endswith(".turso.io")
):
    raise SystemExit(
        "Blocked: expected the dedicated procureai-dev database."
    )


# Synthetic catalog data — not real commercial offers.
materials = [
    (
        "MAT-2001",
        "Standard Business Laptop",
        "IT Equipment",
        "14-inch laptop, 16 GB RAM, 512 GB SSD",
        "EA",
        "ACTIVE",
    ),
    (
        "MAT-2002",
        "Performance Business Laptop",
        "IT Equipment",
        "14-inch laptop, 32 GB RAM, 1 TB SSD",
        "EA",
        "ACTIVE",
    ),
    (
        "MAT-2003",
        "Lightweight Business Laptop",
        "IT Equipment",
        "13-inch laptop, 16 GB RAM, 512 GB SSD",
        "EA",
        "ACTIVE",
    ),
]

suppliers = [
    ("SUP-2001", "OfficeTech Solutions", "ACTIVE"),
    ("SUP-2002", "BusinessIT Direct", "ACTIVE"),
]

today = date.today()
start_date = (today - timedelta(days=30)).isoformat()
end_date = (today + timedelta(days=365)).isoformat()

contracts = [
    ("CON-2001", "SUP-2001", "ACTIVE", start_date, end_date),
    ("CON-2002", "SUP-2002", "ACTIVE", start_date, end_date),
]

offers = [
    # Standard Business Laptop
    ("OFF-2001", "CON-2001", "MAT-2001", 950.00, "USD", 7),
    ("OFF-2002", "CON-2002", "MAT-2001", 995.00, "USD", 3),

    # Performance Business Laptop
    ("OFF-2003", "CON-2001", "MAT-2002", 1450.00, "USD", 7),
    ("OFF-2004", "CON-2002", "MAT-2002", 1495.00, "USD", 4),

    # Lightweight Business Laptop
    ("OFF-2005", "CON-2001", "MAT-2003", 1100.00, "USD", 6),
    ("OFF-2006", "CON-2002", "MAT-2003", 1150.00, "USD", 3),
]

connection = libsql.connect(
    database=database_url,
    auth_token=auth_token,
)

try:
    connection.execute("PRAGMA foreign_keys = ON")

    required_tables = {
        "materials",
        "suppliers",
        "contracts",
        "supplier_catalog",
    }

    existing_tables = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }

    if not required_tables.issubset(existing_tables):
        raise RuntimeError(
            "Required catalog tables are missing. No records inserted."
        )

    # Avoid updating records or overwriting existing IDs.
    # If the script is run twice, existing matching IDs are skipped.
    connection.execute("BEGIN IMMEDIATE")

    for record in materials:
        connection.execute(
            """
            INSERT OR IGNORE INTO materials
            (material_id, material_name, category, description,
             uom, material_status)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            record,
        )

    for record in suppliers:
        connection.execute(
            """
            INSERT OR IGNORE INTO suppliers
            (supplier_id, supplier_name, supplier_status)
            VALUES (?, ?, ?)
            """,
            record,
        )

    for record in contracts:
        connection.execute(
            """
            INSERT OR IGNORE INTO contracts
            (contract_id, supplier_id, contract_status,
             start_date, end_date)
            VALUES (?, ?, ?, ?, ?)
            """,
            record,
        )

    for record in offers:
        connection.execute(
            """
            INSERT OR IGNORE INTO supplier_catalog
            (offer_id, contract_id, material_id,
             unit_price, currency, lead_time_days)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            record,
        )

    connection.commit()

    print("Laptop catalog update completed.")

    for material_id, *_ in materials:
        row = connection.execute(
            """
            SELECT material_id, material_name
            FROM materials
            WHERE material_id = ?
            """,
            (material_id,),
        ).fetchone()

        print(f"Material: {row[0]} - {row[1]}")

    print(f"Laptop offers configured: {len(offers)}")

except Exception:
    connection.rollback()
    raise

finally:
    connection.close()
