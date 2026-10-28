"""Single, fail-closed database environment selector for ProcureAI API.

Development (default): .env
Isolated transaction-test server (explicit): PROCUREAI_ENV=test -> .env.test

Never display or log the database token.
"""

import os
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parent.parent
_CONFIGURED_ENV = None


def configure_database() -> str:
    global _CONFIGURED_ENV
    selected = os.environ.get("PROCUREAI_ENV", "development").strip().lower()
    if selected not in {"development", "test"}:
        raise RuntimeError("PROCUREAI_ENV must be 'development' or 'test'")
    if _CONFIGURED_ENV and _CONFIGURED_ENV != selected:
        raise RuntimeError("Cannot switch database environment in a running process")

    target_file = _ROOT / (".env.test" if selected == "test" else ".env")
    if not target_file.is_file():
        raise RuntimeError(f"Missing configuration file: {target_file.name}")

    # Explicit file wins over any inherited developer credentials.
    load_dotenv(target_file, override=True)
    url = os.environ.get("TURSO_DATABASE_URL", "")
    token = os.environ.get("TURSO_AUTH_TOKEN", "")
    if not url or not token:
        raise RuntimeError("Missing Turso connection settings")

    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "libsql" or not host.endswith(".turso.io"):
        raise RuntimeError("Expected a hosted Turso libsql database URL")

    if selected == "test":
        if not host.startswith("procureai-test-"):
            raise RuntimeError("Test API blocked: database is not procureai-test")
        if os.environ.get("ENABLE_DEMO_WRITES", "").lower() != "true":
            raise RuntimeError("Test API requires ENABLE_DEMO_WRITES=true")
        if os.environ.get("DEMO_REQUESTER_ID") != "EMP-1001":
            raise RuntimeError("Test API requires synthetic requester EMP-1001")
        if os.environ.get("DEMO_APPROVER_ID") != "EMP-1002":
            raise RuntimeError("Test API requires synthetic approver EMP-1002")

    _CONFIGURED_ENV = selected
    return selected
