"""Reset synthetic catalog data on the dedicated ProcureAI TEST database only.

Usage: python database/reset_and_seed.py --test --reset

This script never reads .env and refuses to run if transactional records exist.
It seeds materials, suppliers, contracts and supplier_catalog ONLY.
Identity, budgets and policies are seeded separately.
"""

from datetime import date, timedelta
import sys

import libsql
from db_target import test_credentials

if sys.argv[1:] != ['--test', '--reset']:
    raise SystemExit('Refusing reset. Usage: python database/reset_and_seed.py --test --reset')

database_url, auth_token = test_credentials()

materials = [
    ('MAT-1001', 'Industrial Safety Helmet, Type I', 'PPE', 'General industrial head protection', 'EA', 'ACTIVE'),
    ('MAT-1002', 'Electrical Insulating Helmet, Class E', 'PPE', 'Head protection rated for electrical work', 'EA', 'ACTIVE'),
    ('MAT-1003', 'Safety Helmet with Face Shield', 'PPE', 'Head and face protection combination', 'EA', 'ACTIVE'),
    ('MAT-1004', 'General Protective Gloves', 'PPE', 'General-purpose work gloves', 'PAIR', 'ACTIVE'),
    ('MAT-1005', 'Electrical Insulating Gloves', 'PPE', 'Protective gloves for appropriate electrical applications', 'PAIR', 'ACTIVE'),
    ('MAT-1006', 'Standard Safety Helmet, Legacy', 'PPE', 'Discontinued legacy helmet', 'EA', 'INACTIVE'),
]

suppliers = [
    ('SUP-1001', 'SafeGuard Supplies', 'ACTIVE'),
    ('SUP-1002', 'IndustrialSource', 'ACTIVE'),
    ('SUP-1003', 'Legacy Safety Co.', 'ACTIVE'),
    ('SUP-1004', 'Inactive Industrial Supplier', 'INACTIVE'),
]

today = date.today()
active_start = (today - timedelta(days=30)).isoformat()
active_end = (today + timedelta(days=365)).isoformat()
expired_start = (today - timedelta(days=730)).isoformat()
expired_end = (today - timedelta(days=30)).isoformat()

contracts = [
    ('CON-1001', 'SUP-1001', 'ACTIVE', active_start, active_end),
    ('CON-1002', 'SUP-1002', 'ACTIVE', active_start, active_end),
    ('CON-1003', 'SUP-1003', 'EXPIRED', expired_start, expired_end),
    ('CON-1004', 'SUP-1004', 'ACTIVE', active_start, active_end),
]

offers = [
    ('OFF-1001', 'CON-1001', 'MAT-1001', 25.00, 'USD', 5),
    ('OFF-1002', 'CON-1002', 'MAT-1001', 23.50, 'USD', 7),
    ('OFF-1003', 'CON-1003', 'MAT-1001', 21.00, 'USD', 3),
    ('OFF-1004', 'CON-1001', 'MAT-1002', 38.00, 'USD', 6),
    ('OFF-1005', 'CON-1002', 'MAT-1002', 36.50, 'USD', 8),
    ('OFF-1006', 'CON-1001', 'MAT-1003', 45.00, 'USD', 5),
    ('OFF-1007', 'CON-1001', 'MAT-1004', 8.50, 'USD', 4),
    ('OFF-1008', 'CON-1002', 'MAT-1004', 7.75, 'USD', 6),
    ('OFF-1009', 'CON-1001', 'MAT-1005', 32.00, 'USD', 6),
    ('OFF-1010', 'CON-1004', 'MAT-1001', 19.00, 'USD', 2),
]

required = {
    'materials', 'suppliers', 'contracts', 'supplier_catalog',
    'purchase_requisitions', 'approval_requests', 'audit_logs',
}

print('Verified target: procureai-test')
connection = libsql.connect(database=database_url, auth_token=auth_token)
try:
    connection.execute('PRAGMA foreign_keys = ON')
    connection.execute('BEGIN IMMEDIATE')
    existing = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    missing = required - existing
    if missing:
        raise RuntimeError(f'Missing tables: {sorted(missing)}. Run create_tables.py --test first.')

    for name in ('purchase_requisitions', 'approval_requests', 'audit_logs'):
        count = connection.execute(f'SELECT COUNT(*) FROM {name}').fetchone()[0]
        if count:
            raise RuntimeError(f'Reset blocked: {name} has {count} records. Use a fresh test database.')

    for table in ('supplier_catalog', 'contracts', 'suppliers', 'materials'):
        connection.execute(f'DELETE FROM {table}')

    for item in materials:
        connection.execute('INSERT INTO materials (material_id, material_name, category, description, uom, material_status) VALUES (?, ?, ?, ?, ?, ?)', item)
    for item in suppliers:
        connection.execute('INSERT INTO suppliers (supplier_id, supplier_name, supplier_status) VALUES (?, ?, ?)', item)
    for item in contracts:
        connection.execute('INSERT INTO contracts (contract_id, supplier_id, contract_status, start_date, end_date) VALUES (?, ?, ?, ?, ?)', item)
    for item in offers:
        connection.execute('INSERT INTO supplier_catalog (offer_id, contract_id, material_id, unit_price, currency, lead_time_days) VALUES (?, ?, ?, ?, ?, ?)', item)
    connection.commit()
    print('Synthetic test catalog seeded successfully.')
    for name in ('materials', 'suppliers', 'contracts', 'supplier_catalog'):
        count = connection.execute(f'SELECT COUNT(*) FROM {name}').fetchone()[0]
        print(f'{name}: {count}')
except Exception:
    connection.rollback()
    print('Reset stopped; transaction rolled back.')
    raise
finally:
    connection.close()
