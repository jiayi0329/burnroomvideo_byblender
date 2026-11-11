"""PRD section 5 / ARCHITECTURE 2.4 / migration batch 7.

Offline registry, explicit integration opt-in, temporary package fixtures and
PowerShell SSH/SCP substitutes. No real API/DB/Docker/Blender/deployment.
Run: python -B -m unittest tests.deploy.test_migration_cleanup -v
"""
import ast
from contextlib import redirect_stderr, redirect_stdout
import io
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

from tests import run_regression as runner
from tests.suites import GROUPS, PACKAGE_FILES, selected_modules
from tests.deploy import test_release_safety as release

ROOT = Path(__file__).resolve().parents[2]


class OfflineRegistry(unittest.TestCase):
    def test_groups_are_deduplicated_and_real_scene_tests_are_not_selected(self) -> None:
        modules = selected_modules()
        self.assertEqual(len(modules), len(set(modules)))
        self.assertEqual(selected_modules(['tools', 'tools']), GROUPS['tools'])
        self.assertTrue(all(m.startswith(('test.', 'tests.')) for m in modules))
        self.assertFalse({'tests.integration.test_api', 'tests.legacy.test_f6', 'tests.legacy.test_f7', 'test_4dkankan'} & set(modules))
        with self.assertRaises(ValueError):
            selected_modules(['unknown'])

    def test_list_is_lazy_and_direct_script_works_outside_project(self) -> None:
        code = f'''import runpy,sys
sys.argv=['regression','--list']
try:runpy.run_path({str(ROOT/'tests/run_regression.py')!r},run_name='__main__')
except SystemExit as exc:assert exc.code==0
assert not any(n.startswith(('app.','backend.','render_engine.','test.','requests','bpy','psycopg')) for n in sys.modules)
'''
        with tempfile.TemporaryDirectory() as folder:
            result = subprocess.run([sys.executable, '-B', '-c', code], cwd=folder,
                capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('tests.engine.test_room_animation', result.stdout)
            self.assertEqual(list(Path(folder).iterdir()), [])

    def test_offline_run_rejects_real_integration_environment_before_loading(self) -> None:
        for name in ('ROOM_DB_INTEGRATION', 'ROOM_TIMELINE_INTEGRATION'):
            with self.subTest(name=name), patch.dict(os.environ, {name: '1'}), \
                    patch.object(runner.unittest, 'TestLoader') as loader, redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as exc:
                    runner.main([])
                self.assertEqual(exc.exception.code, 2)
                loader.assert_not_called()

    def test_existing_report_is_never_overwritten_or_tests_loaded(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'report.json'
            path.write_bytes(b'history')
            with patch.dict(os.environ, {'ROOM_DB_INTEGRATION': '0', 'ROOM_TIMELINE_INTEGRATION': '0'}), \
                    patch.object(runner.unittest, 'TestLoader') as loader, redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    runner.main(['--report', str(path)])
                loader.assert_not_called()
            self.assertEqual(path.read_bytes(), b'history')

    def test_failure_skip_and_duration_are_reported_with_nonzero_exit(self) -> None:
        class Synthetic(unittest.TestCase):
            def test_pass(self) -> None:
                pass

            @unittest.skip('synthetic skip')
            def test_skip(self) -> None:
                pass

            def test_failure(self) -> None:
                self.fail('synthetic failure')

        suite = unittest.defaultTestLoader.loadTestsFromTestCase(Synthetic)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'new/report.json'
            with patch.dict(os.environ, {'ROOM_DB_INTEGRATION': '0', 'ROOM_TIMELINE_INTEGRATION': '0'}), \
                    patch.object(runner.unittest.TestLoader, 'loadTestsFromNames', return_value=suite), \
                    redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                self.assertEqual(runner.main(['--group', 'backend', '--report', str(path)]), 1)
            report = json.loads(path.read_text(encoding='utf-8'))
            self.assertEqual((report['tests_run'], report['passed'], report['failures']), (3, 1, 1))
            self.assertEqual(len(report['skipped']), 1)
            self.assertFalse(report['successful'])
            self.assertFalse(report['remote_validation'])
            self.assertGreaterEqual(report['elapsed_seconds'], 0)

    def test_real_timeline_class_requires_explicit_opt_in(self) -> None:
        tree = ast.parse((ROOT/'tests/integration/test_api.py').read_text(encoding='utf-8'))
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef))
        skip = cls.decorator_list[0]
        for value, expected in (('0', False), ('1', True)):
            with patch.dict(os.environ, {'ROOM_TIMELINE_INTEGRATION': value}):
                actual = eval(compile(ast.Expression(skip.args[0]), 'integration guard', 'eval'), {'os': os})
            self.assertEqual(actual, expected)


class DeploymentContracts(unittest.TestCase):
    def test_canonical_templates_shell_and_python_only_context(self) -> None:
        for name in ('docker-compose.prod.yml','docker-compose.gpu.yml','prod.env.example','scripts/prepare_deploy.sh'):
            self.assertTrue((ROOT/'deploy'/name).is_file())
            self.assertFalse((ROOT/'release'/name).exists())
        for name in ('build.ps1','deploy.ps1'):
            self.assertTrue((ROOT/'deploy/scripts'/name).read_bytes().startswith(b'\xef\xbb\xbf'))
        self.assertNotIn(b'\r',(ROOT/'deploy/scripts/prepare_deploy.sh').read_bytes())
        rules=(ROOT/'.dockerignore').read_text().splitlines()
        self.assertIn('!tests/**/*.py',rules)
        for forbidden in ('!app/**','!test/**','!tests/**'):
            self.assertNotIn(forbidden,rules)

    def check_idle(self, root: Path) -> None:
        source = (ROOT/'deploy/scripts/prepare_deploy.sh').read_text(encoding='utf-8')
        code = source.split("python3 - <<'PY'\n", 1)[1].split('\nPY\n', 1)[0]
        # Replace only the root Path with a temporary directory; execute the real guard.
        with patch('pathlib.Path', return_value=root):
            exec(compile(code, 'readonly predeploy guard', 'exec'), {})

    def test_deploy_guard_blocks_legacy_and_all_active_room_states_without_writes(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            legacy = root/'synthetic/render_status.json'
            legacy.parent.mkdir(parents=True)
            legacy.write_text('{"status":"running"}', encoding='utf-8')
            with self.assertRaisesRegex(SystemExit, 'Legacy render'):
                self.check_idle(root)
            legacy.write_text('{"status":"completed"}', encoding='utf-8')
            path = root/'synthetic/rooms/RoomX/render_jobs/job/status.json'
            path.parent.mkdir(parents=True)
            for state in ('created', 'preparing', 'rendering', 'encoding'):
                path.write_text(json.dumps({'state': state}), encoding='utf-8')
                before = path.read_bytes()
                with self.subTest(state=state), self.assertRaisesRegex(SystemExit, 'Room render'):
                    self.check_idle(root)
                self.assertEqual(path.read_bytes(), before)

    def test_deploy_guard_allows_finished_jobs_and_rejects_corrupt_status(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path = root/'synthetic/rooms/RoomX/render_jobs/job/status.json'
            path.parent.mkdir(parents=True)
            for state in ('awaiting_visual_review', 'failed'):
                path.write_text(json.dumps({'state': state}), encoding='utf-8')
                self.check_idle(root)
            path.write_bytes(b'broken')
            with self.assertRaises(json.JSONDecodeError):
                self.check_idle(root)
            self.assertEqual(path.read_bytes(), b'broken')


@unittest.skipUnless(shutil.which('powershell.exe') and shutil.which('tar'), 'Windows PowerShell and tar required')
class DeploymentPackages(unittest.TestCase):
    setUp = release.ReleaseSafety.setUp
    run_ps = release.ReleaseSafety.run_ps
    script = release.ReleaseSafety.script

    def canonical(self, name: str) -> str:
        return "'" + str(self.root/'deploy/scripts'/name).replace("'", "''") + "'"

    def test_repeat_canonical_build_preserves_packages_and_has_no_old_directories(self) -> None:
        for _ in range(2):
            result=self.run_ps('& '+self.script('build.ps1'))
            self.assertEqual(result.returncode,0,result.stderr)
        packages=list((self.root/'release/out').glob('burnroom-deploy-package-*.tar.gz'))
        self.assertEqual(len(packages),2)
        contents=[]
        for package in packages:
            with tarfile.open(package) as archive:
                self.assertFalse(any(n.startswith(('burnroom-deploy-package/app/','burnroom-deploy-package/test/')) for n in archive.getnames()))
                contents.append({m.name:archive.extractfile(m).read() for m in archive if m.isfile()})
        self.assertEqual(contents[0],contents[1])
        for name in PACKAGE_FILES:self.assertIn('burnroom-deploy-package/'+name,contents[0])
        self.assertEqual(contents[0]['burnroom-deploy-package/docker-compose.yml'],(self.root/'deploy/docker-compose.prod.yml').read_bytes())

    def test_missing_canonical_template_or_helper_prevents_archive_creation(self) -> None:
        for name in ('docker-compose.prod.yml','docker-compose.gpu.yml','prod.env.example','scripts/prepare_deploy.sh'):
            path=self.root/'deploy'/name;original=path.read_bytes();path.unlink()
            result=self.run_ps('& '+self.script('build.ps1'))
            self.assertNotEqual(result.returncode,0,result.stdout)
            path.write_bytes(original)
        self.assertEqual(list((self.root/'release/out').glob('*.tar.gz')),[])

    def test_test_artifacts_and_credentials_are_not_packaged(self) -> None:
        junk = ('test/private.json', 'test/preview.png', 'test/private.blend', 'test/__pycache__/x.pyc',
                'tests/deploy/private.json', 'tests/.env', 'tests/prod.env', 'tests/private.key')
        for name in junk:
            path = self.root/name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'synthetic private artifact')
        result = self.run_ps('& ' + self.script('build.ps1'))
        self.assertEqual(result.returncode, 0, result.stderr)
        package = next((self.root/'release/out').glob('*.tar.gz'))
        with tarfile.open(package) as archive:
            names = archive.getnames()
            for name in junk:
                self.assertNotIn('burnroom-deploy-package/' + name, names)

    def test_missing_deploy_implementation_does_not_silently_use_old_code(self) -> None:
        (self.root/'deploy/scripts/build.ps1').unlink()
        self.assertNotEqual(self.run_ps('& ' + self.script('build.ps1')).returncode, 0)
        self.assertFalse((self.root/'release/out').exists())

    def test_missing_test_runner_stops_build_instead_of_shipping_partial_entry(self) -> None:
        (self.root/'tests/run_regression.py').unlink()
        self.assertNotEqual(self.run_ps('& ' + self.script('build.ps1')).returncode, 0)
        self.assertEqual(list((self.root/'release/out').glob('*.tar.gz')), [])

    def test_old_and_new_deploy_entries_stop_on_fake_ssh_failure(self) -> None:
        out = self.root/'release/out'
        out.mkdir(parents=True)
        (out/'burnroom-deploy-package-synthetic.tar.gz').write_bytes(b'synthetic')
        for command in (self.script('deploy.ps1'), self.canonical('deploy.ps1')):
            code = "function ssh { $global:LASTEXITCODE=19 }; function scp { throw 'unexpected SCP' }; try { & " + command + "; exit 2 } catch { if ($_.Exception.Message -like '*停止部署') { exit 0 }; exit 3 }"
            self.assertEqual(self.run_ps(code).returncode, 0)

    def test_missing_canonical_helper_prevents_deploy_before_any_ssh(self) -> None:
        (self.root/'deploy/scripts/prepare_deploy.sh').unlink()
        code="function ssh { throw 'unexpected SSH' }; try { & "+self.script('deploy.ps1')+"; exit 2 } catch { if ($_.Exception.Message -like '*helper missing*') { exit 0 }; exit 3 }"
        self.assertEqual(self.run_ps(code).returncode,0)


if __name__ == '__main__':
    unittest.main()
