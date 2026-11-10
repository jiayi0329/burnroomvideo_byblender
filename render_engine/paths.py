"""Installed engine paths and complete source guards; stdlib, no Blender import.

All keys are relative to the package root, never to a caller's working directory.
The app shims and preset mirrors remain guarded during the migration period.
"""
from pathlib import Path


MODULE_LOCATIONS = {
    'F8_prepare_room_asset': 'blender',
    'F8_room_demo': 'blender',
    'F8_room_animation': 'blender',
    'F8_room_fire_style': 'blender',
    'F8_room_helpers': 'blender',
    'run_room_animation': 'jobs',
    'room_animation_job': 'jobs',
    'room_fire_config': 'effects',
    'room_demo_plan': 'propagation',
    'room_source_io': 'geometry',
    'room_source_inputs': 'geometry',
    'room_clip_geometry': 'geometry',
    'prepare_room_candidate': 'geometry',
}
CODE_FILES = (
    'render_engine/__init__.py', 'render_engine/paths.py',
    'render_engine/geometry/floorplan_alignment.py',
    *(f'render_engine/{group}/__init__.py' for group in
      ('blender', 'jobs', 'effects', 'propagation', 'geometry')),
    *(f'render_engine/{group}/{name}.py' for name, group in MODULE_LOCATIONS.items()),
    *(f'app/{name}.py' for name in MODULE_LOCATIONS),
    *(f'{folder}/room_fire_round{revision}.json' for folder in ('configs/render', 'app')
      for revision in (1, 2, 3)),
)


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def code_root(path: Path) -> Path:
    """Accept the legacy app directory as well as the installed package root."""
    resolved = path.resolve()
    return resolved.parent if resolved.name == 'app' else resolved


def default_config() -> Path:
    return project_root()/'configs/render/room_fire_round3.json'


def worker_script(root: Path) -> Path:
    return code_root(root)/'render_engine/blender/F8_room_animation.py'


def source_paths(root: Path) -> dict[str, Path]:
    """Refuse incomplete installations before creating a rendering job."""
    root = code_root(root)
    result = {}
    for name in CODE_FILES:
        path = (root/name).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise FileNotFoundError('Required engine source/config missing or outside package: '+name)
        result[name] = path
    return result
