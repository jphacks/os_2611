import importlib.util
from pathlib import Path
import tempfile
import unittest
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / 'launch.py'
if not LAUNCHER.exists(): LAUNCHER = ROOT.parent / '.launcher/launch.py'
spec = importlib.util.spec_from_file_location('launcher', LAUNCHER)
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


class LaunchTests(unittest.TestCase):
    def test_codex_encodes_space_unicode_and_shell_characters(self):
        root = Path('/tmp/test folder/日本語/$draft`text`')
        p = launcher.plan('codex', root, 'zh', platform='darwin')
        parsed = urlsplit(p['command'][-1]); query = parse_qs(parsed.query)
        self.assertEqual(parsed.scheme, 'codex')
        self.assertEqual(query['path'], [str(root)])
        self.assertEqual(query['prompt'], [p['prompt']])
        self.assertTrue(p['requires_send'])
        self.assertEqual(p['command'][0], '/usr/bin/open')

    def test_claude_uses_interactive_prompt_without_permission_override(self):
        p = launcher.plan('claude', Path('/tmp/test space'), 'ja', claude='/test path/claude')
        self.assertEqual(p['command'], ['/test path/claude', p['prompt']])
        self.assertNotIn('--dangerously-skip-permissions', p['command'])
        self.assertNotIn('-p', p['command'])

    def test_packaged_workspace_is_relative_not_developer_path(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); app = root / 'app'
            (app / '.agents/skills/work-intake/scripts').mkdir(parents=True)
            for name in ['AGENTS.md', 'CLAUDE.md', '.agents/skills/work-intake/scripts/intake.py']:
                (app / name).write_text('test')
            self.assertEqual(launcher.workspace(root / '.launcher/launch.py'), app.resolve())

    def test_incomplete_package_is_a_clear_error(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError, 'incomplete_package'):
                launcher.workspace(Path(d) / '.launcher/launch.py')

    def test_no_auto_submission_or_installer_in_codex_url(self):
        p = launcher.plan('codex', Path('/tmp/test'), 'ja', platform='darwin')
        self.assertEqual(set(parse_qs(urlsplit(p['command'][-1]).query)), {'path', 'prompt'})
        self.assertIn('Before saving personal facts', p['prompt'])

    def test_source_workspace_remains_supported(self):
        self.assertEqual(launcher.workspace(LAUNCHER), ROOT.resolve())

    def test_launch_prioritizes_existing_memory_instead_of_resetting_user(self):
        p = launcher.prompt('zh')
        self.assertIn('saved local profile', p)
        self.assertIn('available memory search tools', p)
        self.assertNotIn('Treat me as a new user', p)
        self.assertIn('Never restart the occupation questionnaire', p)


if __name__ == '__main__': unittest.main()

class AutomaticLaunchTests(unittest.TestCase):
    def test_system_languages_are_not_limited_to_author_language(self):
        from unittest.mock import patch
        import subprocess
        for tag in ('ja-JP', 'ko-KR', 'zh-Hans-CN', 'en-US', 'fr-FR'):
            result = subprocess.CompletedProcess([], 0, '(\n    "' + tag + '"\n)')
            with patch.object(launcher.sys, 'platform', 'darwin'), patch.object(launcher.subprocess, 'run', return_value=result):
                self.assertEqual(launcher.language(), tag)
                self.assertIn('Initial system language: ' + tag, launcher.prompt(tag))

    def test_environment_locale_fallback(self):
        from unittest.mock import patch
        for value, expected in [('ja_JP.UTF-8', 'ja-JP'), ('ko_KR.UTF-8', 'ko-KR'), ('C.UTF-8', 'en')]:
            with patch.object(launcher.sys, 'platform', 'linux'), patch.dict(launcher.os.environ, {'LANG': value}, clear=True):
                self.assertEqual(launcher.language(), expected)

    def test_host_detection_choices(self):
        self.assertEqual(launcher.choose_host(['codex']), 'codex')
        self.assertEqual(launcher.choose_host(['claude']), 'claude')
        self.assertIsNone(launcher.choose_host(['codex', 'claude']))
        self.assertEqual(launcher.choose_host(['codex', 'claude'], 'claude'), 'claude')
        self.assertEqual(launcher.choose_host(['codex'], 'claude'), 'codex')
        with self.assertRaisesRegex(ValueError, 'no_host'): launcher.choose_host([])

    def test_host_choice_is_separate_from_personal_profile(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            launcher.save_host(root, 'claude')
            self.assertEqual(launcher.remembered_host(root), 'claude')
            self.assertEqual(set((root / '.private').iterdir()), {root / '.private/launcher.json'})

    def test_host_memory_does_not_follow_symlink(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); target = root / 'other'; target.mkdir()
            (root / '.private').symlink_to(target, target_is_directory=True)
            launcher.save_host(root, 'claude')
            self.assertIsNone(launcher.remembered_host(root))
            self.assertEqual(list(target.iterdir()), [])

    def test_launcher_messages_follow_locale_tag(self):
        self.assertIn('選択', launcher.message('choose_host', 'ja-JP'))
        self.assertIn('선택', launcher.message('choose_host', 'ko-KR'))
        self.assertIn('请选择', launcher.message('choose_host', 'zh-Hans'))


class CodexRouteTests(unittest.TestCase):
    def test_cli_only_machine_uses_interactive_existing_codex(self):
        from unittest.mock import patch
        with patch.object(launcher, 'codex_available', return_value=False), patch.object(launcher, 'codex_app', return_value=None):
            p = launcher.plan('codex', Path('/tmp/test folder'), 'ja', platform='darwin', codex_cli='/usr/local/bin/codex')
        self.assertEqual(p['command'], ['/usr/local/bin/codex', p['prompt']])
        self.assertFalse(p['requires_send'])

    def test_known_desktop_app_is_targeted_directly(self):
        p = launcher.plan('codex', Path('/tmp/test'), 'ja', platform='darwin', desktop_app='/Applications/Codex.app')
        self.assertEqual(p['command'][:3], ['/usr/bin/open', '-a', '/Applications/Codex.app'])
        self.assertTrue(p['command'][3].startswith('codex://threads/new?'))

    def test_failed_desktop_request_falls_back_without_installing(self):
        from unittest.mock import patch
        import subprocess
        p = {'command': ['/usr/bin/open', 'codex://test'], 'cwd': '/tmp', 'prompt': 'synthetic', 'requires_send': True}
        with patch.object(launcher, 'codex_executable', return_value='/usr/local/bin/codex'), patch.object(launcher.subprocess, 'run', side_effect=[subprocess.CompletedProcess([], 1), subprocess.CompletedProcess([], 0)]) as run, patch('builtins.print'):
            result = launcher.execute(p, 'ja')
        self.assertEqual(result.returncode, 0)
        self.assertEqual(run.call_args.args[0], ['/usr/local/bin/codex', 'synthetic'])
        self.assertFalse(p['requires_send'])

    def test_cli_in_standard_intel_location_counts_as_installed(self):
        from unittest.mock import patch
        with patch.object(launcher, 'codex_available', return_value=False), patch.object(launcher, 'codex_app', return_value=None), patch.object(launcher, 'codex_executable', return_value='/usr/local/bin/codex'):
            self.assertTrue(launcher.codex_detected())

class WorkDirectoryTests(unittest.TestCase):
    def test_actual_work_directory_is_distinct_from_installation(self):
        root=Path('/tmp/assistant package')
        target=Path('/tmp/用户 work')
        p=launcher.plan('codex',root,'zh',platform='darwin',work_root=target)
        q=parse_qs(urlsplit(p['command'][-1]).query)
        self.assertEqual(Path(q['path'][0]),target.resolve())
        self.assertIn(str(root/'AGENTS.md'),p['prompt'])
        self.assertIn('not yet linked',launcher.prompt('zh',root,None))

    def test_active_task_directory_is_recovered_without_scanning_history(self):
        import json,sqlite3
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); state=root/'.private';state.mkdir(); work=root/'工作';work.mkdir()
            with sqlite3.connect(state/'work.sqlite3') as db:
                db.executescript('CREATE TABLE tasks(id TEXT, document TEXT); CREATE TABLE settings(key TEXT,value TEXT);')
                db.execute('INSERT INTO tasks VALUES (?,?)',('t',json.dumps({'root':str(work)})))
                db.execute('INSERT INTO settings VALUES (?,?)',('active','t'))
            self.assertEqual(launcher.remembered_workspace(root),work.resolve())
