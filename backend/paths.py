"""Backend installation paths; stdlib only, no connections or file writes."""
from pathlib import Path

MODULE_LOCATIONS = {
    'main': 'api',
    'room_api': 'api',
    'database': 'adapters/postgres',
    's3_io': 'adapters/minio',
    'import_rooms': 'cli',
    'check_catalog': 'cli',
    'observability': 'services',
}
PACKAGE_FILES = (
    'backend/__init__.py', 'backend/paths.py',
    *(f'backend/{group}/__init__.py' for group in
      ('api', 'adapters', 'adapters/postgres', 'adapters/minio', 'cli', 'services')),
    *(f'backend/{group}/{name}.py' for name, group in MODULE_LOCATIONS.items()),
    'backend/db/migrations/001_rooms.sql',
)


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def legacy_render_script() -> Path:
    """Legacy API keeps its original worker and subprocess working directory."""
    return project_root()/'app/F8_blender_render.py'


def migration_files(root: Path | None = None) -> tuple[Path, ...]:
    """Refuse missing or drifted baseline SQL before connecting to a database."""
    root = (root or project_root()).resolve()
    folder = root/'backend/db/migrations'
    canonical = folder/'001_rooms.sql'
    compatibility = root/'app/db/001_rooms.sql'
    for path in (canonical, compatibility):
        if not path.is_file() or not path.resolve().is_relative_to(root):
            raise FileNotFoundError('Required catalog baseline migration missing from installation')
    if canonical.read_bytes() != compatibility.read_bytes():
        raise ValueError('Baseline migration differs from compatibility SQL; do not change applied migrations')
    return tuple(sorted(folder.glob('*.sql')))
