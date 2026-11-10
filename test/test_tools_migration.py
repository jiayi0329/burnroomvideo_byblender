"""PRD engineering baseline / ARCHITECTURE geometry boundary / batch 6.

Temporary synthetic inputs, fake API responses, Blender import stand-ins and
PowerShell/tar packaging only. No real network/DB/Blender/render/deployment.
Run: python -B -m unittest test.test_tools_migration -v
"""
import ast
from contextlib import redirect_stdout, redirect_stderr
import importlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from render_engine.geometry import floorplan_alignment as core
from render_engine.jobs import room_animation_job as jobs
from tools.diagnostics import analyze_floorplan as align
from tools.diagnostics import inspect_room_asset as inspection
from tools.integration import probe_scene_api as manual
from test import test_diagnostics_migration as packaging
from test import test_room_animation as animations
from test import test_room_database as fixtures
from test.tool_paths import DIAGNOSTIC_FILES

ROOT=Path(__file__).resolve().parents[1]
MOVED={'analyze_floorplan':'tools.diagnostics.analyze_floorplan',
       'inspect_room_asset':'tools.diagnostics.inspect_room_asset',
       'probe_floorplan':'tools.diagnostics.probe_floorplan'}


def python(code: str, working: Path, root: Path=ROOT) -> subprocess.CompletedProcess:
    result=subprocess.run([sys.executable,'-B','-c',code],cwd=working,
        env={**os.environ,'PYTHONPATH':str(root)},capture_output=True,text=True,timeout=20)
    if result.returncode:raise AssertionError(result.stderr)
    return result


class ToolCompatibility(unittest.TestCase):
    def test_old_and_new_modules_and_shared_functions_keep_identity(self) -> None:
        for old,new in MOVED.items():
            self.assertIs(importlib.import_module('app.'+old),importlib.import_module(new))
        for name in ('analyze','resolve_source','contains','classify','sha256','rank_candidates','parse_rooms'):
            self.assertIs(getattr(align,name),getattr(core,name))

    def test_old_cli_patching_still_changes_the_actual_command(self) -> None:
        old=importlib.import_module('app.analyze_floorplan')
        with patch.object(old,'analyze',side_effect=ValueError('synthetic sentinel')) as analyze, \
                patch('sys.argv',['align','--scene','test','--probe-dir','unused']),redirect_stdout(io.StringIO()):
            self.assertEqual(align.main(),1)
        analyze.assert_called_once()

    def test_imports_have_no_network_dotenv_db_bpy_or_file_writes(self) -> None:
        code='''import importlib,os,sys
from pathlib import Path
before=os.environ.get('DK_APPKEY')
for name in ('app.analyze_floorplan','app.inspect_room_asset','app.probe_floorplan',
             'tools.diagnostics.analyze_floorplan','tools.diagnostics.inspect_room_asset',
             'tools.diagnostics.probe_floorplan','tools.integration.probe_scene_api','test_4dkankan'):
    importlib.import_module(name)
assert os.environ.get('DK_APPKEY')==before
assert not {'requests','dotenv','psycopg','bpy','matplotlib'} & set(sys.modules)
assert list(Path.cwd().iterdir())==[]
print('lazy diagnostic imports',flush=True)
'''
        with tempfile.TemporaryDirectory() as folder:
            self.assertIn('lazy diagnostic imports',python(code,Path(folder)).stdout)

    def test_old_new_module_and_direct_script_help_outside_repository(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            for name,module in MOVED.items():
                for command in (['-m','app.'+name],['-m',module],
                    [str(ROOT/'app'/(name+'.py'))],[str(ROOT/Path(*module.split('.')).with_suffix('.py'))]):
                    result=subprocess.run([sys.executable,'-B',*command,'--help'],cwd=folder,
                        env={**os.environ,'PYTHONPATH':str(ROOT)},capture_output=True,text=True,timeout=15)
                    self.assertEqual(result.returncode,0,result.stderr)
                    self.assertIn('--scene',result.stdout)
            self.assertEqual(list(Path(folder).iterdir()),[])

    def test_blender_diagnostic_has_same_import_and_help_with_no_ops_available(self) -> None:
        code=f'''import importlib,runpy,sys
from pathlib import Path
from types import SimpleNamespace
sys.modules['bpy']=SimpleNamespace()
sys.modules['mathutils']=SimpleNamespace()
sys.modules['mathutils.kdtree']=SimpleNamespace(KDTree=object)
old=importlib.import_module('app.F8_inspect_room_import')
new=importlib.import_module('tools.diagnostics.blender.F8_inspect_room_import')
assert old is new
for name in ('app/F8_inspect_room_import.py','tools/diagnostics/blender/F8_inspect_room_import.py'):
    sys.argv=['blender','--','--help']
    try:runpy.run_path(str(Path({str(ROOT)!r})/name),run_name='__main__')
    except SystemExit as exc:assert exc.code==0
print('Blender import/help only',flush=True)
'''
        with tempfile.TemporaryDirectory() as folder:
            self.assertIn('import/help only',python(code,Path(folder)).stdout)
            self.assertEqual(list(Path(folder).iterdir()),[])

    def test_core_is_read_only_and_backend_no_longer_imports_diagnostic_cli(self) -> None:
        tree=ast.parse((ROOT/'render_engine/geometry/floorplan_alignment.py').read_text(encoding='utf-8'))
        functions={n.name for n in tree.body if isinstance(n,ast.FunctionDef)}
        self.assertEqual(len(functions),18)
        self.assertFalse(functions & {'main','write_outputs','write_overlay'})
        for node in ast.walk(tree):
            if isinstance(node,ast.ImportFrom):
                self.assertFalse((node.module or '').startswith(('tools','backend','bpy','argparse')))
            if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute):
                self.assertNotIn(node.func.attr,('write_text','write_bytes','mkdir','unlink'))
        code='''import sys
import backend.cli.import_rooms
assert 'render_engine.geometry.floorplan_alignment' in sys.modules
assert not any(n.startswith(('tools','app.analyze_floorplan','psycopg','bpy')) for n in sys.modules)
print('backend/core only',flush=True)
'''
        with tempfile.TemporaryDirectory() as folder:
            self.assertIn('backend/core only',python(code,Path(folder)).stdout)

    def test_synthetic_alignment_inspection_and_review_files_are_preserved(self) -> None:
        f=fixtures.ImportValidation(methodName='runTest');f.setUp();self.addCleanup(f.doCleanups)
        before={p:core.sha256(p) for p in f.scene.rglob('*') if p.is_file()}
        old=importlib.import_module('app.analyze_floorplan')
        self.assertEqual(old.analyze(f.scene,f.probe,transform_id='xy'),core.analyze(f.scene,f.probe,transform_id='xy'))
        old_inspect=importlib.import_module('app.inspect_room_asset')
        args=(f.scene,f.probe,f.output,f.review_path,'R')
        self.assertEqual(old_inspect.inspect(*args),inspection.inspect(*args))
        self.assertEqual(before,{p:core.sha256(p) for p in before})

    def test_shared_core_is_guarded_and_changed_source_rejects_resume(self) -> None:
        key='render_engine/geometry/floorplan_alignment.py';self.assertIn(key,jobs.CODE_FILES)
        f=animations.AnimationJobs(methodName='runTest');f.setUp();self.addCleanup(f.doCleanups)
        job=f.new_job();before=(job/'config_snapshot.json').read_bytes()
        (f.codes/key).write_text('# changed synthetic core',encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'Protected input'):jobs.check_guards(f.inputs)
        new=jobs.preflight(f.asset,f.points,f.config,f.codes)
        with self.assertRaises(ValueError):jobs.check_resume(job,jobs.build_spec(new,'short'))
        self.assertEqual((job/'config_snapshot.json').read_bytes(),before)


class ManualIntegration(unittest.TestCase):
    def test_old_root_is_not_an_automatic_test_and_requires_network_opt_in(self) -> None:
        old=importlib.import_module('test_4dkankan')
        self.assertFalse(old.__test__);self.assertFalse(old.test_connection.__test__)
        self.assertIs(old.test_connection,manual.test_connection)
        with self.assertRaisesRegex(ValueError,'authorization'):old.test_connection()
        with patch('sys.argv',['probe']),redirect_stdout(io.StringIO()),redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as exc:manual.main()
        self.assertEqual(exc.exception.code,2)

    def test_missing_key_makes_no_request(self) -> None:
        post=Mock(side_effect=AssertionError('no network'))
        with patch.dict(sys.modules,{'requests':SimpleNamespace(post=post)}), \
                patch.dict(os.environ,{},clear=True),redirect_stdout(io.StringIO()):
            self.assertEqual(manual.test_connection(allow_network=True),1)
        post.assert_not_called()

    def test_explicit_fake_api_reports_counts_without_private_scene_or_urls(self) -> None:
        response=Mock();response.json.return_value={'code':0,'data':{'total':3,'list':[
            {'sceneName':'private-scene','url':'https://example.test/?secret=token'}]}}
        post=Mock(return_value=response);out=io.StringIO()
        with patch.dict(sys.modules,{'requests':SimpleNamespace(post=post)}), \
                patch.dict(os.environ,{'DK_APPKEY':'synthetic-key'}),redirect_stdout(out):
            self.assertEqual(manual.test_connection(allow_network=True),0)
        result=json.loads(out.getvalue());self.assertEqual(result,{'status':'ok','code':0,'scene_count':3})
        self.assertNotIn('synthetic-key',out.getvalue());self.assertNotIn('private-scene',out.getvalue())
        self.assertEqual(post.call_args.kwargs['timeout'],(10,30));self.assertFalse(post.call_args.kwargs['allow_redirects'])

    def test_fake_failure_does_not_echo_exception_secrets(self) -> None:
        post=Mock(side_effect=RuntimeError('synthetic-key private-url'));out=io.StringIO()
        with patch.dict(sys.modules,{'requests':SimpleNamespace(post=post)}), \
                patch.dict(os.environ,{'DK_APPKEY':'synthetic-key'}),redirect_stdout(out):
            self.assertEqual(manual.test_connection(allow_network=True),1)
        self.assertIn('RuntimeError',out.getvalue());self.assertNotIn('synthetic-key',out.getvalue())

    def test_old_and_new_help_paths_never_load_dotenv_or_send_request(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            for command in (['-m','tools.integration.probe_scene_api'],[str(ROOT/'test_4dkankan.py')]):
                result=subprocess.run([sys.executable,'-B',*command,'--help'],cwd=folder,
                    env={**os.environ,'PYTHONPATH':str(ROOT)},capture_output=True,text=True,timeout=15)
                self.assertEqual(result.returncode,0,result.stderr);self.assertIn('--allow-network',result.stdout)
            self.assertEqual(list(Path(folder).iterdir()),[])


@unittest.skipUnless(shutil.which('powershell.exe') and shutil.which('tar'),'Windows PowerShell and tar required')
class ToolsPackage(unittest.TestCase):
    setUp_base=packaging.DiagnosticsPackage.setUp_base
    run_ps=packaging.DiagnosticsPackage.run_ps
    script=packaging.DiagnosticsPackage.script

    def setUp(self) -> None:
        packaging.DiagnosticsPackage.setUp(self)
        for name in ('inspect_room_asset','probe_floorplan','F8_inspect_room_import'):
            shutil.copyfile(ROOT/'app'/(name+'.py'),self.root/'app'/(name+'.py'))
        shutil.copyfile(ROOT/'backend/cli/import_rooms.py',self.root/'backend/cli/import_rooms.py')

    def test_all_diagnostics_import_from_extracted_package_and_private_tools_excluded(self) -> None:
        junk=('tools/integration/probe_scene_api.py','tools/diagnostics/private.py',
              'tools/diagnostics/report.json','tools/diagnostics/blender/output.blend')
        for name in junk:
            path=self.root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'synthetic private file')
        result=self.run_ps('& '+self.script('build.ps1'));self.assertEqual(result.returncode,0,result.stderr)
        package=next((self.root/'release/out').glob('burnroom-deploy-package-*.tar.gz'));extracted=self.root/'extracted'
        with tarfile.open(package) as archive:
            names=set(archive.getnames())
            for name in DIAGNOSTIC_FILES:self.assertIn('burnroom-deploy-package/'+name,names)
            for name in junk:self.assertNotIn('burnroom-deploy-package/'+name,names)
            archive.extractall(extracted,filter='data')
        installed=extracted/'burnroom-deploy-package';outside=self.root/'outside';outside.mkdir()
        code=f'''import importlib
from pathlib import Path
for old,new in {MOVED!r}.items():
    module=importlib.import_module('app.'+old)
    assert module is importlib.import_module(new)
    assert Path(module.__file__).resolve().is_relative_to(Path({str(installed)!r}))
from backend.cli.import_rooms import build_plan
assert callable(build_plan)
print('packaged diagnostics verified',flush=True)
'''
        self.assertIn('diagnostics verified',python(code,outside,installed).stdout)

    def test_missing_blender_diagnostic_stops_build(self) -> None:
        (self.root/'tools/diagnostics/blender/F8_inspect_room_import.py').unlink()
        self.assertNotEqual(self.run_ps('& '+self.script('build.ps1')).returncode,0)
        self.assertEqual(list((self.root/'release/out').glob('*.tar.gz')),[])

    def test_missing_shared_core_stops_build(self) -> None:
        (self.root/'render_engine/geometry/floorplan_alignment.py').unlink()
        self.assertNotEqual(self.run_ps('& '+self.script('build.ps1')).returncode,0)
        self.assertEqual(list((self.root/'release/out').glob('*.tar.gz')),[])
