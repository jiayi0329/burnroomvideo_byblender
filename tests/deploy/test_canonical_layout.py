"""PRD engineering cleanup / ARCHITECTURE process boundaries.

Canonical-only source layout, immutable SQL/presets and old-job rejection.
Synthetic offline inputs only; no real database, Blender, Docker or deployment.
Run: python -B -m unittest tests.deploy.test_canonical_layout -v
"""
import ast
import hashlib
import importlib.util
from pathlib import Path
import unittest

from backend import paths as backend
from render_engine import paths as engine
from render_engine.jobs import room_animation_job as jobs
from tests.engine import test_room_animation as fixtures
from tests.suites import selected_modules

ROOT = Path(__file__).resolve().parents[2]


class CanonicalLayout(unittest.TestCase):
    def test_removed_source_trees_have_no_compatibility_files(self) -> None:
        for folder in ('app', 'test'):
            self.assertFalse(any((ROOT/folder).rglob('*.py')), folder)
        for relative in ('scripts/build.ps1', 'scripts/deploy.ps1', 'scripts/prepare_deploy.sh',
                         'docker-compose.prod.yml', 'docker-compose.gpu.yml', 'prod.env.example'):
            self.assertFalse((ROOT/'release'/relative).exists(), relative)

    def test_database_has_one_immutable_baseline_location(self) -> None:
        file = ROOT/'backend/database/migrations/001_rooms.sql'
        self.assertEqual(backend.migration_files(), (file,))
        self.assertEqual(hashlib.sha256(file.read_bytes()).hexdigest(), backend.BASELINE_MIGRATION_SHA256)
        self.assertFalse((ROOT/'backend/db/migrations/001_rooms.sql').exists())
        self.assertFalse((ROOT/'app/db/001_rooms.sql').exists())

    def test_three_distinct_presets_have_one_location_and_approved_default(self) -> None:
        presets = [ROOT/f'configs/render/room_fire_round{i}.json' for i in (1, 2, 3)]
        self.assertEqual(len({p.read_bytes() for p in presets}), 3)
        self.assertEqual(jobs.fingerprint(jobs.read_json(engine.default_config())), jobs.APPROVED_STYLE_FINGERPRINT)
        for file in presets:
            self.assertFalse((ROOT/'app'/file.name).exists())

    def test_registered_tests_resolve_to_single_tests_tree(self) -> None:
        modules = selected_modules()
        self.assertEqual(len(modules), len(set(modules)))
        for name in modules:
            self.assertTrue(name.startswith('tests.'), name)
            spec = importlib.util.find_spec(name)
            self.assertIsNotNone(spec, name)
            self.assertTrue(Path(spec.origin).resolve().is_relative_to(ROOT/'tests'), name)

    def test_runtime_imports_do_not_depend_on_deleted_packages(self) -> None:
        for folder in ('backend', 'render_engine', 'tools'):
            for file in (ROOT/folder).rglob('*.py'):
                for node in ast.walk(ast.parse(file.read_text(encoding='utf-8'))):
                    names = ([node.module or ''] if isinstance(node, ast.ImportFrom) else
                             [x.name for x in node.names] if isinstance(node, ast.Import) else [])
                    for name in names:
                        self.assertFalse(name.split('.')[0] in ('app', 'test'), str(file)+': '+name)

    def test_legacy_worker_is_separate_and_backend_does_not_import_it(self) -> None:
        self.assertEqual(backend.legacy_render_script(), ROOT/'render_engine/legacy/F8_blender_render.py')
        self.assertTrue(backend.legacy_render_script().is_file())
        for file in (ROOT/'backend').rglob('*.py'):
            source = file.read_text(encoding='utf-8')
            for node in ast.walk(ast.parse(source)):
                if isinstance(node, ast.ImportFrom):
                    self.assertFalse((node.module or '').startswith(('bpy', 'render_engine.blender',
                                                                             'render_engine.legacy.F8_blender_render')))

    def test_source_guard_covers_every_engine_module_without_mirrors(self) -> None:
        sources = engine.source_paths(ROOT)
        actual = {p.relative_to(ROOT).as_posix() for p in (ROOT/'render_engine').rglob('*.py')}
        self.assertEqual(actual, {k for k in sources if k.startswith('render_engine/')})
        self.assertEqual(len(sources), 28)
        self.assertFalse(any(k.startswith(('app/', 'release/', 'test/')) for k in sources))

    def test_previous_40_file_task_cannot_resume_or_have_snapshot_rewritten(self) -> None:
        f = fixtures.AnimationJobs(methodName='runTest')
        f.setUp()
        self.addCleanup(f.doCleanups)
        old = jobs.build_spec(f.inputs, 'short')
        old['inputs']['codes'] = {f'old-source-{i}': 'original-sha' for i in range(40)}
        old.pop('signature')
        old['signature'] = jobs.fingerprint(old)
        job = jobs.create_job(f.job_root, old)
        before = (job/'config_snapshot.json').read_bytes()
        with self.assertRaises(ValueError):
            jobs.check_resume(job, f.spec)
        self.assertEqual((job/'config_snapshot.json').read_bytes(), before)
