"""Explicit offline allowlist. Importing this registry never loads test bodies."""
from tests.backend import MODULES as BACKEND
from tests.engine import MODULES as ENGINE
from tests.tools import MODULES as TOOLS
from tests.deploy import MODULES as DEPLOY

GROUPS = {'backend': BACKEND, 'engine': ENGINE, 'tools': TOOLS, 'deploy': DEPLOY}
PACKAGE_FILES = (
    'tests/__init__.py', 'tests/suites.py', 'tests/run_regression.py',
    'tests/backend/__init__.py', 'tests/engine/__init__.py',
    'tests/tools/__init__.py', 'tests/deploy/__init__.py',
    'tests/deploy/test_migration_cleanup.py',
    'tests/deploy/test_canonical_layout.py',
)


def selected_modules(groups: list[str] | None = None) -> tuple[str, ...]:
    """Select each registered module once, preserving the requested order."""
    result = []
    for group in groups or GROUPS:
        if group not in GROUPS:
            raise ValueError('Unknown offline test group: ' + group)
        for module in GROUPS[group]:
            if module not in result:
                result.append(module)
    return tuple(result)
