"""PRD operation tracing / OBSERVABILITY / ARCHITECTURE: offline evidence only.

Temporary JSONL, in-process ASGI requests and synthetic CLI failures. Never
contacts real API/DB/MinIO or starts Blender/Docker/a server.
"""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stderr, redirect_stdout
from contextvars import copy_context
import io
import json
import multiprocessing
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.testclient import TestClient

from backend.cli import check_catalog, log_timeline
from backend.services.request_logging import OperationLoggingMiddleware
from backend.services import request_logging
from render_engine.jobs import operation_logging as log


def rows(directory: Path) -> list[dict]:
    return [json.loads(line) for file in directory.rglob('*.jsonl')
            for line in file.read_text(encoding='utf-8').splitlines()]


def process_writer(directory: str) -> None:
    with log.bind_context(sink=log.JsonlSink(Path(directory)), trace_id='process-trace'):
        for _ in range(30):
            log.emit('success', operation='synthetic', stage='write')


class EventLogging(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.environment = patch.dict(os.environ, {'OPERATION_LOG_ROOT': str(self.root)})
        self.environment.start(); self.addCleanup(self.environment.stop)

    def test_nested_spans_share_trace_have_parents_and_monotonic_duration(self) -> None:
        with log.stage('test', 'cli'):
            with log.stage('test', 'read'):
                pass
        events = rows(self.root)
        outer, inner, finished, done = events
        self.assertEqual(len({r['trace_id'] for r in events}), 1)
        self.assertEqual(inner['parent_span_id'], outer['span_id'])
        self.assertEqual(finished['span_id'], inner['span_id'])
        self.assertGreaterEqual(done['duration_ms'], finished['duration_ms'])
        self.assertIsNone(log.current_context().get('trace_id'))

    def test_redacts_unknown_fields_raw_error_messages_headers_queries_and_urls(self) -> None:
        secret = 'PRIVATE-TOKEN'
        with log.bind_context(trace_id='safe-trace'):
            log.emit('failure', operation='test', stage='read', password=secret,
                     authorization=secret, payload={'appkey': secret},
                     url='https://host/asset?X-Amz-Signature='+secret,
                     error_code='https://host/?'+secret, error_type='ValueError\n'+secret,
                     scene_code='unsafe\n'+secret)
        content = next(self.root.glob('*.jsonl')).read_text()
        self.assertNotIn(secret, content)
        self.assertNotIn('authorization', content)
        self.assertEqual(rows(self.root)[0]['trace_id'], 'safe-trace')

    def test_failure_and_cancel_rethrow_original_exceptions_without_messages(self) -> None:
        for exception in (ValueError('secret-value'), KeyboardInterrupt()):
            with self.assertRaises(type(exception)):
                with log.stage('test', 'failure'):
                    raise exception
        events = rows(self.root)
        self.assertEqual([r['event'] for r in events], ['start', 'failure', 'start', 'cancel'])
        self.assertNotIn('secret-value', json.dumps(events))
        self.assertTrue(all('duration_ms' in r for r in events if r['event'] != 'start'))

    def test_async_stage_awaits_completion_and_propagates_cancellation(self) -> None:
        @log.traced('test','async_task')
        async def work(cancel: bool = False) -> dict:
            if cancel: raise asyncio.CancelledError()
            return {'status':'failed'}
        self.assertEqual(asyncio.run(work()),{'status':'failed'})
        with self.assertRaises(asyncio.CancelledError): asyncio.run(work(True))
        self.assertEqual([r['event'] for r in rows(self.root)],['start','failure','start','cancel'])

    def test_sink_failure_warns_safely_but_preserves_success_and_original_failure(self) -> None:
        with patch.object(Path, 'mkdir', side_effect=PermissionError('secret-path')), \
             patch.object(log, '_LAST_WARNING', float('-inf')), \
             self.assertLogs('burnroom.operations', level='WARNING') as capture:
            with log.stage('test', 'success'):
                result = 17
            self.assertEqual(result, 17)
            with self.assertRaisesRegex(RuntimeError, 'original'):
                with log.stage('test', 'failure'):
                    raise RuntimeError('original')
        self.assertEqual(len(capture.output), 1)
        self.assertNotIn('secret-path', capture.output[0])
        self.assertIn('PermissionError', capture.output[0])

    def test_threaded_append_is_valid_and_rotates_without_overwrite(self) -> None:
        sink = log.JsonlSink(self.root, max_bytes=2048)
        def write(index: int) -> None:
            with log.bind_context(sink=sink, trace_id=f'thread-{index}'):
                log.emit('success', operation='test', stage='thread')
        with ThreadPoolExecutor(max_workers=8) as executor:
            list(executor.map(write, range(100)))
        self.assertEqual(len(rows(self.root)), 100)
        self.assertEqual(len({r['event_id'] for r in rows(self.root)}), 100)
        self.assertGreater(len(list(self.root.glob('*.jsonl'))), 1)
        self.assertTrue(all(file.stat().st_size <= 2048 for file in self.root.glob('*.jsonl')))

    def test_processes_use_separate_files_and_keep_all_events(self) -> None:
        context = multiprocessing.get_context('spawn')
        workers = [context.Process(target=process_writer, args=(str(self.root),)) for _ in range(2)]
        for worker in workers: worker.start()
        for worker in workers:
            worker.join(20)
            if worker.is_alive():
                worker.terminate(); worker.join()
                self.fail('Synthetic log writer did not exit')
            self.assertEqual(worker.exitcode, 0)
        self.assertEqual(len(rows(self.root)), 60)
        self.assertEqual(len({r['pid'] for r in rows(self.root)}), 2)

    def test_subprocess_roundtrip_carries_trace_job_and_parent_span(self) -> None:
        with log.bind_context(trace_id='parent-trace', job_id='job-1', attempt_id='attempt-1'):
            with log.stage('test', 'launch'):
                parent = log.current_context()
                environment = {**os.environ, **log.child_environment()}
        code = '''from pathlib import Path
from render_engine.jobs.operation_logging import inherited_context,default_sink,stage
with inherited_context(default_sink()):
    with stage('test','worker'): pass
'''
        subprocess.run([sys.executable, '-B', '-c', code], env=environment, check=True,
                       capture_output=True, timeout=15)
        worker = next(r for r in rows(self.root) if r.get('stage') == 'worker')
        self.assertEqual(worker['trace_id'], parent['trace_id'])
        self.assertEqual(worker['job_id'], 'job-1')
        self.assertEqual(worker['parent_span_id'], parent['span_id'])

    def test_cli_validation_rejection_and_returned_failure_have_no_success_end(self) -> None:
        with patch('sys.argv', ['check', '--invalid']), redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit): check_catalog.main()
        events = rows(self.root)
        self.assertEqual([r['event'] for r in events], ['start', 'failure'])
        self.assertEqual(events[-1]['exit_code'], 2)
        with patch('sys.argv', ['check']), patch.object(check_catalog, 'check_catalog',
                side_effect=RuntimeError('password=secret')), redirect_stdout(io.StringIO()):
            self.assertEqual(check_catalog.main(), 1)
        self.assertEqual([r['event'] for r in rows(self.root)][-2:], ['start', 'failure'])
        self.assertNotIn('password', json.dumps(rows(self.root)))

    def test_cli_success_is_print_compatible_and_help_does_not_write(self) -> None:
        with patch('sys.argv', ['check', '--help']), redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit) as exit:
                check_catalog.main()
        self.assertEqual(exit.exception.code, 0)
        self.assertEqual(list(self.root.iterdir()), [])
        with patch('sys.argv', ['check']), patch.object(check_catalog, 'check_catalog',
                return_value={'status':'ok', 'tables_checked':8}), redirect_stdout(io.StringIO()) as output:
            self.assertEqual(check_catalog.main(), 0)
        self.assertEqual(json.loads(output.getvalue())['tables_checked'], 8)
        self.assertEqual([r['event'] for r in rows(self.root)], ['start', 'success'])

    def test_timeline_is_readonly_sanitized_handles_truncated_tail_and_refuses_overwrite(self) -> None:
        with log.bind_context(trace_id='one-trace'):
            with log.stage('test', 'cli'): pass
        file = next(self.root.glob('*.jsonl'))
        with file.open('a') as stream: stream.write('{"broken":')
        before = file.read_bytes()
        report = log_timeline.read_events(self.root, trace_id='one-trace')
        self.assertEqual(len(report['events']), 2)
        self.assertEqual(report['malformed_lines'], 1)
        self.assertEqual(file.read_bytes(), before)
        self.assertIn('Operation timeline', log_timeline.markdown(report))
        output = self.root/'timeline.md'; output.write_text('original')
        with patch('sys.argv', ['timeline', '--logs', str(self.root), '--trace-id', 'one-trace', '--output', str(output)]), \
                redirect_stdout(io.StringIO()):
            self.assertEqual(log_timeline.main(), 1)
        self.assertEqual(output.read_text(), 'original')
        self.assertTrue(log_timeline.read_events(self.root, trace_id='one-trace', limit=1)['truncated'])


class RequestLogging(unittest.TestCase):
    def setUp(self) -> None:
        EventLogging.setUp(self)
        self.app = FastAPI()
        self.app.add_middleware(OperationLoggingMiddleware)

        @self.app.get('/rooms/{room_id}')
        def room(room_id: int) -> dict:
            with log.stage('test', 'database_read'):
                return {'room_id':room_id}

        @self.app.get('/error')
        def error() -> None:
            raise RuntimeError('private-password-and-url')

        @self.app.get('/unavailable')
        def unavailable() -> None:
            raise HTTPException(503, 'not available')

        @self.app.get('/background')
        def background() -> dict:
            context = copy_context()
            with ThreadPoolExecutor(max_workers=1) as pool:
                def worker() -> None:
                    with log.stage('test', 'background'): pass
                pool.submit(context.run, worker).result()
            return {'accepted':True}
        self.client = TestClient(self.app, raise_server_exceptions=False)

    def test_http_success_returns_ids_and_records_template_without_query_or_body(self) -> None:
        response = self.client.get('/rooms/8?appkey=PRIVATE-QUERY', headers={
            'X-Trace-ID':'operation-1', 'Authorization':'PRIVATE-AUTH', 'X-Request-ID':'not-trusted'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['x-trace-id'], 'operation-1')
        self.assertNotEqual(response.headers['x-request-id'], 'not-trusted')
        events = rows(self.root)
        self.assertEqual({r['trace_id'] for r in events}, {'operation-1'})
        self.assertEqual(events[-1]['route'], '/rooms/{room_id}')
        self.assertEqual(events[-1]['room_id'], '8')
        self.assertNotIn('PRIVATE', json.dumps(events))
        self.assertGreaterEqual(events[-1]['duration_ms'], 0)

    def test_validation_404_503_and_500_logged_and_ids_returned(self) -> None:
        for path, expected in (('/rooms/no-int', 422), ('/private-unmatched-path',404),
                               ('/unavailable',503),('/error',500)):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, expected)
                self.assertTrue(log.valid_id(response.headers['x-trace-id']))
                terminal = next(r for r in reversed(rows(self.root)) if r.get('operation')=='http.request')
                self.assertEqual(terminal['event'], 'failure')
                self.assertEqual(terminal['status_code'], expected)
        self.assertNotIn('private-password', json.dumps(rows(self.root)))
        self.assertNotIn('private-unmatched-path', json.dumps(rows(self.root)))

    def test_invalid_trace_replaced_and_each_poll_has_unique_request(self) -> None:
        first = self.client.get('/rooms/8', headers={'X-Trace-ID':'https://bad/?secret=1'})
        second = self.client.get('/rooms/8', headers={'X-Trace-ID':first.headers['x-trace-id']})
        self.assertNotIn('https', first.headers['x-trace-id'])
        self.assertEqual(first.headers['x-trace-id'],second.headers['x-trace-id'])
        self.assertNotEqual(first.headers['x-request-id'],second.headers['x-request-id'])

    def test_parallel_requests_do_not_mix_contexts(self) -> None:
        def get(index: int) -> str:
            return self.client.get('/rooms/8', headers={'X-Trace-ID':f'parallel-{index}'}).headers['x-request-id']
        with ThreadPoolExecutor(max_workers=4) as pool:
            ids = list(pool.map(get, range(8)))
        self.assertEqual(len(set(ids)), 8)
        for request_id in ids:
            events = [r for r in rows(self.root) if r.get('request_id')==request_id]
            self.assertEqual(len(events), 4)
            self.assertEqual(len({r['trace_id'] for r in events}), 1)
            self.assertEqual(events[1]['parent_span_id'],events[0]['span_id'])

    def test_background_thread_retains_request_and_trace_context(self) -> None:
        response = self.client.get('/background')
        event = next(r for r in rows(self.root) if r.get('stage')=='background')
        self.assertEqual(event['trace_id'],response.headers['x-trace-id'])
        self.assertEqual(event['request_id'],response.headers['x-request-id'])

    def test_after_response_task_keeps_trace_without_inflating_http_duration(self) -> None:
        clock = [100.0]
        @self.app.get('/after-response')
        def after_response(background: BackgroundTasks) -> dict:
            def work() -> None:
                clock[0] = 109.0
                with log.stage('test','background_after_response'): pass
            background.add_task(work)
            clock[0] = 100.25
            return {'accepted':True}
        with patch.object(request_logging, 'time', SimpleNamespace(perf_counter=lambda:clock[0])):
            response = self.client.get('/after-response')
        records = rows(self.root)
        http_end = next(r for r in records if r.get('operation')=='http.request' and r['event']=='success')
        self.assertEqual(http_end['duration_ms'],250)
        task = next(r for r in records if r.get('stage')=='background_after_response')
        self.assertEqual(task['trace_id'],response.headers['x-trace-id'])
        self.assertEqual(task['request_id'],http_end['request_id'])

    def test_timeline_request_counts_do_not_treat_missing_requests_as_zero_latency(self) -> None:
        trace = 'summary-trace'
        self.client.get('/rooms/8',headers={'X-Trace-ID':trace})
        self.client.get('/unavailable',headers={'X-Trace-ID':trace})
        summary = log_timeline.read_events(self.root,trace_id=trace)['http_summary']
        self.assertEqual(summary['completed_requests'],2)
        self.assertEqual(summary['failure_rate'],.5)
        self.assertGreaterEqual(summary['p90_ms'],0)
        missing = log_timeline.read_events(self.root,trace_id='missing-trace')['http_summary']
        self.assertIsNone(missing['mean_ms'])
        self.assertIsNone(missing['failure_rate'])

    def test_actual_app_registers_middleware_without_changing_health_or_catalog(self) -> None:
        from backend.api.main import app
        client = TestClient(app)
        response = client.get('/')
        self.assertEqual(response.json()['status'], 'Backend is running!')
        self.assertIn('x-trace-id', response.headers)
        with patch('backend.api.room_api.query', return_value=[]):
            self.assertEqual(client.get('/api/catalog/scenes/synthetic/rooms').status_code,404)

    def test_streaming_passes_messages_and_disconnect_is_cancel(self) -> None:
        async def synthetic(scope, receive, send):
            await send({'type':'http.response.start','status':200,'headers':[]})
            await send({'type':'http.response.body','body':b'a','more_body':True})
            await send({'type':'http.response.body','body':b'b','more_body':False})
        messages=[]
        async def send(message): messages.append(message)
        asyncio.run(OperationLoggingMiddleware(synthetic)({'type':'http','method':'GET'}, None, send))
        self.assertEqual([r['body'] for r in messages if 'body' in r], [b'a',b'b'])
        async def cancelled(scope, receive, send): raise asyncio.CancelledError()
        with self.assertRaises(asyncio.CancelledError):
            asyncio.run(OperationLoggingMiddleware(cancelled)({'type':'http','method':'GET'}, None, send))
        self.assertEqual(rows(self.root)[-1]['event'],'cancel')


if __name__ == '__main__':
    unittest.main()
