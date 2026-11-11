"""PRD engineering baseline; ARCHITECTURE 2.2/2.3; directory batch 4.

Offline checks of installed Room8 packages, compatibility, source guards and
presets. Temporary PowerShell/tar packages and Blender/process stand-ins only;
no real Blender, rendering, Docker, network, database or production writes.
Run: python -B -m unittest tests.engine.test_engine_migration -v
"""
import ast
from contextlib import contextmanager
from copy import deepcopy
import importlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

from render_engine import paths
from render_engine.jobs import room_animation_job as jobs
from render_engine.jobs import run_room_animation as launcher
from tests.deploy import test_release_safety as release
from tests.engine import test_room_animation as animations

ROOT = Path(__file__).resolve().parents[2]
PURE = {name:group for name,group in paths.MODULE_LOCATIONS.items() if group!='blender' and name!='F8_blender_render'}


def python(code: str, working: Path, root: Path = ROOT) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable,'-B','-c',code],cwd=working,
        env={**os.environ,'PYTHONPATH':str(root)},text=True,capture_output=True,timeout=20,check=True)


class Compatibility(unittest.TestCase):
    def test_canonical_pure_modules_import_and_launcher_patching_works(self) -> None:
        for name,group in PURE.items():
            module=importlib.import_module('render_engine.'+group+'.'+name)
            self.assertEqual(Path(module.__file__).resolve(),ROOT/'render_engine'/group/(name+'.py'))
        with patch.object(launcher,'execute') as execute, patch('sys.argv',['launcher','--asset','unused','--points','unused']):
            launcher.main()
        self.assertEqual(execute.call_args.args[0].config,paths.default_config())
        self.assertEqual(execute.call_args.args[0].camera_mode,'overview')

    def test_pure_packages_and_old_shims_import_without_bpy_backend_or_diagnostics(self) -> None:
        code=f'''import importlib,json,sys
mapping={PURE!r}
for name,group in mapping.items():
    importlib.import_module('render_engine.'+group+'.'+name)
for name in sys.modules:
    assert not name.startswith(('bpy','psycopg','fastapi','tools.diagnostics','backend.api.main','backend.adapters.postgres.database','backend.cli.import_rooms')),name
print('isolated',flush=True)
'''
        with tempfile.TemporaryDirectory() as directory:
            self.assertIn('isolated',python(code,Path(directory)).stdout)
            self.assertEqual(list(Path(directory).iterdir()),[])

    def test_legacy_and_new_cli_help_work_outside_project(self) -> None:
        entries=[['-m','render_engine.jobs.run_room_animation'],['-m','render_engine.jobs.run_room_animation'],
            [str(ROOT/'render_engine/jobs/run_room_animation.py')], [str(ROOT/'render_engine/jobs/run_room_animation.py')],
            ['-m','render_engine.geometry.prepare_room_candidate'],['-m','render_engine.geometry.prepare_room_candidate'],
            [str(ROOT/'render_engine/geometry/prepare_room_candidate.py')], [str(ROOT/'render_engine/geometry/prepare_room_candidate.py')]]
        with tempfile.TemporaryDirectory() as directory:
            for entry in entries:
                with self.subTest(entry=entry):
                    result=subprocess.run([sys.executable,'-B',*entry,'--help'],cwd=directory,
                        env={**os.environ,'PYTHONPATH':str(ROOT)},text=True,capture_output=True,timeout=15)
                    self.assertEqual(result.returncode,0,result.stderr)
                    self.assertIn('--asset' if 'animation' in str(entry) else '--inspection',result.stdout)
            self.assertEqual(list(Path(directory).iterdir()),[])

    def test_all_blender_paths_import_identically_and_cli_help_does_not_render(self) -> None:
        code='''import importlib,runpy,sys
from pathlib import Path
from types import SimpleNamespace
sys.modules['bpy']=SimpleNamespace()
sys.modules['mathutils']=SimpleNamespace(Vector=list)
root=Path(sys.path[0])
'''+f'root=Path({str(ROOT)!r})\n'+'''
for name in ('F8_prepare_room_asset','F8_room_demo','F8_room_animation','F8_room_helpers','F8_room_fire_style'):
    module=importlib.import_module('render_engine.blender.'+name)
    assert Path(module.__file__).resolve()==root/'render_engine/blender'/(name+'.py')
for name in ('F8_prepare_room_asset','F8_room_demo','F8_room_animation'):
    for folder in ('render_engine/blender',):
        sys.argv=['blender','--','--help']
        try: runpy.run_path(str(root/folder/(name+'.py')),run_name='__main__')
        except SystemExit as exc: assert exc.code==0,(name,exc.code)
print('Blender entry import/help stand-ins passed',flush=True)
'''
        with tempfile.TemporaryDirectory() as directory:
            self.assertIn('stand-ins passed',python(code,Path(directory)).stdout)
            self.assertEqual(list(Path(directory).iterdir()),[])

    def test_only_canonical_presets_exist_and_default_matches_approved_style(self) -> None:
        for revision in (1,2,3):
            file=ROOT/f'configs/render/room_fire_round{revision}.json'
            self.assertTrue(file.is_file())
            self.assertFalse((ROOT/f'app/room_fire_round{revision}.json').exists())
        self.assertEqual(jobs.fingerprint(jobs.read_json(paths.default_config())),jobs.APPROVED_STYLE_FINGERPRINT)

    def test_engine_never_imports_app_backend_diagnostics_or_legacy(self) -> None:
        for file in (ROOT/'render_engine').rglob('*.py'):
            tree=ast.parse(file.read_text(encoding='utf-8'))
            for node in ast.walk(tree):
                modules=([node.module or ''] if isinstance(node,ast.ImportFrom) else
                         [a.name for a in node.names] if isinstance(node,ast.Import) else [])
                for module in modules:
                    self.assertFalse(module.startswith(('app','tools','fastapi','psycopg')),str(file)+': '+module)
                    if file.parent.name not in ('blender','legacy'):self.assertNotEqual(module,'bpy')


class RuntimeSources(unittest.TestCase):
    def fixture(self) -> animations.AnimationJobs:
        result=animations.AnimationJobs(methodName='runTest');result.setUp()
        self.addCleanup(result.doCleanups);return result

    def test_guards_cover_all_canonical_engine_modules_and_presets(self) -> None:
        sources=paths.source_paths(ROOT)
        actual={p.relative_to(ROOT).as_posix() for p in (ROOT/'render_engine').rglob('*.py')}
        self.assertEqual(actual,{p for p in sources if p.startswith('render_engine/')})
        self.assertFalse(any(p.startswith('app/') for p in sources))
        self.assertIn('configs/render/room_fire_round3.json',sources)
        self.assertEqual(len(sources),len(set(paths.CODE_FILES)))
        with self.assertRaises(FileNotFoundError):paths.source_paths(ROOT/'app')
        f=self.fixture()
        self.assertEqual(jobs.preflight(f.asset,f.points,f.config,f.codes),f.inputs)

    def test_mutated_package_source_shim_init_or_preset_rejects_old_job(self) -> None:
        f=self.fixture();job=f.new_job();snapshot=(job/'config_snapshot.json').read_bytes()
        for name in ('render_engine/blender/F8_room_fire_style.py','render_engine/__init__.py',
                     'render_engine/paths.py','render_engine/jobs/run_room_animation.py','configs/render/room_fire_round3.json'):
            path=f.codes/name;original=path.read_bytes()
            with self.subTest(file=name):
                path.write_bytes(original+b'\n# modified fixture')
                with self.assertRaisesRegex(ValueError,'Protected input'):jobs.check_guards(f.inputs)
                inputs=jobs.preflight(f.asset,f.points,f.config,f.codes)
                with self.assertRaises(ValueError):jobs.check_resume(job,jobs.build_spec(inputs,'short'))
                path.write_bytes(original)
        self.assertEqual((job/'config_snapshot.json').read_bytes(),snapshot)
        jobs.check_guards(f.inputs)

    def test_old_nine_file_snapshot_cannot_resume_with_installed_package(self) -> None:
        f=self.fixture();old=deepcopy(f.spec)
        old['inputs']['codes']={'F8_room_animation.py':'legacy-nine-file-guard'}
        old.pop('signature');old['signature']=jobs.fingerprint(old)
        job=jobs.create_job(f.job_root,old);before=(job/'config_snapshot.json').read_bytes()
        with self.assertRaises(ValueError):jobs.check_resume(job,f.spec)
        self.assertEqual((job/'config_snapshot.json').read_bytes(),before)

    def test_missing_package_config_or_worker_stops_preflight_without_job(self) -> None:
        f=self.fixture()
        for name in ('render_engine/blender/F8_room_animation.py','render_engine/geometry/room_source_io.py',
                     'configs/render/room_fire_round3.json'):
            path=f.codes/name;original=path.read_bytes();path.unlink()
            with self.subTest(file=name),self.assertRaises(FileNotFoundError):
                jobs.preflight(f.asset,f.points,f.config,f.codes)
            path.write_bytes(original)
        self.assertFalse(f.job_root.exists())

    def test_launcher_uses_canonical_worker_and_preserves_lock_and_output_root(self) -> None:
        f=self.fixture();args=__import__('argparse').Namespace(asset=f.asset,points=f.points,config=f.config,
            stage='short',preset='test',wall_height=1.1,drop_component=[],approval=None,resume=None)
        process,run=f.launcher_fixture(0)
        @contextmanager
        def lock(root: Path):
            self.assertEqual(root,f.points.parent.parent);yield 5
        with patch.object(launcher.shutil,'which',return_value='fixture'), \
                patch.object(launcher,'preflight',return_value=f.inputs),patch.object(launcher,'gpu_lock',lock), \
                patch.object(launcher,'busy_processes',return_value={}),patch.object(launcher,'monitor_gpu'), \
                patch.object(launcher.subprocess,'Popen',side_effect=process) as child, \
                patch.object(launcher.subprocess,'run',side_effect=run):
            job=launcher.execute(args)
        command=child.call_args.args[0]
        self.assertEqual(Path(command[command.index('--python')+1]),paths.worker_script(ROOT))
        self.assertEqual(job.parent,f.job_root)


@unittest.skipUnless(shutil.which('powershell.exe') and shutil.which('tar'),'Windows PowerShell and tar required')
class EnginePackage(unittest.TestCase):
    setUp_base=release.ReleaseSafety.setUp
    run_ps=release.ReleaseSafety.run_ps
    script=release.ReleaseSafety.script

    def setUp(self) -> None:
        self.setUp_base()
        for name in paths.CODE_FILES:
            target=self.root/name
            target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(ROOT/name,target)

    def test_archive_installs_all_guarded_sources_without_engine_private_files(self) -> None:
        junk=('render_engine/blender/private.blend','render_engine/geometry/debug.json',
              'render_engine/jobs/.env','render_engine/blender/image.png',
              'configs/render/private.json','configs/render/prod.env')
        for name in junk:(self.root/name).write_bytes(b'private synthetic data')
        result=self.run_ps('& '+self.script('build.ps1'))
        self.assertEqual(result.returncode,0,result.stderr)
        package=next((self.root/'release/out').glob('burnroom-deploy-package-*.tar.gz'))
        extracted=self.root/'extracted'
        with tarfile.open(package) as archive:
            names=set(archive.getnames())
            for name in paths.CODE_FILES:self.assertIn('burnroom-deploy-package/'+name,names)
            for name in junk:self.assertNotIn('burnroom-deploy-package/'+name,names)
            archive.extractall(extracted,filter='data')
        installed=extracted/'burnroom-deploy-package'
        code='''from pathlib import Path
import render_engine.jobs.run_room_animation as old
import render_engine.jobs.run_room_animation as new
from render_engine.paths import default_config,project_root,source_paths
assert old is new
assert project_root()==Path('''+repr(str(installed))+''').resolve()
assert default_config().is_file()
assert all(p.is_file() for p in source_paths(project_root()).values())
print('installed engine verified',flush=True)
'''
        outside=self.root/'outside';outside.mkdir()
        self.assertIn('installed engine verified',python(code,outside,installed).stdout)

    def test_incomplete_engine_stops_packaging(self) -> None:
        path=self.root/'render_engine/blender/F8_room_animation.py';path.unlink()
        result=self.run_ps('& '+self.script('build.ps1'))
        self.assertNotEqual(result.returncode,0)
        self.assertEqual(list((self.root/'release/out').glob('*.tar.gz')),[])

    def test_missing_or_drifted_canonical_preset_stops_packaging(self) -> None:
        path=self.root/'configs/render/room_fire_round3.json'
        path.write_bytes(path.read_bytes()+b' ')
        self.assertNotEqual(self.run_ps('& '+self.script('build.ps1')).returncode,0)
        path.unlink()
        self.assertNotEqual(self.run_ps('& '+self.script('build.ps1')).returncode,0)
        self.assertEqual(list((self.root/'release/out').glob('*.tar.gz')),[])


class DockerContext(unittest.TestCase):
    def test_new_package_and_only_named_presets_are_allowed_and_bom_preserved(self) -> None:
        rules=(ROOT/'.dockerignore').read_text().splitlines()
        self.assertIn('!render_engine/**/*.py',rules)
        for revision in (1,2,3):self.assertIn(f'!configs/render/room_fire_round{revision}.json',rules)
        self.assertNotIn('!configs/**',rules)
        self.assertNotIn('!configs/render/*.json',rules)
        self.assertTrue((ROOT/'deploy/scripts/build.ps1').read_bytes().startswith(b'\xef\xbb\xbf'))
