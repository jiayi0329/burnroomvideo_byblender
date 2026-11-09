"""Compatibility path for tools.diagnostics.diagnose_room_sections."""
import sys

from tools.diagnostics import diagnose_room_sections as _implementation

if __name__ == "__main__":
    raise SystemExit(_implementation.main())
else:
    sys.modules[__name__] = _implementation
