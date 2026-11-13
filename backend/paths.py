"""Backend installation paths; stdlib only, no connections or file writes."""
from pathlib import Path
import hashlib

BASELINE_MIGRATION_SHA256 = 'f87b9e6d1c6513fa7f8fe00c0fa2d3674796cd136cdc5b4c9080967fe97e5668'

MODULE_LOCATIONS = {
    'main': 'api',
    'room_api': 'api',
    'database': 'adapters/postgres',
    's3_io': 'adapters/minio',
    'import_rooms': 'cli',
    'check_catalog': 'cli',
    'observability': 'services',
    'request_logging': 'services',
    'log_timeline': 'cli',
    'room_registration': 'services',
    'room_asset_repository': 'adapters/postgres',
    'room_objects': 'adapters/minio',
    'register_room_assets': 'cli',
}
PACKAGE_FILES = (
    'backend/__init__.py', 'backend/paths.py',
    *(f'backend/{group}/__init__.py' for group in
      ('api', 'adapters', 'adapters/postgres', 'adapters/minio', 'cli', 'services')),
    *(f'backend/{group}/{name}.py' for name, group in MODULE_LOCATIONS.items()),
    'backend/database/migrations/001_rooms.sql',
)


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def legacy_render_script() -> Path:
    """Legacy API keeps its original worker and subprocess working directory."""
    return project_root()/'render_engine/legacy/F8_blender_render.py'


def migration_files(root: Path | None = None) -> tuple[Path, ...]:
    """Refuse missing or drifted baseline SQL before connecting to a database."""
    root = (root or project_root()).resolve()
    folder = root/'backend/database/migrations'
    canonical = folder/'001_rooms.sql'
    for path in (canonical,):
        if not path.is_file() or not path.resolve().is_relative_to(root):
            raise FileNotFoundError('Required catalog baseline migration missing from installation')
    if hashlib.sha256(canonical.read_bytes()).hexdigest() != BASELINE_MIGRATION_SHA256:
        raise ValueError('Baseline migration changed; do not edit applied migrations')
    return tuple(sorted(folder.glob('*.sql')))
