import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from test_recommend import request, existing, recommend

ROOT = Path(__file__).resolve().parents[1]


class HostCompatibilityTests(unittest.TestCase):
    def test_claude_adapters_resolve_to_canonical_packages(self):
        for name in ('work-intake', 'work-context', 'company-research', 'find-capabilities'):
            adapter = ROOT / '.claude/skills' / name / 'SKILL.md'
            content = adapter.read_text()
            target = re.search(r'`(../../../.agents/skills/[^`]+/SKILL.md)`', content).group(1)
            self.assertEqual((adapter.parent / target).resolve(),
                             ROOT / '.agents/skills' / name / 'SKILL.md')
            self.assertIn('name: ' + name, content)
            self.assertTrue((adapter.parent / target).is_file())

    def test_claude_imports_shared_project_instructions(self):
        self.assertIn('@AGENTS.md', (ROOT / 'CLAUDE.md').read_text())

    def test_recommendation_uses_actual_host_not_codex_constant(self):
        req = request(); req['pool']['host'] = 'Claude Code'
        tool = existing(); tool['observation']['host'] = 'Claude Code'
        req['available_tools'] = [tool]
        result = recommend.handle(req)
        self.assertEqual(result['host'], 'Claude Code')
        self.assertEqual(result['selection']['state'], 'use_existing')
        self.assertEqual(result['selection']['observation']['host'], 'Claude Code')

    def test_helper_can_run_from_another_working_directory(self):
        script = ROOT / '.agents/skills/work-context/scripts/research.py'
        payload = json.dumps({'action': 'plan', 'context': {'audience': 'worker'}}).encode()
        with tempfile.TemporaryDirectory() as directory:
            p = subprocess.run([sys.executable, '-B', str(script)], input=payload,
                               cwd=directory, capture_output=True)
        self.assertEqual(p.returncode, 0)
        self.assertTrue(json.loads(p.stdout)['ok'])


if __name__ == '__main__': unittest.main()
