
import os
from pathlib import Path

import libsql
from dotenv import load_dotenv
from fastapi import FastAPI, Query, HTTPException

# Read credentials from ProcureAI/.env
project_root = Path(__file__).resolve().parent.parent
load_dotenv(project_root / ".env")

app = FastAPI(
    title="ProcureAI Catalog API",
    version="0.1.0"
)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/v1/materials")
def search_materials(
    search: str = Query(min_length=2, max_length=100)
):
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

        # Escape SQL LIKE wildcard characters in the search term
        safe_search = (
            search.strip()
            .replace("\\", "\\\\")
            .replace("%", "\\%")
            .replace("_", "\\_")
        )

        rows = connection.execute(
            """
            SELECT
                material_id,
                material_name,
                category,
                description,
                uom
            FROM materials
            WHERE material_status = 'ACTIVE'
            AND (
                material_name LIKE ?
                OR description LIKE ?
            )
            ORDER BY material_name
            LIMIT 50
            """,
            (f"%{search.strip()}%", f"%{search.strip()}%")
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

        return {
            "search": search,
            "count": len(materials),
            "materials": materials
        }

    except Exception as e:
        print(f"Catalog API error: {type(e).__name__}: {e}")
        raise HTTPException(
            status_code=503,
            detail="Catalog service temporarily unavailable"
        )

    finally:
        if connection is not None:
            connection.close()
