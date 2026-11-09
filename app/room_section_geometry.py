"""Compatibility path for tools.diagnostics.room_section_geometry."""
import sys

from tools.diagnostics import room_section_geometry as _implementation

# Preserve module identity so legacy imports and monkeypatches share globals.
sys.modules[__name__] = _implementation
