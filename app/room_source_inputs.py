"""Compatibility path for render_engine.geometry.room_source_inputs."""
import sys
from importlib import import_module
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
_implementation = import_module('render_engine.geometry.room_source_inputs')

sys.modules[__name__] = _implementation
