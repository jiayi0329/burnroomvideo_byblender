"""PRD engineering baseline / ARCHITECTURE 2.1 / directory migration batch 5.

Actual FastAPI TestClient and MinIO/psycopg modules, synthetic files/connections.
Checks compatibility, unchanged SQL, lazy connections, legacy worker selection
and temporary PowerShell/tar packages. No live DB/MinIO/HTTP/GPU/Blender/Docker.
Run: python -B -m unittest tests.backend.test_backend_migration -v
"""
import ast
from contextlib import nullcontext
import hashlib
import importlib
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
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from backend import paths
from backend.api import main, room_api
from backend.adapters.postgres import database
from tests.deploy import test_release_safety as release

ROOT = Path(__file__).resolve().parents[2]


def python(code: str, working: Path, root: Path = ROOT) -> subprocess.CompletedProcess:
    result = subprocess.run([sys.executable,'-B','-c',code],cwd=working,
        env={**os.environ,'PYTHONPATH':str(root)},capture_output=True,text=True,timeout=25)
    if result.returncode:
        raise AssertionError(result.stderr)
    return result


class Compatibility(unittest.TestCase):
    def test_backend_modules_have_only_canonical_locations_and_patching_works(self) -> None:
        for name, group in paths.MODULE_LOCATIONS.items():
            module=importlib.import_module('backend.'+group.replace('/','.')+'.'+name)
            self.assertEqual(Path(module.__file__).resolve(),ROOT/'backend'/group/(name+'.py'))
        self.assertFalse(any((ROOT/'app').glob('*.py')))
        with patch.object(main,'APP_KEY',None):
            self.assertFalse(main.read_root()['appkey_loaded'])

    def test_startup_imports_do_not_connect_migrate_launch_or_import_bpy(self) -> None:
        code='''import importlib,sys
from unittest.mock import patch
import backend.adapters.postgres.database as db
import backend.adapters.minio.s3_io as s3
with patch.object(db,'connect',side_effect=AssertionError('database forbidden')) as connect, \\
     patch.object(db,'migrate',side_effect=AssertionError('migration forbidden')) as migrate, \\
     patch.object(s3,'get_minio_client',side_effect=AssertionError('MinIO forbidden')) as minio, \\
     patch('subprocess.Popen',side_effect=AssertionError('process forbidden')), \\
     patch('threading.Thread.start',side_effect=AssertionError('thread forbidden')):
    import backend.api.main as old
    import backend.api.main as new
    assert old.app is new.app
    import backend.cli.import_rooms,backend.cli.check_catalog
    connect.assert_not_called();migrate.assert_not_called();minio.assert_not_called()
assert 'bpy' not in sys.modules
print('startup has no service calls',flush=True)
'''
        with tempfile.TemporaryDirectory() as folder:
            self.assertIn('no service calls',python(code,Path(folder)).stdout)
            self.assertEqual(list(Path(folder).iterdir()),[])

    def test_existing_asgi_routes_and_methods_are_preserved_without_new_room_job_api(self) -> None:
        expected={
            ('/','GET'),('/api/scenes','GET'),('/api/download_scene/{scene_code}','GET'),
            ('/api/generate_timeline/{scene_code}','POST'),('/api/render/{scene_code}','POST'),
            ('/api/render/{scene_code}/status','GET'),('/api/render/{scene_code}/share','GET'),
            ('/api/pipeline/{scene_code}','POST'),('/api/catalog/scenes/{scene_code}/rooms','GET'),
            ('/api/catalog/rooms/{room_id}/points','GET'),('/api/catalog/rooms/{room_id}/assets','GET'),
            ('/api/catalog/assets/{asset_id}/share','GET'),
        }
        actual={(r.path,m) for r in main.app.routes if r.path=='/' or r.path.startswith('/api/') for m in r.methods}
        self.assertEqual(actual,expected)
        self.assertIs(importlib.import_module('backend.api.main').app,main.app)

    def test_canonical_cli_module_and_script_help_are_read_only(self) -> None:
        entries=[]
        for name in ('import_rooms','check_catalog','database'):
            group=paths.MODULE_LOCATIONS[name]
            entries.extend([['-m','backend.'+group.replace('/','.')+'.'+name],
                            [str(ROOT/'backend'/group/(name+'.py'))]])
        with tempfile.TemporaryDirectory() as folder:
            for entry in entries:
                result=subprocess.run([sys.executable,'-B',*entry,'--help'],cwd=folder,
                    env={**os.environ,'PYTHONPATH':str(ROOT)},capture_output=True,text=True,timeout=15)
                self.assertEqual(result.returncode,0,result.stderr)
                self.assertIn('usage:',result.stdout)
            self.assertEqual(list(Path(folder).iterdir()),[])

    def test_backend_uses_canonical_imports_and_never_imports_bpy_or_room8_worker(self) -> None:
        allowed_legacy={'render_engine.legacy.F6_detect','render_engine.legacy.F7_spread','tools.diagnostics.analyze_floorplan'}
        for file in (ROOT/'backend').rglob('*.py'):
            tree=ast.parse(file.read_text(encoding='utf-8'))
            for node in ast.walk(tree):
                modules=([node.module or ''] if isinstance(node,ast.ImportFrom) else
                         [n.name for n in node.names] if isinstance(node,ast.Import) else [])
                for module in modules:
                    self.assertNotEqual(module,'bpy',str(file))
                    self.assertFalse(module.startswith('render_engine.blender'),str(file))
                    self.assertFalse(module.startswith(('app.','tools.')),str(file))


class DatabasePaths(unittest.TestCase):
    def test_baseline_sql_hash_is_unchanged_and_only_canonical_location_is_used(self) -> None:
        file=ROOT/'backend/database/migrations/001_rooms.sql'
        self.assertEqual(hashlib.sha256(file.read_bytes()).hexdigest(),paths.BASELINE_MIGRATION_SHA256)
        self.assertEqual(paths.migration_files(),(file,))
        self.assertNotIn('app/db/001_rooms.sql',paths.PACKAGE_FILES)
        self.assertEqual(len(paths.PACKAGE_FILES),22)

    def test_missing_or_drifted_sql_fails_before_database_connection(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            canonical=root/'backend/database/migrations/001_rooms.sql';canonical.parent.mkdir(parents=True)
            for mode in ('missing','drift'):
                if mode=='drift':
                    canonical.write_text('SELECT 1;',encoding='utf-8')
                with patch.object(database,'migration_files',side_effect=lambda:paths.migration_files(root)), \
                        patch.object(database,'connect',side_effect=AssertionError('no database')) as connect:
                    with self.subTest(mode=mode),self.assertRaises((FileNotFoundError,ValueError)):
                        database.migrate()
                    connect.assert_not_called()

    def connection(self, checksum: str) -> MagicMock:
        conn=MagicMock()
        def execute(statement: object,params: tuple | None=None) -> SimpleNamespace:
            value=None
            if isinstance(statement,str) and statement.startswith('SELECT sha256 FROM schema_migrations'):
                value={'sha256':checksum}
            if isinstance(statement,str) and statement.startswith('SELECT 1 FROM pg_roles'):
                value={'exists':True}
            return SimpleNamespace(fetchone=lambda:value)
        conn.execute.side_effect=execute
        return conn

    def test_existing_migration_checksum_skips_sql_body_and_preserves_application_role(self) -> None:
        file=paths.migration_files()[0];conn=self.connection(hashlib.sha256(file.read_bytes()).hexdigest())
        with patch.dict(os.environ,{'PGUSER':'synthetic_app','PGPASSWORD':'synthetic-only'}), \
                patch.object(database,'connect',return_value=nullcontext(conn)) as connect,patch('builtins.print'):
            database.migrate()
        connect.assert_called_once_with(admin=True)
        statements=[c.args[0] for c in conn.execute.call_args_list]
        self.assertNotIn(file.read_text(encoding='utf-8'),statements)
        self.assertTrue(any(isinstance(s,str) and s.startswith('SELECT sha256 FROM schema_migrations') for s in statements))

    def test_changed_applied_checksum_is_rejected_without_running_sql_body(self) -> None:
        file=paths.migration_files()[0];conn=self.connection('different-checksum')
        with patch.dict(os.environ,{'PGUSER':'synthetic_app','PGPASSWORD':'synthetic-only'}), \
                patch.object(database,'connect',return_value=nullcontext(conn)),self.assertRaisesRegex(ValueError,'checksum changed'):
            database.migrate()
        self.assertNotIn(file.read_text(encoding='utf-8'),[c.args[0] for c in conn.execute.call_args_list])

    def test_cli_migration_failure_keeps_error_redacted(self) -> None:
        with patch('sys.argv',['database']),patch.object(database,'migrate',side_effect=RuntimeError('synthetic-private-token')), \
                patch('builtins.print') as output:
            self.assertEqual(database.main(),1)
        self.assertIn('RuntimeError',output.call_args.args[0])
        self.assertNotIn('synthetic-private-token',output.call_args.args[0])
        self.assertTrue(output.call_args.kwargs['flush'])

    def test_connect_keeps_existing_environment_names_timeout_and_role_split(self) -> None:
        import psycopg
        env={'PGPASSWORD':'synthetic-app','POSTGRES_PASSWORD':'synthetic-admin','PGUSER':'synthetic_role',
             'PGHOST':'synthetic-host','PGPORT':'5433','PGDATABASE':'synthetic_db'}
        with patch.dict(os.environ,env,clear=True),patch.object(psycopg,'connect') as connect:
            database.connect();app=dict(connect.call_args.kwargs)
            database.connect(admin=True);admin=dict(connect.call_args.kwargs)
        self.assertEqual(app['user'],'synthetic_role');self.assertEqual(admin['user'],'postgres')
        self.assertEqual(app['connect_timeout'],5);self.assertEqual(app['options'],'-c statement_timeout=30000')
        self.assertEqual((app['host'],app['dbname'],app['port']),('synthetic-host','synthetic_db','5433'))


class LegacyBehavior(unittest.TestCase):
    def test_database_outage_still_allows_health_and_existing_video_share(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            video=Path(folder)/'output.mp4';video.write_bytes(b'synthetic video')
            with patch.object(room_api,'connect',side_effect=RuntimeError('synthetic secret')), \
                    patch.object(main,'read_render_status',return_value=None),patch.object(main,'verify_output',return_value=video), \
                    patch.object(main,'ensure_share_output',return_value='test/output.mp4'), \
                    patch.object(main,'get_share_url',return_value='http://synthetic.test/video'),patch.object(main,'write_event'):
                client=TestClient(main.app)
                self.assertEqual(client.get('/').status_code,200)
                response=client.get('/api/catalog/scenes/test/rooms')
                self.assertEqual(response.status_code,503);self.assertNotIn('synthetic secret',response.text)
                self.assertEqual(client.get('/api/render/test/share').status_code,200)

    def test_legacy_render_keeps_worker_cwd_and_does_not_select_room8_engine(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);scene=root/'test';scene.mkdir();(scene/'timeline.json').write_text('{}',encoding='utf-8')
            with patch.object(main,'DATA_ROOT',root),patch.object(main,'read_render_status',return_value=None), \
                    patch.object(main,'download_scene_assets',return_value={'pulled':0,'skipped':0,'failed':0}), \
                    patch.object(main,'write_event'),patch.object(main,'write_render_status'), \
                    patch.object(main,'start_gpu_sampler'),patch.object(main.threading,'Thread'), \
                    patch.object(main.subprocess,'Popen') as process:
                result=main.start_render('test')
            command=process.call_args.args[0]
            self.assertEqual(Path(command[command.index('--python')+1]),ROOT/'render_engine/legacy/F8_blender_render.py')
            self.assertEqual(Path(process.call_args.kwargs['cwd']),ROOT)
            self.assertEqual(result['status'],'running')


@unittest.skipUnless(shutil.which('powershell.exe') and shutil.which('tar'),'Windows PowerShell and tar required')
class BackendPackage(unittest.TestCase):
    setUp_base=release.ReleaseSafety.setUp
    run_ps=release.ReleaseSafety.run_ps
    script=release.ReleaseSafety.script

    def setUp(self) -> None:
        self.setUp_base()
        from render_engine.paths import CODE_FILES
        for name in (*paths.PACKAGE_FILES,*(n for n in CODE_FILES if n.endswith('.py'))):
            target=self.root/name;target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(ROOT/name,target)

    def test_package_contains_backend_sql_and_imports_asgi_from_extracted_install(self) -> None:
        for name in ('backend/api/private.json','backend/cli/.env','backend/services/video.mp4','backend/database/migrations/private.sql'):
            (self.root/name).write_bytes(b'synthetic private file')
        result=self.run_ps('& '+self.script('build.ps1'));self.assertEqual(result.returncode,0,result.stderr)
        package=next((self.root/'release/out').glob('burnroom-deploy-package-*.tar.gz'));extracted=self.root/'extracted'
        with tarfile.open(package) as archive:
            names=set(archive.getnames())
            for name in paths.PACKAGE_FILES:self.assertIn('burnroom-deploy-package/'+name,names)
            for name in ('backend/api/private.json','backend/cli/.env','backend/services/video.mp4','backend/database/migrations/private.sql'):
                self.assertNotIn('burnroom-deploy-package/'+name,names)
            archive.extractall(extracted,filter='data')
        installed=extracted/'burnroom-deploy-package';outside=self.root/'outside';outside.mkdir()
        code=f'''import importlib
from pathlib import Path
from fastapi.testclient import TestClient
from backend.paths import project_root,migration_files,legacy_render_script
root=Path({str(installed)!r}).resolve()
assert project_root()==root
assert migration_files()==(root/'backend/database/migrations/001_rooms.sql',)
assert legacy_render_script()==root/'render_engine/legacy/F8_blender_render.py'
for name,group in {paths.MODULE_LOCATIONS!r}.items():
    assert Path(importlib.import_module('backend.'+group.replace('/','.')+'.'+name).__file__).resolve().is_relative_to(root)
from backend.api.main import app
assert TestClient(app).get('/').status_code==200
print('packaged backend verified',flush=True)
'''
        self.assertIn('packaged backend verified',python(code,outside,installed).stdout)

    def test_missing_backend_source_stops_packaging(self) -> None:
        (self.root/'backend/api/room_api.py').unlink()
        self.assertNotEqual(self.run_ps('& '+self.script('build.ps1')).returncode,0)
        self.assertEqual(list((self.root/'release/out').glob('*.tar.gz')),[])

    def test_missing_or_drifted_sql_stops_packaging(self) -> None:
        file=self.root/'backend/database/migrations/001_rooms.sql';file.write_bytes(file.read_bytes()+b' ')
        self.assertNotEqual(self.run_ps('& '+self.script('build.ps1')).returncode,0)
        file.unlink()
        self.assertNotEqual(self.run_ps('& '+self.script('build.ps1')).returncode,0)
        self.assertEqual(list((self.root/'release/out').glob('*.tar.gz')),[])


class DeploymentContracts(unittest.TestCase):
    def test_docker_context_includes_backend_sources_and_only_baseline_sql(self) -> None:
        rules=(ROOT/'.dockerignore').read_text().splitlines()
        self.assertIn('!backend/**/*.py',rules)
        self.assertIn('!backend/database/migrations/001_rooms.sql',rules)
        self.assertNotIn('!backend/**',rules)
        self.assertNotIn('!backend/database/migrations/*.sql',rules)
        self.assertTrue((ROOT/'deploy/scripts/build.ps1').read_bytes().startswith(b'\xef\xbb\xbf'))

    def test_uvicorn_entry_stays_app_main_and_watches_new_backend_directory(self) -> None:
        line=next(line for line in (ROOT/'Dockerfile').read_text(encoding='utf-8').splitlines() if line.startswith('CMD '))
        command=json.loads(line[4:])
        self.assertEqual(command[:2],['uvicorn','backend.api.main:app'])
        self.assertNotIn('/app/app',command);self.assertIn('/app/backend',command);self.assertIn('/app/render_engine',command)
