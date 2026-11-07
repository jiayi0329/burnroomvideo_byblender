"""PRD 2.3 / architecture 3.3: NVIDIA graphics injection and fail-closed final jobs.

No Docker, Blender or GPU execution. Worker guard is executed from its real AST
with a synthetic context; all evidence files live in TemporaryDirectory.
"""
import ast
from contextlib import redirect_stdout
import io
from pathlib import Path
import tempfile
import unittest

from app import room_animation_job as jobs
from test import test_room_animation as fixtures

ROOT=Path(__file__).resolve().parents[1]
NVIDIA={'available':True,'vendor':'NVIDIA Corporation','renderer':'NVIDIA L20/PCIe/SSE2',
        'device_type':'NVIDIA','software_rendering_suspected':False}


class GraphicsGuard(unittest.TestCase):
    def test_accepts_actual_nvidia_context(self) -> None:
        jobs.verify_nvidia_renderer(NVIDIA)

    def test_rejects_software_unknown_and_non_nvidia(self) -> None:
        for info in ({}, {'available':False},
                     {**NVIDIA,'device_type':'SOFTWARE'},
                     {**NVIDIA,'software_rendering_suspected':True},
                     {**NVIDIA,'renderer':'llvmpipe'},
                     {**NVIDIA,'renderer':'softpipe'},
                     {**NVIDIA,'vendor':'Mesa','renderer':'Intel GPU'}):
            with self.subTest(info=info),self.assertRaisesRegex(RuntimeError,'NVIDIA graphics renderer required'):
                jobs.verify_nvidia_renderer(info)

    def worker_guard(self,root: Path,info: dict) -> dict:
        tree=ast.parse((ROOT/'app/F8_room_animation.py').read_text(encoding='utf-8'))
        run=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='run')
        guard=next(n for n in ast.walk(run) if isinstance(n,ast.If) and
            any(isinstance(call,ast.Call) and isinstance(call.func,ast.Name) and call.func.id=='renderer_info'
                for call in ast.walk(n)) and isinstance(n.test,ast.Compare) and
            isinstance(n.test.left,ast.Constant) and n.test.left.value=='renderer')
        scope={'timings':{},'manifest':{},'work':root,'job':root,
               'renderer_info':lambda:info,'write_json':jobs.write_json,
               'verify_nvidia_renderer':jobs.verify_nvidia_renderer,
               'spec':{'animation':{'require_nvidia_graphics':True}}}
        with redirect_stdout(io.StringIO()):
            exec(compile(ast.Module(body=[guard],type_ignores=[]),'worker GPU guard','exec'),scope)
        return scope

    def test_worker_stops_after_first_context_and_retains_failure_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); info={**NVIDIA,'renderer':'llvmpipe','device_type':'SOFTWARE'}
            with self.assertRaisesRegex(RuntimeError,'NVIDIA graphics renderer required'):
                self.worker_guard(root,info)
            self.assertEqual(jobs.read_json(root/'renderer.json'),info)
            self.assertEqual(jobs.read_json(root/'render_manifest.json')['renderer'],info)
        source=(ROOT/'app/F8_room_animation.py').read_text(encoding='utf-8')
        self.assertLess(source.index("verify_nvidia_renderer(timings['renderer'])"),source.index('temp.replace(target)'))

    def test_worker_records_actual_nvidia_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            scope=self.worker_guard(Path(directory),NVIDIA)
            self.assertEqual(scope['timings']['renderer'],NVIDIA)

    def test_all_final_specs_require_gpu_and_old_cpu_spec_cannot_resume(self) -> None:
        fixture=fixtures.AnimationJobs(); fixture.setUp(); self.addCleanup(fixture.doCleanups)
        for preset in ('test','final'):
            spec=jobs.build_spec(fixture.inputs,'final',preset)
            self.assertTrue(spec['animation']['require_nvidia_graphics'])
        self.assertNotIn('require_nvidia_graphics',fixture.spec['animation'])
        spec=jobs.build_spec(fixture.inputs,'final','final',direct_final=True)
        job=jobs.create_job(fixture.job_root,spec)
        old=jobs.read_json(job/'config_snapshot.json'); del old['animation']['require_nvidia_graphics']
        jobs.write_json(job/'config_snapshot.json',old)
        with self.assertRaisesRegex(ValueError,'differs'):jobs.check_resume(job,spec)

    def test_production_and_overlay_request_graphics_without_other_service_changes(self) -> None:
        prod=(ROOT/'release/docker-compose.prod.yml').read_text(encoding='utf-8')
        self.assertIn('NVIDIA_DRIVER_CAPABILITIES=compute,utility,graphics',prod)
        self.assertIn('NVIDIA_VISIBLE_DEVICES=all',prod)
        overlay=(ROOT/'release/docker-compose.gpu.yml').read_text(encoding='utf-8')
        self.assertIn('NVIDIA_DRIVER_CAPABILITIES: compute,utility,graphics',overlay)
        self.assertIn('NVIDIA_VISIBLE_DEVICES: all',overlay)
        for key in ('volumes:','ports:','image:','env_file:','minio-oss:','postgres:'):
            self.assertNotIn(key,overlay)

    def test_nvidia_runtime_is_explicit_and_scoped_to_app_server(self) -> None:
        for filename in ('docker-compose.prod.yml','docker-compose.gpu.yml'):
            source=(ROOT/'release'/filename).read_text(encoding='utf-8')
            self.assertEqual(source.count('runtime: nvidia'),1)
            app=source.split('  app-server:',1)[1].split('\n  minio-oss:',1)[0]
            self.assertIn('    runtime: nvidia',app)

    def test_gpu_requests_are_cleared_while_runtime_environment_keeps_devices(self) -> None:
        prod=(ROOT/'release/docker-compose.prod.yml').read_text(encoding='utf-8')
        overlay=(ROOT/'release/docker-compose.gpu.yml').read_text(encoding='utf-8')
        active_prod=[line.strip() for line in prod.splitlines() if line.strip() and not line.lstrip().startswith('#')]
        self.assertFalse(any(line.startswith('gpus:') for line in active_prod))
        self.assertIn('    gpus: !reset []',overlay)
        self.assertIn('    runtime: nvidia',overlay)
        self.assertIn('NVIDIA_VISIBLE_DEVICES: all',overlay)
        self.assertIn('NVIDIA_DRIVER_CAPABILITIES: compute,utility,graphics',overlay)


if __name__=='__main__':unittest.main()
