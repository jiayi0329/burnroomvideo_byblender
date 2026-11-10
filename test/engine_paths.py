"""Locate actual implementations for AST regressions; shims are tested separately."""
from pathlib import Path
from render_engine.paths import MODULE_LOCATIONS
from backend.paths import MODULE_LOCATIONS as BACKEND_MODULES

ROOT = Path(__file__).resolve().parents[1]


def source_path(name: str) -> Path:
    stem = Path(name).stem
    group = MODULE_LOCATIONS.get(stem)
    if group:
        return ROOT/'render_engine'/group/(stem+'.py')
    if stem in BACKEND_MODULES:
        return ROOT/'backend'/BACKEND_MODULES[stem]/(stem+'.py')
    return ROOT/'app'/name
