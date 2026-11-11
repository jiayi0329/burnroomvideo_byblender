"""Run only registered offline suites; no discovery or deployment side effects.

PRD engineering baseline / ARCHITECTURE process and private-data boundaries.
Run from the project root: python -B -m tests.run_regression
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tests.suites import GROUPS, selected_modules


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Explicit offline regression; no automatic test discovery')
    parser.add_argument('--group', action='append', choices=tuple(GROUPS))
    parser.add_argument('--list', action='store_true', help='List modules without importing or running tests')
    parser.add_argument('--report', type=Path, help='Write a new JSON report; refuses existing files')
    parser.add_argument('--verbose', action='store_true')
    args = parser.parse_args(argv)
    modules = selected_modules(args.group)
    if args.list:
        print('\n'.join(modules), flush=True)
        return 0
    for name in ('ROOM_DB_INTEGRATION', 'ROOM_TIMELINE_INTEGRATION'):
        if os.environ.get(name) == '1':
            parser.error(name + '=1 is incompatible with offline regression; no tests loaded')
    if args.report and args.report.exists():
        parser.error('Report already exists; choose a new path')
    started = time.perf_counter()
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromNames(modules)
    # unittest represents import errors as failed tests; never report a partial pass.
    result = unittest.TextTestRunner(verbosity=2 if args.verbose else 1).run(suite)
    report = {
        'mode': 'offline', 'modules': modules,
        'completed_at_utc': datetime.now(timezone.utc).isoformat(),
        'tests_run': result.testsRun, 'passed': result.testsRun - len(result.failures)
            - len(result.errors) - len(result.skipped) - len(result.expectedFailures)
            - len(result.unexpectedSuccesses),
        'failures': len(result.failures), 'errors': len(result.errors),
        'skipped': [{'test': test.id(), 'reason': reason} for test, reason in result.skipped],
        'expected_failures': len(result.expectedFailures),
        'unexpected_successes': len(result.unexpectedSuccesses),
        'successful': result.wasSuccessful(), 'elapsed_seconds': time.perf_counter() - started,
        'python': sys.version, 'executable': sys.executable,
        'remote_validation': False,
    }
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        with args.report.open('x', encoding='utf-8') as output:
            json.dump(report, output, ensure_ascii=False, indent=2)
            output.write('\n')
        print('[offline-tests] report=' + str(args.report), flush=True)
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
