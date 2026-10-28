"""Fail-closed Turso test database configuration for ProcureAI setup scripts."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from dotenv import dotenv_values


def test_credentials() -> tuple[str, str]:
    root = Path(__file__).resolve().parent.parent
    path = root / '.env.test'
    if not path.is_file():
        raise RuntimeError('Missing .env.test: refusing to select any database.')

    # Read only this file. Do not inherit database credentials from .env or the shell.
    config = dotenv_values(path)
    url = (config.get('TURSO_DATABASE_URL') or '').strip()
    token = (config.get('TURSO_AUTH_TOKEN') or '').strip()
    if not url or not token:
        raise RuntimeError('Missing test database URL or auth token in .env.test')

    parsed = urlparse(url)
    host = (parsed.hostname or '').lower()
    # Turso standard database URLs use libsql://<db>-<org>.turso.io.
    if parsed.scheme != 'libsql' or not host.startswith('procureai-test-') or not host.endswith('.turso.io'):
        raise RuntimeError('Database guard refused connection: expected libsql://procureai-test-<org>.turso.io')
    if parsed.username or parsed.password or parsed.port or parsed.query or parsed.fragment:
        raise RuntimeError('Unexpected database URL format; refusing connection.')
    return url, token
