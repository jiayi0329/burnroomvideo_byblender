"""Shared stdlib operation events; no renderer, database or import-time IO.

Request/task state remains owned by its existing files. These append-only events
provide correlation and timing, never a replacement state machine.
"""
from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from functools import wraps
import inspect
import json
import logging
import os
from pathlib import Path
import re
import sys
import threading
import time
from typing import Any
import uuid

from render_engine.paths import project_root

_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}\Z')
_LABEL = re.compile(r'[A-Za-z0-9_./{}:-]{1,180}\Z')
_CONTEXT_FIELDS = ('trace_id', 'request_id', 'span_id', 'parent_span_id',
                   'scene_code', 'room_id', 'asset_version', 'job_id', 'attempt_id')
_LABEL_FIELDS = ('operation', 'stage', 'method', 'route', 'error_code', 'error_type')
_NUMERIC_FIELDS = ('status_code', 'exit_code', 'duration_ms', 'completed_outputs')
_CURRENT: ContextVar[dict[str, Any] | None] = ContextVar('operation_context', default=None)
_SINK: ContextVar[JsonlSink | None] = ContextVar('operation_sink', default=None)
_LOCK = threading.RLock()
_PROCESS_TOKEN = uuid.uuid4().hex[:8]
_LAST_WARNING = float('-inf')


def valid_id(value: object) -> str | None:
    """Reject URLs, control characters, whitespace and unbounded external IDs."""
    return value if isinstance(value, str) and _ID.fullmatch(value) else None


def new_id() -> str:
    return uuid.uuid4().hex


def current_context() -> dict[str, Any]:
    return dict(_CURRENT.get() or {})


def _safe_fields(fields: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name in _CONTEXT_FIELDS:
        value = fields.get(name)
        if name in ('room_id', 'job_id') and isinstance(value, int) and not isinstance(value, bool):
            value = str(value)
        if valid_id(value):
            result[name] = value
    for name in _LABEL_FIELDS:
        value = fields.get(name)
        if isinstance(value, str) and _LABEL.fullmatch(value):
            result[name] = value
    for name in _NUMERIC_FIELDS:
        value = fields.get(name)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and 0 <= value < 1e15:
            result[name] = round(value, 3)
    return result


class JsonlSink:
    """Daily per-process shards, bounded segments, one locked append per event.

    Processes never share a file, threads serialize through the process lock.
    Old logs are not deleted automatically; retention is an operator decision.
    """
    def __init__(self, directory: Path, max_bytes: int = 50 * 1024 * 1024) -> None:
        self.directory = Path(directory)
        if max_bytes < 1024:
            raise ValueError('Log segment must allow at least 1024 bytes')
        self.max_bytes = max_bytes
        self.part = 0

    def write(self, record: dict[str, Any]) -> bool:
        global _LAST_WARNING
        try:
            data = (json.dumps(record, ensure_ascii=True, allow_nan=False, separators=(',', ':')) + '\n').encode('utf-8')
            if len(data) > self.max_bytes:
                raise ValueError('Event exceeds segment size')
            with _LOCK:
                self.directory.mkdir(parents=True, exist_ok=True)
                day = datetime.now(timezone.utc).strftime('%Y-%m-%d')
                while True:
                    path = self.directory / f'{day}-{os.getpid()}-{_PROCESS_TOKEN}-{self.part:04d}.jsonl'
                    if not path.exists() or path.stat().st_size + len(data) <= self.max_bytes:
                        break
                    self.part += 1
                descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, 'O_BINARY', 0), 0o600)
                try:
                    if os.write(descriptor, data) != len(data):
                        raise OSError('Incomplete event append')
                finally:
                    os.close(descriptor)
            return True
        except Exception as exc:
            # Business result and original exception must survive sink failures.
            # Never emit exception text: OS/library errors can contain secrets.
            with _LOCK:
                if time.monotonic() - _LAST_WARNING >= 60:
                    _LAST_WARNING = time.monotonic()
                    try:
                        logging.getLogger('burnroom.operations').warning(
                            'operation_log_write_failed error_type=%s', type(exc).__name__)
                    except Exception:
                        pass
            return False


def default_sink() -> JsonlSink:
    return JsonlSink(Path(os.environ.get('OPERATION_LOG_ROOT', str(project_root() / 'data/logs/operations'))))


@contextmanager
def bind_context(*, sink: JsonlSink | None = None, **fields: Any) -> Iterator[dict[str, Any]]:
    context = {**current_context(), **_safe_fields(fields)}
    context.setdefault('trace_id', new_id())
    token = _CURRENT.set(context)
    sink_token = _SINK.set(sink or _SINK.get() or default_sink())
    try:
        yield context
    finally:
        _SINK.reset(sink_token)
        _CURRENT.reset(token)


def emit(event: str, **fields: Any) -> bool:
    if event not in ('start', 'success', 'failure', 'cancel', 'accepted', 'progress'):
        raise ValueError('Unsupported operation event')
    record = {'schema_version': 1, 'ts': datetime.now(timezone.utc).isoformat(),
              'event_id': new_id(), 'pid': os.getpid(), 'event': event,
              **_safe_fields({**current_context(), **fields})}
    record.setdefault('trace_id', new_id())
    return (_SINK.get() or default_sink()).write(record)


def mark_failure(error_code: str) -> None:
    """For existing handlers that retain failures in status files instead of raising."""
    context = _CURRENT.get()
    if context is not None and _LABEL.fullmatch(error_code):
        context['_failure_code'] = error_code


@contextmanager
def stage(operation: str, name: str, **fields: Any) -> Iterator[dict[str, Any]]:
    parent = current_context().get('span_id')
    with bind_context(operation=operation, stage=name, span_id=new_id(),
                      parent_span_id=parent, **fields) as context:
        started = time.perf_counter()
        emit('start')
        try:
            yield context
        except BaseException as exc:
            if isinstance(exc, SystemExit):
                code = exc.code if isinstance(exc.code, int) else 1
                event = 'success' if code == 0 else 'failure'
                emit(event, exit_code=code, error_type=type(exc).__name__ if code else '',
                     error_code='cli_rejected' if code else '', duration_ms=(time.perf_counter()-started)*1000)
            else:
                emit('cancel' if isinstance(exc, (KeyboardInterrupt, asyncio.CancelledError)) else 'failure',
                     error_type=type(exc).__name__, error_code='operation_failed',
                     duration_ms=(time.perf_counter()-started)*1000)
            raise
        else:
            exit_code = context.get('_failed_exit_code')
            failure = context.get('_failure_code') or ('cli_failed' if exit_code else '')
            emit('failure' if failure else 'success',
                 error_code=failure, exit_code=exit_code,
                 duration_ms=(time.perf_counter()-started)*1000)


def traced(operation: str, name: str) -> Callable:
    """Trace sync/async boundaries without logging raw arguments or results."""
    def decorate(function: Callable) -> Callable:
        @wraps(function)
        async def async_wrapped(*args: Any, **kwargs: Any) -> Any:
            with stage(operation, name):
                result = await function(*args, **kwargs)
                if isinstance(result, dict) and result.get('status') == 'failed':
                    mark_failure('business_failed')
                return result

        @wraps(function)
        def wrapped(*args: Any, **kwargs: Any) -> Any:
            with stage(operation, name):
                result = function(*args, **kwargs)
                if isinstance(result, dict) and result.get('status') == 'failed':
                    mark_failure('business_failed')
                return result
        # FastAPI resolves postponed annotations in the original module.
        target = async_wrapped if inspect.iscoroutinefunction(function) else wrapped
        target.__signature__ = inspect.signature(function, eval_str=True)
        return target
    return decorate


def cli_operation(operation: str) -> Callable:
    """A CLI span includes parsing failures; --help remains a side-effect-free read."""
    def decorate(function: Callable) -> Callable:
        @wraps(function)
        def wrapped(*args: Any, **kwargs: Any) -> Any:
            if any(value in ('--help', '-h') for value in sys.argv[1:]):
                return function(*args, **kwargs)
            with stage(operation, 'cli') as context:
                result = function(*args, **kwargs)
                # Existing catalog CLIs return 1 after their own error handling.
                if isinstance(result, int) and not isinstance(result, bool) and result != 0:
                    context['_failed_exit_code'] = result
                return result
        return wrapped
    return decorate


def child_environment() -> dict[str, str]:
    """Only correlation crosses the process boundary, never arbitrary payloads."""
    return {'BURNROOM_OPERATION_CONTEXT': json.dumps(_safe_fields(current_context()), separators=(',', ':'))}


@contextmanager
def inherited_context(sink: JsonlSink) -> Iterator[dict[str, Any]]:
    try:
        fields = json.loads(os.environ.get('BURNROOM_OPERATION_CONTEXT', '{}'))
        if not isinstance(fields, dict):
            fields = {}
    except (ValueError, TypeError):
        fields = {}
    with bind_context(sink=sink, **_safe_fields(fields)) as context:
        yield context
