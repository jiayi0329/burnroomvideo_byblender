"""PRD 2.1 / architecture 2.3: release packaging and fail-fast behavior.

Local PowerShell/tar subprocesses in temporary fixture directories only.
Never runs Docker, real SSH/SCP, Blender or a server.
Run: python -m unittest tests.deploy.test_release_safety -v
"""
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import unittest
from render_engine.paths import CODE_FILES
from backend.paths import PACKAGE_FILES
from tests.tool_paths import DIAGNOSTIC_FILES
from tests.suites import PACKAGE_FILES as TEST_ENTRY_FILES

ROOT = Path(__file__).resolve().parents[2]


@unittest.skipUnless(shutil.which('powershell.exe') and shutil.which('tar'), 'Windows PowerShell and tar required')
class ReleaseSafety(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        scripts = self.root / 'deploy/scripts'
        scripts.mkdir(parents=True)
        for name in ('build.ps1', 'deploy.ps1', 'prepare_deploy.sh'):
            shutil.copyfile(ROOT / 'deploy/scripts' / name, scripts / name)
        for name, content in {
            'Dockerfile': 'COPY . .', 'requirements.txt': '', 'docs/database.md': 'synthetic',
            'tests/test_synthetic.py': '',
            'deploy/docker-compose.prod.yml': 'services: {}', 'deploy/prod.env.example': 'PLACEHOLDER=1',
            'deploy/docker-compose.gpu.yml': 'services: {}',
            '.env': 'SYNTHETIC_SECRET=not-production', 'prod.env': 'SYNTHETIC_SECRET=not-production',
            'tests/prod.env': 'SYNTHETIC_SECRET=not-production',
        }.items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding='utf-8')
        for relative in CODE_FILES:
            path = self.root / relative
            if not path.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('# synthetic engine fixture', encoding='utf-8')
        for revision in (1, 2, 3):
            relative = f'configs/render/room_fire_round{revision}.json'
            shutil.copyfile(ROOT/relative, self.root/relative)
        for relative in PACKAGE_FILES:
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('# synthetic backend fixture', encoding='utf-8')
        shutil.copyfile(ROOT/'backend/database/migrations/001_rooms.sql', self.root/'backend/database/migrations/001_rooms.sql')
        for relative in DIAGNOSTIC_FILES:
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('# synthetic diagnostic fixture', encoding='utf-8')
        for relative in TEST_ENTRY_FILES:
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, path)
        shutil.copyfile(ROOT / '.dockerignore', self.root / '.dockerignore')

    def run_ps(self, command: str) -> subprocess.CompletedProcess:
        return subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', command],
                              capture_output=True, timeout=40)

    def script(self, name: str) -> str:
        return "'" + str(self.root / 'deploy/scripts' / name).replace("'", "''") + "'"

    def test_package_contains_ignore_and_preserves_old_packages(self) -> None:
        out = self.root / 'release/out'
        out.mkdir(parents=True)
        previous = out / 'previous.tar.gz'
        previous.write_bytes(b'old package')
        result = self.run_ps('& ' + self.script('build.ps1'))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(previous.read_bytes(), b'old package')
        package = next(out.glob('burnroom-deploy-package-*.tar.gz'))
        with tarfile.open(package) as archive:
            names = set(archive.getnames())
            self.assertIn('burnroom-deploy-package/.dockerignore', names)
            self.assertIn('burnroom-deploy-package/backend/database/migrations/001_rooms.sql', names)
            self.assertIn('burnroom-deploy-package/render_engine/blender/F8_room_helpers.py', names)
            self.assertNotIn('burnroom-deploy-package/.env', names)
            self.assertNotIn('burnroom-deploy-package/prod.env', names)
            self.assertNotIn('burnroom-deploy-package/app/.env', names)
            self.assertNotIn('burnroom-deploy-package/tests/prod.env', names)

    def test_tar_failure_stops_build(self) -> None:
        command = "function tar { $global:LASTEXITCODE = 7 }; try { & " + self.script('build.ps1') + "; exit 2 } catch { if ($_.Exception.Message -like 'tar *') { exit 0 }; exit 3 }"
        self.assertEqual(self.run_ps(command).returncode, 0)
        self.assertEqual(list((self.root / 'release/out').glob('*.tar.gz')), [])

    def test_ssh_failure_stops_before_upload(self) -> None:
        out = self.root / 'release/out'
        out.mkdir(parents=True)
        (out / 'burnroom-deploy-package-test.tar.gz').write_bytes(b'synthetic')
        command = "function ssh { $global:LASTEXITCODE = 19 }; function scp { throw 'unexpected SCP' }; try { & " + self.script('deploy.ps1') + "; exit 2 } catch { if ($_.Exception.Message -like '*停止部署') { exit 0 }; exit 3 }"
        self.assertEqual(self.run_ps(command).returncode, 0)

    def test_backup_failure_stops_before_extraction(self) -> None:
        out = self.root / 'release/out'
        out.mkdir(parents=True)
        (out / 'burnroom-deploy-package-test.tar.gz').write_bytes(b'synthetic')
        command = "$global:sshCalls=0; function ssh { $global:sshCalls++; $global:LASTEXITCODE=0; if ($global:sshCalls -eq 2) { $global:LASTEXITCODE=9 } }; function scp { $global:LASTEXITCODE=0 }; try { & " + self.script('deploy.ps1') + "; exit 2 } catch { if ($global:sshCalls -eq 2 -and $_.Exception.Message -like '*未解压覆盖代码') { exit 0 }; exit 3 }"
        self.assertEqual(self.run_ps(command).returncode, 0)


class DockerContextPolicy(unittest.TestCase):
    def test_default_deny_secrets_and_private_data(self) -> None:
        rules = [line.strip() for line in (ROOT / '.dockerignore').read_text().splitlines() if line.strip() and not line.startswith('#')]
        self.assertEqual(rules[0], '**')
        self.assertIn('!backend/**/*.py', rules)
        self.assertIn('**/.env', rules)
        self.assertIn('**/prod.env', rules)
        for private in ('!data/', '!data/**', '!.env', '!prod.env', '!release/'):
            self.assertNotIn(private, rules)
