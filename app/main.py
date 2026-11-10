"""Compatibility path for backend.api.main."""
import sys
from importlib import import_module
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
_implementation = import_module('backend.api.main')

sys.modules[__name__] = _implementation
