import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('environment', ROOT / 'environment.py')
env = importlib.util.module_from_spec(spec); spec.loader.exec_module(env)


class EnvironmentTests(unittest.TestCase):
    def test_installed_apps_is_bounded_and_does_not_read_contents(self):
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d)
            for name in ('Codex.app', 'Excel.app', 'UnknownPersonalApp.app', 'Passwords.app'):
                (folder / name).mkdir()
            (folder / 'private-note.txt').write_text('not inspected')
            self.assertEqual(env.installed_apps([folder]), ['Codex', 'Excel'])

    def test_inventory_never_claims_common_usage(self):
        with patch.object(env.platform, 'system', return_value='Linux'), patch.object(env.shutil, 'which', side_effect=lambda x: '/bin/' + x if x == 'python3' else None):
            report = env.collect(ROOT)
        self.assertIsNone(report['frequent_tools'])
        self.assertEqual(report['installed_commands'], ['python3'])
        self.assertNotIn(str(Path.home()), str(report))

    def test_intel_and_arm_metadata_follow_actual_machine(self):
        for arch in ('x86_64', 'arm64'):
            with patch.object(env.platform, 'system', return_value='Darwin'), patch.object(env.platform, 'machine', return_value=arch), patch.object(env, 'read_os_value', side_effect=lambda c: '17179869184' if c[-1] == 'hw.memsize' else 'synthetic'), patch.object(env, 'installed_apps', return_value=[]):
                report = env.collect(ROOT)
            self.assertEqual(report['hardware']['architecture'], arch)
            self.assertEqual(report['hardware']['ram_bytes'], 17179869184)
            self.assertNotIn('serial', report['hardware'])
