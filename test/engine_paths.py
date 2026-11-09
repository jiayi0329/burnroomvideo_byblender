"""Locate actual implementations for AST regressions; shims are tested separately."""
from pathlib import Path
from render_engine.paths import MODULE_LOCATIONS

ROOT = Path(__file__).resolve().parents[1]


def source_path(name: str) -> Path:
    stem = Path(name).stem
    group = MODULE_LOCATIONS.get(stem)
    return ROOT/'render_engine'/group/(stem+'.py') if group else ROOT/'app'/name
