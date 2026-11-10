"""Compatibility path for tools.diagnostics.blender.F8_inspect_room_import."""
import sys
from pathlib import Path
from importlib import import_module

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
_implementation = import_module('tools.diagnostics.blender.F8_inspect_room_import')

if __name__ == "__main__":
    _implementation.main()
else:
    sys.modules[__name__] = _implementation
