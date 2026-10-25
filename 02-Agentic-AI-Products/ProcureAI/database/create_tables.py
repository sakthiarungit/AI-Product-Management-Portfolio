import os
import libsql
from pathlib import Path
from dotenv import load_dotenv

# Find ProcureAI/.env even when running from another directory
project_root = Path(__file__).resolve().parent.parent
load_dotenv(project_root / ".env")

database_url = os.getenv("TURSO_DATABASE_URL")
auth_token = os.getenv("TURSO_AUTH_TOKEN")

if not database_url or not auth_token:
    raise ValueError("Missing Turso database configuration")

connection = libsql.connect(
    database=database_url,
    auth_token=auth_token
)

try:
    connection.execute("""
        CREATE TABLE IF NOT EXISTS materials (
            material_id TEXT PRIMARY KEY,
            material_name TEXT NOT NULL,
            category TEXT NOT NULL,
            description TEXT,
            uom TEXT NOT NULL,
            material_status TEXT NOT NULL DEFAULT 'ACTIVE'
                CHECK (material_status IN ('ACTIVE', 'INACTIVE')),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)

    connection.commit()

    print("Materials table created or already exists!")

finally:
    connection.close()