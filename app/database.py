"""Database connection and explicit versioned migration; never used by Blender."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any


def connect(admin: bool = False) -> Any:
    import psycopg
    from psycopg.rows import dict_row
    password = os.getenv('POSTGRES_PASSWORD' if admin else 'PGPASSWORD')
    if not password or password.startswith('REPLACE_'):
        raise ValueError('Database password is not configured')
    return psycopg.connect(
        host=os.getenv('PGHOST', 'postgres'), port=os.getenv('PGPORT', '5432'),
        dbname=os.getenv('PGDATABASE', 'burnroom'),
        user='postgres' if admin else os.getenv('PGUSER', 'burnroom_app'),
        password=password, connect_timeout=5, row_factory=dict_row,
        options='-c statement_timeout=30000',
    )


def migrate() -> None:
    from psycopg import sql
    role = os.getenv('PGUSER', 'burnroom_app')
    password = os.getenv('PGPASSWORD', '')
    if role in ('postgres', '') or not password or password.startswith('REPLACE_'):
        raise ValueError('Configure a dedicated application role and password')
    with connect(admin=True) as conn:
        conn.execute('SELECT pg_advisory_xact_lock(623017)')
        conn.execute('CREATE TABLE IF NOT EXISTS schema_migrations (version text PRIMARY KEY, sha256 text NOT NULL)')
        for path in sorted((Path(__file__).parent / 'db').glob('*.sql')):
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            existing = conn.execute('SELECT sha256 FROM schema_migrations WHERE version=%s', (path.name,)).fetchone()
            if existing:
                if existing['sha256'] != digest:
                    raise ValueError('Applied migration checksum changed')
                continue
            conn.execute(path.read_text(encoding='utf-8'))
            conn.execute('INSERT INTO schema_migrations VALUES (%s,%s)', (path.name, digest))
        if not conn.execute('SELECT 1 FROM pg_roles WHERE rolname=%s', (role,)).fetchone():
            conn.execute(sql.SQL('CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE').format(sql.Identifier(role)))
        conn.execute(sql.SQL('ALTER ROLE {} PASSWORD {}').format(sql.Identifier(role), sql.Literal(password)))
        conn.execute(sql.SQL('GRANT CONNECT ON DATABASE {} TO {}').format(sql.Identifier(os.getenv('PGDATABASE', 'burnroom')), sql.Identifier(role)))
        conn.execute(sql.SQL('GRANT USAGE ON SCHEMA public TO {}').format(sql.Identifier(role)))
        tables = 'scenes layout_versions rooms points point_room_memberships assets render_jobs render_job_assets'.split()
        for table in tables:
            conn.execute(sql.SQL('GRANT SELECT, INSERT, UPDATE ON TABLE {} TO {}').format(sql.Identifier(table), sql.Identifier(role)))
        conn.execute(sql.SQL('GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {}').format(sql.Identifier(role)))
    print('[database] migrations applied', flush=True)


if __name__ == '__main__':
    try:
        migrate()
    except Exception as exc:
        print(f'[database] migration failed: {type(exc).__name__}; check server configuration', flush=True)
        raise SystemExit(1) from None
