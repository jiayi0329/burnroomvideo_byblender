"""PRD engineering baseline; PROJECT_ORGANIZATION diagnostics migration.

ARCHITECTURE: readonly diagnostics stay separate from Room8 execution.
Legacy trace: PRD 2.2 / architecture 3.2. Checks the three migrated modules,
app compatibility paths and release packaging. Local offline unittest only:
python -B -m unittest tests.tools.test_diagnostics_migration -v
Uses temporary synthetic data, plotting stubs and Windows PowerShell/tar;
never runs Blender, Docker, real SSH, a database or real-scene diagnostics.
"""
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

from tools.diagnostics import diagnose_room_sections as diagnostic
from tools.diagnostics import room_section_plots as plots
from tests.deploy import test_release_safety as release
from tests.tools import test_room_sections as fixtures
from tests.tool_paths import DIAGNOSTIC_FILES

ROOT = Path(__file__).resolve().parents[2]
MODULES = ('diagnose_room_sections', 'room_section_geometry', 'room_section_plots')


def python(code: str, directory: Path, code_root: Path = ROOT) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, '-B', '-c', code], cwd=directory,
                          env={**os.environ, 'PYTHONPATH': str(code_root)},
                          capture_output=True, text=True, timeout=15, check=True)


class Compatibility(unittest.TestCase):
    def test_diagnostic_modules_exist_only_in_canonical_directory(self) -> None:
        for name in MODULES:
            module=importlib.import_module('tools.diagnostics.'+name)
            self.assertEqual(Path(module.__file__).resolve().parent,ROOT/'tools/diagnostics')
            self.assertFalse((ROOT/'app'/(name+'.py')).exists())

    def test_patching_old_entrypoint_still_affects_run(self) -> None:
        legacy = importlib.import_module('tools.diagnostics.diagnose_room_sections')
        with patch.object(legacy, 'load_inputs', side_effect=ValueError('synthetic sentinel')) as loader:
            with self.assertRaisesRegex(ValueError, 'synthetic sentinel'):
                diagnostic.run(Path('unused'), Path('unused'), Path('unused'), Path('unused'))
            loader.assert_called_once()

    def test_both_cli_help_paths_work_outside_repository_without_writes(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            for prefix in ('tools.diagnostics',):
                result = subprocess.run([sys.executable, '-B', '-m', prefix + '.diagnose_room_sections', '--help'],
                                        cwd=folder, env={**os.environ, 'PYTHONPATH': str(ROOT)},
                                        capture_output=True, text=True, timeout=15)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn('--inspection', result.stdout)
                self.assertIn('--wall-search', result.stdout)
            self.assertEqual(list(Path(folder).iterdir()), [])

    def test_both_cli_paths_still_require_explicit_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            for prefix in ('tools.diagnostics',):
                result = subprocess.run([sys.executable, '-B', '-m', prefix + '.diagnose_room_sections'],
                                        cwd=folder, env={**os.environ, 'PYTHONPATH': str(ROOT)},
                                        capture_output=True, text=True, timeout=15)
                self.assertEqual(result.returncode, 2)
                self.assertIn('--inspection', result.stderr)
            self.assertEqual(list(Path(folder).iterdir()), [])

    def test_imports_remain_lazy_and_do_not_change_matplotlib_environment(self) -> None:
        code = '''import importlib, json, os, sys
before = os.environ.get('MPLCONFIGDIR')
for prefix in ('tools.diagnostics',):
    for name in ('diagnose_room_sections', 'room_section_geometry', 'room_section_plots'):
        importlib.import_module(prefix + '.' + name)
assert os.environ.get('MPLCONFIGDIR') == before
print(json.dumps([name for name in ('matplotlib', 'bpy', 'psycopg') if name in sys.modules]), flush=True)
'''
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(json.loads(python(code, Path(folder)).stdout), [])

    def test_candidate_import_still_has_no_diagnostics_dependency(self) -> None:
        code = '''import json, sys
import render_engine.geometry.prepare_room_candidate
print(json.dumps([n for n in sys.modules if n.startswith(('tools', 'tools.diagnostics.diagnose_room_sections',
    'app.room_section_', 'tools.diagnostics.inspect_room_asset', 'backend.cli.import_rooms', 'matplotlib', 'bpy', 'psycopg'))]), flush=True)
'''
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(json.loads(python(code, Path(folder)).stdout), [])

    def test_html_index_still_escapes_labels_and_links_local_reports(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            plots.write_index(Path(folder), {'room_id': '<synthetic>'}, ['overview.png', 'section_X20.png'])
            text = (Path(folder) / 'index.html').read_text(encoding='utf-8')
            self.assertIn('&lt;synthetic&gt;', text)
            self.assertNotIn('<synthetic>', text)
            self.assertIn('section_X20.png', text)
            self.assertIn('report.json', text)
            self.assertIn('ready_for_cut=false', text)


class DiagnosticWorkflow(unittest.TestCase):
    setUp_base = fixtures.DiagnosticInputs.setUp_base
    write_review = fixtures.DiagnosticInputs.write_review
    save_evidence = fixtures.DiagnosticInputs.save_evidence
    setUp = fixtures.DiagnosticInputs.setUp

    def test_new_and_old_report_pipeline_match_with_plotting_stub(self) -> None:
        before = {p: diagnostic.sha256(p) for p in self.scene.rglob('*') if p.is_file()}

        def plot_stub(output: Path, report: dict, mesh: dict) -> list[str]:
            (output / 'synthetic_plot.png').write_bytes(b'unit-test placeholder, not a real PNG')
            return ['synthetic_plot.png']

        legacy = importlib.import_module('tools.diagnostics.diagnose_room_sections')
        with patch.object(plots, 'plot_report', side_effect=plot_stub):
            report, output = diagnostic.run(self.scene.parent, self.inspection_path, self.blender_path, self.output)
            old_report, old_output = legacy.run(self.scene.parent, self.inspection_path, self.blender_path, self.output)
        self.assertEqual(report, old_report)
        self.assertNotEqual(output, old_output)
        self.assertFalse(report['ready_for_cut'])
        self.assertTrue(report['source_and_history_unchanged'])
        self.assertEqual((output / 'findings.md').read_bytes(), (old_output / 'findings.md').read_bytes())
        self.assertTrue((output / 'index.html').is_file())
        self.assertEqual(before, {p: diagnostic.sha256(p) for p in before})

    def test_plot_failure_keeps_failure_receipt_and_sources(self) -> None:
        before = {p: diagnostic.sha256(p) for p in self.scene.rglob('*') if p.is_file()}
        with patch.object(plots, 'plot_report', side_effect=RuntimeError('synthetic plot failure')):
            with self.assertRaisesRegex(RuntimeError, 'synthetic plot failure'):
                diagnostic.run(self.scene.parent, self.inspection_path, self.blender_path, self.output)
        failures = list((self.scene / 'diagnostics/room_sections').glob('*/failure.json'))
        self.assertEqual(len(failures), 1)
        self.assertFalse(json.loads(failures[0].read_text(encoding='utf-8'))['ready_for_cut'])
        self.assertEqual(before, {p: diagnostic.sha256(p) for p in before})


@unittest.skipUnless(shutil.which('powershell.exe') and shutil.which('tar'), 'Windows PowerShell and tar required')
class DiagnosticsPackage(unittest.TestCase):
    setUp_base = release.ReleaseSafety.setUp
    run_ps = release.ReleaseSafety.run_ps
    script = release.ReleaseSafety.script

    def setUp(self) -> None:
        self.setUp_base()
        # The existing app imports now resolve to the installed geometry package.
        shutil.copytree(ROOT / 'render_engine', self.root / 'render_engine', dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns('__pycache__'))
        for source in (ROOT / 'tools').rglob('*.py'):
            relative = source.relative_to(ROOT)
            if relative.parts[:2] != ('tools', 'diagnostics') and relative.as_posix() != 'tools/__init__.py':
                continue
            target = self.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)

    def test_installer_contains_tools_and_imports_from_extracted_package(self) -> None:
        for relative in ('tools/diagnostics/private.json', 'tools/diagnostics/.env', 'tools/diagnostics/prod.env',
                         'tools/diagnostics/private.key', 'tools/diagnostics/preview.png',
                         'tools/diagnostics/__pycache__/cache.pyc', 'tools/integration/private.py'):
            target = self.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text('synthetic excluded content', encoding='utf-8')
        result = self.run_ps('& ' + self.script('build.ps1'))
        self.assertEqual(result.returncode, 0, result.stderr)
        package = next((self.root / 'release/out').glob('burnroom-deploy-package-*.tar.gz'))
        extracted = self.root / 'extracted'
        with tarfile.open(package) as archive:
            names = set(archive.getnames())
            expected = {'burnroom-deploy-package/' + name for name in DIAGNOSTIC_FILES}
            self.assertEqual({n for n in names if n.startswith('burnroom-deploy-package/tools/') and n.endswith('.py')}, expected)
            for name in names:
                if name.startswith('burnroom-deploy-package/tools/'):
                    self.assertNotIn(name.rsplit('/', 1)[-1], ('private.json', '.env', 'prod.env', 'private.key', 'preview.png', 'cache.pyc', 'private.py'))
            archive.extractall(extracted, filter='data')
        package_root = extracted / 'burnroom-deploy-package'
        code = '''import importlib
from pathlib import Path
root = Path.cwd().resolve()
for name in ('diagnose_room_sections', 'room_section_geometry', 'room_section_plots'):
    module = importlib.import_module('tools.diagnostics.' + name)
    assert Path(module.__file__).resolve().is_relative_to(root)
print('packaged imports verified', flush=True)
'''
        self.assertIn('packaged imports verified', python(code, package_root, package_root).stdout)

    def test_missing_tools_package_stops_build_instead_of_shipping_broken_shims(self) -> None:
        source = self.root / 'tools/__init__.py'
        source.rename(source.with_suffix('.unavailable'))
        self.assertNotEqual(self.run_ps('& ' + self.script('build.ps1')).returncode, 0)
        self.assertEqual(list((self.root / 'release/out').glob('*.tar.gz')), [])


class ContextPolicy(unittest.TestCase):
    def test_only_diagnostic_python_sources_are_allowed_in_docker_context(self) -> None:
        rules = [line.strip() for line in (ROOT / '.dockerignore').read_text().splitlines() if line.strip() and not line.startswith('#')]
        self.assertEqual(rules[0], '**')
        for rule in ('!tools/', '!tools/__init__.py', '!tools/diagnostics/', '!tools/diagnostics/*.py'):
            self.assertIn(rule, rules)
        for rule in ('!tools/**', '!tools/diagnostics/**', '!tools/integration/', '!data/**'):
            self.assertNotIn(rule, rules)
        self.assertTrue((ROOT / 'deploy/scripts/build.ps1').read_bytes().startswith(b'\xef\xbb\xbf'))
