"""Read-only application-role check, before import and after restore. No Blender."""
from __future__ import annotations

import argparse
import json
from typing import Any

from app.database import connect

TABLES = ('scenes', 'layout_versions', 'rooms', 'points', 'point_room_memberships',
          'assets', 'render_jobs', 'render_job_assets')


def check_catalog(scene_code: str | None = None) -> dict[str, Any]:
    with connect() as conn:
        role = conn.execute('SELECT current_user AS name, rolsuper, rolcreatedb, rolcreaterole FROM pg_roles WHERE rolname=current_user').fetchone()
        if not role or any(role[key] for key in ('rolsuper', 'rolcreatedb', 'rolcreaterole')):
            raise ValueError('Expected a restricted application role')
        for table in TABLES:
            table_name = f'public.{table}'
            rights = conn.execute("SELECT has_table_privilege(current_user,%s,'SELECT') AND has_table_privilege(current_user,%s,'INSERT') AND has_table_privilege(current_user,%s,'UPDATE') AS allowed", (table_name, table_name, table_name)).fetchone()
            if not rights['allowed']:
                raise ValueError('Application table access is incomplete')
        summary: dict[str, Any] = {'status': 'ok', 'role': role['name'], 'tables_checked': len(TABLES)}
        if scene_code:
            layout = conn.execute('SELECT l.id,l.xy_verified FROM layout_versions l JOIN scenes s ON s.id=l.scene_id WHERE s.scene_code=%s ORDER BY l.id DESC LIMIT 1', (scene_code,)).fetchone()
            if not layout:
                raise ValueError('No imported layout for requested scene')
            counts = conn.execute('SELECT count(*) AS rooms,count(*) FILTER(WHERE is_valid) AS valid_rooms FROM rooms WHERE layout_version_id=%s', (layout['id'],)).fetchone()
            points = conn.execute('SELECT count(*) AS points FROM points p JOIN scenes s ON s.id=p.scene_id WHERE s.scene_code=%s', (scene_code,)).fetchone()
            summary.update(layout_version_id=layout['id'], xy_verified=layout['xy_verified'], **counts, **points)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description='Check catalog using application credentials, without changing data')
    parser.add_argument('--scene')
    args = parser.parse_args()
    try:
        print(json.dumps(check_catalog(args.scene)), flush=True)
        return 0
    except Exception as exc:
        print(f'[catalog-check] failed: {type(exc).__name__}; check migrations/application credentials', flush=True)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
