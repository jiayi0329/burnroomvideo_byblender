"""PRD 2.1 / architecture 2.3: release packaging and fail-fast behavior.

Local PowerShell/tar subprocesses in temporary fixture directories only.
Never runs Docker, real SSH/SCP, Blender or a server.
Run: python -m unittest test.test_release_safety -v
"""
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which('powershell.exe') and shutil.which('tar'), 'Windows PowerShell and tar required')
class ReleaseSafety(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        scripts = self.root / 'release/scripts'
        scripts.mkdir(parents=True)
        for name in ('build.ps1', 'deploy.ps1', 'prepare_deploy.sh'):
            shutil.copyfile(ROOT / 'release/scripts' / name, scripts / name)
        for name, content in {
            'app/source.py': 'print("synthetic")', 'app/db/001.sql': 'SELECT 1;',
            'Dockerfile': 'COPY . .', 'requirements.txt': '', 'docs/database.md': 'synthetic',
            'test/__init__.py': '', 'test/test_synthetic.py': '',
            'release/docker-compose.prod.yml': 'services: {}', 'release/prod.env.example': 'PLACEHOLDER=1',
            '.env': 'SYNTHETIC_SECRET=not-production', 'prod.env': 'SYNTHETIC_SECRET=not-production',
            'app/.env': 'SYNTHETIC_SECRET=not-production', 'test/prod.env': 'SYNTHETIC_SECRET=not-production',
        }.items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding='utf-8')
        shutil.copyfile(ROOT / '.dockerignore', self.root / '.dockerignore')

    def run_ps(self, command: str) -> subprocess.CompletedProcess:
        return subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', command],
                              capture_output=True, timeout=40)

    def script(self, name: str) -> str:
        return "'" + str(self.root / 'release/scripts' / name).replace("'", "''") + "'"

    def test_package_contains_ignore_and_preserves_old_packages(self) -> None:
        out = self.root / 'release/out'
        out.mkdir()
        previous = out / 'previous.tar.gz'
        previous.write_bytes(b'old package')
        result = self.run_ps('& ' + self.script('build.ps1'))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(previous.read_bytes(), b'old package')
        package = next(out.glob('burnroom-deploy-package-*.tar.gz'))
        with tarfile.open(package) as archive:
            names = set(archive.getnames())
            self.assertIn('burnroom-deploy-package/.dockerignore', names)
            self.assertIn('burnroom-deploy-package/app/db/001.sql', names)
            self.assertNotIn('burnroom-deploy-package/.env', names)
            self.assertNotIn('burnroom-deploy-package/prod.env', names)
            self.assertNotIn('burnroom-deploy-package/app/.env', names)
            self.assertNotIn('burnroom-deploy-package/test/prod.env', names)

    def test_tar_failure_stops_build(self) -> None:
        command = "function tar { $global:LASTEXITCODE = 7 }; try { & " + self.script('build.ps1') + "; exit 2 } catch { if ($_.Exception.Message -like 'tar *') { exit 0 }; exit 3 }"
        self.assertEqual(self.run_ps(command).returncode, 0)
        self.assertEqual(list((self.root / 'release/out').glob('*.tar.gz')), [])

    def test_ssh_failure_stops_before_upload(self) -> None:
        out = self.root / 'release/out'
        out.mkdir()
        (out / 'burnroom-deploy-package-test.tar.gz').write_bytes(b'synthetic')
        command = "function ssh { $global:LASTEXITCODE = 19 }; function scp { throw 'unexpected SCP' }; try { & " + self.script('deploy.ps1') + "; exit 2 } catch { if ($_.Exception.Message -like '*停止部署') { exit 0 }; exit 3 }"
        self.assertEqual(self.run_ps(command).returncode, 0)

    def test_backup_failure_stops_before_extraction(self) -> None:
        out = self.root / 'release/out'
        out.mkdir()
        (out / 'burnroom-deploy-package-test.tar.gz').write_bytes(b'synthetic')
        command = "$global:sshCalls=0; function ssh { $global:sshCalls++; $global:LASTEXITCODE=0; if ($global:sshCalls -eq 2) { $global:LASTEXITCODE=9 } }; function scp { $global:LASTEXITCODE=0 }; try { & " + self.script('deploy.ps1') + "; exit 2 } catch { if ($global:sshCalls -eq 2 -and $_.Exception.Message -like '*未解压覆盖代码') { exit 0 }; exit 3 }"
        self.assertEqual(self.run_ps(command).returncode, 0)


class DockerContextPolicy(unittest.TestCase):
    def test_default_deny_secrets_and_private_data(self) -> None:
        rules = [line.strip() for line in (ROOT / '.dockerignore').read_text().splitlines() if line.strip() and not line.startswith('#')]
        self.assertEqual(rules[0], '**')
        self.assertIn('!app/**', rules)
        self.assertIn('**/.env', rules)
        self.assertIn('**/prod.env', rules)
        for private in ('!data/', '!data/**', '!.env', '!prod.env', '!release/'):
            self.assertNotIn(private, rules)
