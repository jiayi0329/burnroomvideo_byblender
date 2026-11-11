"""PRD/OBSERVABILITY: Room8 launch/worker correlation without real rendering.

Reuses existing synthetic asset/PNG/process fixtures. No GPU, API, DB or Docker.
"""
import argparse
import ast
from contextlib import contextmanager, redirect_stdout
import io
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from render_engine.jobs import operation_logging as log
from render_engine.jobs import run_room_animation as launcher
from render_engine.jobs import room_animation_job as jobs
from tests.engine import test_room_animation as fixtures


def events(root: Path) -> list[dict]:
    return [json.loads(line) for file in root.rglob('operations/*.jsonl')
            for line in file.read_text(encoding='utf-8').splitlines()]


@contextmanager
def lock(root: Path):
    yield 5


class RoomOperationLogging(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = fixtures.AnimationJobs(methodName='runTest')
        self.fixture.setUp(); self.addCleanup(self.fixture.doCleanups)
        self.f = self.fixture
        self.patch = patch.dict(os.environ, {'OPERATION_LOG_ROOT':str(self.f.root/'service/operations')})
        self.patch.start(); self.addCleanup(self.patch.stop)
        self.args = argparse.Namespace(asset=self.f.asset, points=self.f.points, config=self.f.config,
            stage='short', preset='test', wall_height=1.1, drop_component=[], approval=None, resume=None)

    def launch(self, code: int = 0):
        process, run = self.f.launcher_fixture(code)
        with patch.object(launcher.shutil,'which',return_value='fixture'), \
             patch.object(launcher,'preflight',return_value=self.f.inputs), \
             patch.object(launcher,'gpu_lock',lock), patch.object(launcher,'busy_processes',return_value={}), \
             patch.object(launcher,'monitor_gpu'), patch.object(launcher.subprocess,'Popen',side_effect=process) as child, \
             patch.object(launcher.subprocess,'run',side_effect=run), redirect_stdout(io.StringIO()):
            job = launcher.execute(self.args)
        return job, child

    def test_job_events_isolated_correlated_and_child_env_preserves_gpu_lock(self) -> None:
        with log.bind_context(trace_id='reviewed-action', request_id='request-1'):
            job, child = self.launch()
        records = events(job)
        self.assertTrue(records)
        self.assertEqual({r['trace_id'] for r in records}, {'reviewed-action'})
        self.assertEqual({r['job_id'] for r in records}, {job.name})
        self.assertEqual({r['request_id'] for r in records}, {'request-1'})
        stages = {r['stage'] for r in records}
        self.assertTrue({'job_attempt','blender_launch','video_encode','video_probe','video_decode'}.issubset(stages))
        env = child.call_args.kwargs['env']
        inherited = json.loads(env['BURNROOM_OPERATION_CONTEXT'])
        self.assertEqual(inherited['trace_id'], 'reviewed-action')
        self.assertEqual(inherited['job_id'], job.name)
        self.assertEqual(env['ROOM_ANIMATION_LOCK_FD'],'5')
        self.assertEqual(jobs.read_json(job/'status.json')['state'],'awaiting_visual_review')
        self.assertFalse((job/'fire_final.mp4').exists())
        self.assertEqual(jobs.read_json(job/'config_snapshot.json')['inputs']['timeline'], self.f.inputs['timeline'])

    def test_worker_failure_retains_frames_and_records_failed_attempt(self) -> None:
        with self.assertRaisesRegex(RuntimeError,'Blender exited'):
            self.launch(1)
        job = next(self.f.job_root.iterdir())
        terminal = next(r for r in events(job) if r['stage']=='job_attempt' and r['event']=='failure')
        self.assertGreaterEqual(terminal['duration_ms'],0)
        self.assertEqual(terminal['error_type'],'RuntimeError')
        self.assertEqual(jobs.read_json(job/'status.json')['state'],'failed')
        self.assertTrue((job/'frames/frame_000001.png').is_file())
        self.assertNotIn('Blender exited', json.dumps(events(job)))

    def test_operation_sink_failure_does_not_erase_video_or_change_review_state(self) -> None:
        with patch.object(log.JsonlSink,'write',return_value=False):
            job, _ = self.launch()
        self.assertTrue((job/'fire_short.mp4').is_file())
        self.assertEqual(jobs.read_json(job/'status.json')['state'],'awaiting_visual_review')
        self.assertTrue(jobs.read_json(job/'render_manifest.json')['technical_complete'])

    def test_two_jobs_have_separate_logs_and_unchanged_first_outputs(self) -> None:
        first, _ = self.launch()
        snapshot = {str(path.relative_to(first)):path.read_bytes() for path in first.rglob('*') if path.is_file()}
        second, _ = self.launch()
        self.assertNotEqual(first, second)
        self.assertEqual({r['job_id'] for r in events(first)},{first.name})
        self.assertEqual({r['job_id'] for r in events(second)},{second.name})
        for name, data in snapshot.items(): self.assertEqual((first/name).read_bytes(),data)

    def test_missing_tools_rejected_with_timing_without_job_or_child(self) -> None:
        with patch.object(launcher.shutil,'which',return_value=None), \
                patch.object(launcher.subprocess,'Popen') as child:
            with self.assertRaisesRegex(RuntimeError,'Required executable'):
                launcher.execute(self.args)
        child.assert_not_called()
        self.assertFalse(self.f.job_root.exists())
        terminal = events(self.f.root)[-1]
        self.assertEqual(terminal['event'],'failure')
        self.assertGreaterEqual(terminal['duration_ms'],0)

    def test_worker_entry_inherits_trace_and_parent_without_importing_blender(self) -> None:
        job = self.f.new_job(); attempt = 'synthetic-attempt'
        work = job/'attempts'/attempt; work.mkdir(parents=True)
        source = Path(launcher.__file__).resolve().parents[1]/'blender/F8_room_animation.py'
        main = next(node for node in ast.parse(source.read_text()).body
                    if isinstance(node,ast.FunctionDef) and node.name=='main')
        def synthetic_run(*args):
            with log.stage('room.animation','asset_and_effects_prepare'): pass
        scope = {'argparse':argparse,'Path':Path,'sys':sys,'confined':jobs.confined,
                 'JsonlSink':log.JsonlSink,'inherited_context':log.inherited_context,
                 'stage':log.stage,'run':synthetic_run}
        exec(compile(ast.Module(body=[main],type_ignores=[]),'worker-entry-stand-in','exec'),scope)
        with log.bind_context(trace_id='cli-trace', job_id=job.name, span_id='launch-span'):
            environment = log.child_environment()
        with patch.dict(os.environ,environment), patch('sys.argv',[
                'blender','--','--job',str(job),'--attempt',attempt,'--launch-monotonic','1']):
            scope['main']()
        records = events(job)
        self.assertEqual({r['trace_id'] for r in records},{'cli-trace'})
        self.assertEqual(records[0]['parent_span_id'],'launch-span')
        self.assertEqual(records[-1]['stage'],'worker')
        self.assertEqual(records[-1]['event'],'success')


if __name__ == '__main__':
    unittest.main()
