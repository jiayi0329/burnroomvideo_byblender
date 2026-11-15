"""Internal detached launcher. Requires API reservation and parent pipe handoff."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.services.room_job_service import run_reserved
from render_engine.jobs.operation_logging import default_sink, inherited_context, stage


def main() -> int:
    parser = argparse.ArgumentParser(description='Run an API-reserved Room8 job; not a public render bypass')
    parser.add_argument('--job', type=Path, required=True)
    args = parser.parse_args()
    with inherited_context(default_sink()):
        try:
            with stage('room.api', 'launcher_process'):
                run_reserved(args.job)
            return 0
        except Exception as exc:
            print(f'[room-job-api] failed: {type(exc).__name__}; frames and logs retained', flush=True)
            return 1


if __name__ == '__main__':
    raise SystemExit(main())
