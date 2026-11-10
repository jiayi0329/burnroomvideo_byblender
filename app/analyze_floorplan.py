"""Compatibility path for tools.diagnostics.analyze_floorplan."""
import sys
from pathlib import Path
from importlib import import_module

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
_implementation = import_module('tools.diagnostics.analyze_floorplan')

if __name__ == "__main__":
    raise SystemExit(_implementation.main())
else:
    sys.modules[__name__] = _implementation
