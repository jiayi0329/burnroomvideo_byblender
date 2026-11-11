"""Installed engine paths and complete source guards; stdlib, no Blender import.

All keys are relative to the package root, never to a caller's working directory.
Only canonical implementations and named presets are guarded.
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
    'operation_logging': 'jobs',
    'room_fire_config': 'effects',
    'room_demo_plan': 'propagation',
    'room_source_io': 'geometry',
    'room_source_inputs': 'geometry',
    'room_clip_geometry': 'geometry',
    'prepare_room_candidate': 'geometry',
    'F6_detect': 'legacy',
    'F7_spread': 'legacy',
    'F8_blender_render': 'legacy',
}
CODE_FILES = (
    'render_engine/__init__.py', 'render_engine/paths.py',
    'render_engine/geometry/floorplan_alignment.py',
    *(f'render_engine/{group}/__init__.py' for group in
      ('blender', 'jobs', 'effects', 'propagation', 'geometry', 'legacy')),
    *(f'render_engine/{group}/{name}.py' for name, group in MODULE_LOCATIONS.items()),
    *(f'configs/render/room_fire_round{revision}.json' for revision in (1, 2, 3)),
)


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def code_root(path: Path) -> Path:
    """Use the explicit installation root; no old-directory aliases."""
    return path.resolve()


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
