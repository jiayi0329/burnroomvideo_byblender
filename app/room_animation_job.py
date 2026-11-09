"""Compatibility path for render_engine.jobs.room_animation_job."""
import sys
from importlib import import_module
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
_implementation = import_module('render_engine.jobs.room_animation_job')

sys.modules[__name__] = _implementation
