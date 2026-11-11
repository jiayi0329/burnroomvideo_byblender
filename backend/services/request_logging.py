"""Pure ASGI request tracing, including validation/404/500; no body inspection."""
from __future__ import annotations

import asyncio
import time
from typing import Any

from render_engine.jobs.operation_logging import bind_context, emit, new_id, valid_id


class OperationLoggingMiddleware:
    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope['type'] != 'http':
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get('headers', []))
        raw_trace = headers.get(b'x-trace-id', b'')
        trace = valid_id(raw_trace.decode('ascii', errors='replace')) or new_id()
        request_id = new_id()  # Always unique, including polling and untrusted supplied IDs.
        status = 500
        response_started = False
        response_finished = False
        exception_fields: dict[str, Any] = {}
        started = time.perf_counter()
        fields: dict[str, Any] = {'method': scope.get('method', ''), 'operation': 'http.request',
                                  'stage': 'request', 'span_id': new_id()}
        with bind_context(trace_id=trace, request_id=request_id, **fields):
            scope.setdefault('state', {}).update(trace_id=trace, request_id=request_id)
            emit('start')

            async def traced_send(message: dict) -> None:
                nonlocal status, response_started, response_finished
                if message['type'] == 'http.response.start':
                    response_started = True
                    status = message['status']
                    # Do not trust caller-provided duplicate response IDs.
                    outgoing = [(k, v) for k, v in message.get('headers', [])
                                if k.lower() not in (b'x-trace-id', b'x-request-id')]
                    message = {**message, 'headers': outgoing + [
                        (b'x-trace-id', trace.encode('ascii')), (b'x-request-id', request_id.encode('ascii'))]}
                await send(message)
                if message['type'] == 'http.response.body' and not message.get('more_body', False):
                    response_finished = True
                    emit('failure' if status >= 400 else 'success', **details(),
                         **(exception_fields or ({'error_code':'request_rejected'} if status >= 400 else {})))

            def details() -> dict:
                # Unmatched paths are not logged: they may contain credentials.
                route = getattr(scope.get('route'), 'path', 'unmatched')
                params = scope.get('path_params', {})
                return {'route': route, 'status_code': status,
                        'scene_code': params.get('scene_code'), 'room_id': params.get('room_id'),
                        'duration_ms': (time.perf_counter()-started)*1000}

            try:
                await self.app(scope, receive, traced_send)
            except BaseException as exc:
                exception_fields.update(error_type=type(exc).__name__, error_code='request_exception')
                if isinstance(exc, Exception) and not response_started:
                    await traced_send({'type': 'http.response.start', 'status': 500,
                                       'headers': [(b'content-type', b'text/plain; charset=utf-8')]})
                    await traced_send({'type': 'http.response.body', 'body': b'Internal Server Error'})
                else:
                    emit('cancel' if isinstance(exc, asyncio.CancelledError) else 'failure',
                         **details(), **exception_fields,
                         operation='http.background' if response_finished else 'http.request',
                         stage='background_after_response' if response_finished else 'request')
                raise
            else:
                if not response_finished:
                    emit('failure', **details(), error_code='incomplete_response')
