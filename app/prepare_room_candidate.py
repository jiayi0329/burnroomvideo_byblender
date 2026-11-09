"""Compatibility path for render_engine.geometry.prepare_room_candidate."""
import sys
from importlib import import_module
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
_implementation = import_module('render_engine.geometry.prepare_room_candidate')

if __name__ == "__main__":
    _implementation.main()
else:
    sys.modules[__name__] = _implementation
