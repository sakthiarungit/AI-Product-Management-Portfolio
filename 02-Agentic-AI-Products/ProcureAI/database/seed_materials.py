
import os
from pathlib import Path

import libsql
from dotenv import load_dotenv

# Load environment variables from ProcureAI/.env
project_root = Path(__file__).resolve().parent.parent
load_dotenv(project_root / ".env")

database_url = os.getenv("TURSO_DATABASE_URL")
auth_token = os.getenv("TURSO_AUTH_TOKEN")

if not database_url or not auth_token:
    raise ValueError("Missing Turso database configuration")

# Synthetic procurement material master records
materials = [
    ("MAT-1001", "Industrial Safety Helmet, Type I", "PPE",
     "General industrial head protection", "EA", "ACTIVE"),

    ("MAT-1002", "Electrical Insulating Helmet, Class E", "PPE",
     "Head protection rated for electrical work", "EA", "ACTIVE"),

    ("MAT-1003", "Safety Helmet with Face Shield", "PPE",
     "Head and face protection combination", "EA", "ACTIVE"),

    ("MAT-1004", "General Protective Gloves", "PPE",
     "General-purpose work gloves", "PAIR", "ACTIVE"),

    ("MAT-1005", "Electrical Insulating Gloves", "PPE",
     "Protective gloves for appropriate electrical applications", "PAIR", "ACTIVE"),

    ("MAT-1006", "Standard Safety Helmet, Legacy", "PPE",
     "Discontinued legacy helmet", "EA", "INACTIVE"),
]

connection = libsql.connect(
    database=database_url,
    auth_token=auth_token
)

try:
    for material in materials:
        connection.execute(
            """
            INSERT INTO materials (
                material_id,
                material_name,
                category,
                description,
                uom,
                material_status
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(material_id) DO NOTHING
            """,
            material
        )

    connection.commit()
    print("Material seed data loaded successfully!")

    rows = connection.execute(
        """
        SELECT material_id, material_name, material_status
        FROM materials
        ORDER BY material_id
        """
    ).fetchall()

    for row in rows:
        print(row)

finally:
    connection.close()
