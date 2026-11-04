
"""One-time synthetic DEVELOPMENT budget adjustment.

Changes only BUD-MAINT-2026 allocated amount.
Does not modify commitments, spending, approvals, or requisitions.

Run:
    python database/adjust_demo_budget.py
"""

from pathlib import Path
from urllib.parse import urlparse

import libsql
from dotenv import dotenv_values


ROOT = Path(__file__).resolve().parent.parent
config = dotenv_values(ROOT / ".env")

url = (config.get("TURSO_DATABASE_URL") or "").strip()
token = (config.get("TURSO_AUTH_TOKEN") or "").strip()

if not url or not token:
    raise SystemExit("Missing development credentials.")

parsed = urlparse(url)
host = (parsed.hostname or "").lower()

if (
    parsed.scheme != "libsql"
    or not host.startswith("procureai-dev-")
    or not host.endswith(".turso.io")
):
    raise SystemExit("Blocked: not the ProcureAI development database.")

budget_id = "BUD-MAINT-2026"
original_allocation = 1_000_000
new_allocation = 2_500_000

conn = libsql.connect(database=url, auth_token=token)

try:
    conn.execute("BEGIN IMMEDIATE")

    before = conn.execute(
        """
        SELECT allocated_amount_cents,
               committed_amount_cents,
               spent_amount_cents
        FROM budgets
        WHERE budget_id = ?
          AND cost_center_id = ?
          AND fiscal_year = ?
        """,
        (budget_id, "CC-MAINT-SEA", 2026),
    ).fetchone()

    if before is None:
        raise RuntimeError("Expected budget record not found.")

    allocated, committed, spent = map(int, before)

    if allocated == new_allocation:
        print("Budget allocation already equals $25,000.")
    elif allocated != original_allocation:
        raise RuntimeError(
            "Unexpected original allocation; refusing to overwrite."
        )
    else:
        conn.execute(
            """
            UPDATE budgets
            SET allocated_amount_cents = ?
            WHERE budget_id = ?
              AND cost_center_id = ?
              AND fiscal_year = ?
              AND allocated_amount_cents = ?
            """,
            (
                new_allocation,
                budget_id,
                "CC-MAINT-SEA",
                2026,
                original_allocation,
            ),
        )

    after = conn.execute(
        """
        SELECT allocated_amount_cents,
               committed_amount_cents,
               spent_amount_cents
        FROM budgets
        WHERE budget_id = ?
        """,
        (budget_id,),
    ).fetchone()

    if after is None:
        raise RuntimeError("Budget disappeared during update.")

    new_allocated, new_committed, new_spent = map(int, after)

    if (
        new_allocated != new_allocation
        or new_committed != committed
        or new_spent != spent
    ):
        raise RuntimeError("Budget verification failed; rolling back.")

    conn.commit()

    print("Development demo budget verified.")
    print(f"Budget: {budget_id}")
    print(f"Allocated: ${new_allocated / 100:,.2f}")
    print(f"Committed: ${new_committed / 100:,.2f}")
    print(f"Spent: ${new_spent / 100:,.2f}")
    print(
        "Available: "
        f"${(new_allocated-new_committed-new_spent)/100:,.2f}"
    )

except Exception:
    conn.rollback()
    raise
finally:
    conn.close()
