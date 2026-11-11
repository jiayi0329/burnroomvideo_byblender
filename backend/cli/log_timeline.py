"""Read safe JSONL events into a trace timeline; no API/DB/Blender calls."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from render_engine.jobs.operation_logging import _safe_fields, cli_operation, valid_id


def read_events(directory: Path, trace_id: str | None = None, job_id: str | None = None,
                limit: int = 5000) -> dict:
    if not directory.is_dir():
        raise ValueError('Operation log directory not found')
    if not 1 <= limit <= 20000:
        raise ValueError('Timeline limit must be 1..20000')
    if not trace_id and not job_id:
        raise ValueError('Choose one trace_id or job_id')
    if (trace_id and not valid_id(trace_id)) or (job_id and not valid_id(job_id)):
        raise ValueError('Invalid correlation ID')
    events = []; malformed = 0; truncated = False
    for file in sorted(directory.rglob('*.jsonl')):
        # Only operation shards, never frame/GPU logs or arbitrary JSON reports.
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}-\d+-[a-f0-9]{8}-\d+\.jsonl', file.name):
            continue
        with file.open('r', encoding='utf-8') as stream:
            while line := stream.readline(8193):
                if len(line) > 8192:
                    while line and not line.endswith('\n'):
                        line = stream.readline(8193)
                    malformed += 1
                    continue
                try:
                    row = json.loads(line)
                    if not isinstance(row, dict) or row.get('schema_version') != 1:
                        raise ValueError('Not an operation event')
                    timestamp = datetime.fromisoformat(row['ts'])
                    if timestamp.tzinfo is None:
                        raise ValueError('Timezone required')
                    if row.get('event') not in ('start', 'success', 'failure', 'cancel', 'accepted', 'progress'):
                        raise ValueError('Unknown event')
                    if (trace_id and row.get('trace_id') != trace_id) or (job_id and row.get('job_id') != job_id):
                        continue
                    # Re-apply allowlist before displaying even a local input file.
                    safe = {**_safe_fields(row), 'ts': timestamp.astimezone(timezone.utc).isoformat(), 'event': row['event']}
                except (ValueError, TypeError, KeyError):
                    malformed += 1
                    continue
                if len(events) >= limit:
                    truncated = True
                    continue
                events.append(safe)
    events.sort(key=lambda row: row['ts'])
    requests = [r for r in events if r.get('operation') == 'http.request' and r['event'] in ('success', 'failure', 'cancel')]
    durations = sorted(r['duration_ms'] for r in requests if 'duration_ms' in r)
    failures = sum(r['event'] != 'success' for r in requests)
    return {'events': events, 'event_counts': dict(Counter(e['event'] for e in events)),
            'http_summary': {'completed_requests': len(requests), 'failed_or_cancelled': failures,
                'failure_rate': failures/len(requests) if requests else None,
                'mean_ms': sum(durations)/len(durations) if durations else None,
                'p90_ms': durations[max(0, (9*len(durations)+9)//10-1)] if durations else None},
            'malformed_lines': malformed, 'truncated': truncated,
            'note': 'UTC events; durations are per span, not summed across requests/processes. Missing events are not success.'}


def markdown(report: dict) -> str:
    lines = ['# Operation timeline', '', report['note'], '',
             f"Events: {len(report['events'])}; malformed lines: {report['malformed_lines']}; truncated: {report['truncated']}", '',
             f"HTTP summary (selected events only): {report['http_summary']}", '',
             '| UTC | Operation | Stage | Result | ms | Request | Job | Error |',
             '| --- | --- | --- | --- | --- | --- | --- | --- |']
    for row in report['events']:
        keys = ('ts', 'operation', 'stage', 'event', 'duration_ms', 'request_id', 'job_id', 'error_code')
        lines.append('| ' + ' | '.join(str(row.get(key, '')) for key in keys) + ' |')
    return '\n'.join(lines) + '\n'


@cli_operation('operations.timeline')
def main() -> int:
    parser = argparse.ArgumentParser(description='Read one operation trace; never changes task state')
    parser.add_argument('--logs', type=Path, required=True)
    parser.add_argument('--trace-id')
    parser.add_argument('--job-id')
    parser.add_argument('--limit', type=int, default=5000)
    parser.add_argument('--output', type=Path, help='New Markdown output; refuses existing files')
    args = parser.parse_args()
    try:
        report = read_events(args.logs, args.trace_id, args.job_id, args.limit)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open('x', encoding='utf-8') as stream:
                stream.write(markdown(report))
        print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
        return 0
    except Exception as exc:
        print(f'[operation-timeline] failed: {type(exc).__name__}; no raw log data printed', flush=True)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
