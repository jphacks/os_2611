"""Behavioral invariants with real file/process I/O, not prompt-string assertions."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from work import Controller
from workstate import WorkError, digest


class WorkRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name).resolve()
        self.root = self.base / '工作 files'; self.root.mkdir()
        self.state = self.base / 'state'
        self.c = Controller(self.state)
        self.task = self.c.handle({'action': 'create', 'root': str(self.root), 'goal': '整理实际材料',
                                  'output': 'summary.md', 'criteria': ['包含已确认结果']})['task']

    def tearDown(self):
        self.c.close(); self.tmp.cleanup()

    def call(self, action, **kwargs):
        return self.c.handle(dict(action=action, **kwargs))

    def grant(self, tool, **selector):
        return self.call('grant', tool=tool, selector=selector, basis='User requested this exact local test task')

    def act(self, tool, **args):
        return self.call('act', tool=tool, args=args, why='Complete the current work using actual I/O')

    def output(self):
        self.grant('write', path='summary.md')
        return self.act('write', path='summary.md', content='confirmed result\n')

    def verify(self):
        return self.act('verify', checks=[{'path': 'summary.md', 'contains': ['confirmed result']}])['operation']['id']

    def test_actual_write_verify_resume_and_complete(self):
        self.output(); verification = self.verify()
        self.c.close(); self.c = Controller(self.state)
        resumed = self.call('resume')
        self.assertEqual(resumed['task']['id'], self.task['id'])
        self.call('complete', summary='Actual file verified', verification_ids=[verification])
        self.assertTrue(self.call('snapshot')['completion_current'])

    def test_external_artifact_change_blocks_completion(self):
        self.output(); verification = self.verify()
        (self.root / 'summary.md').write_text('changed')
        with self.assertRaisesRegex(WorkError, 'artifact_changed'):
            self.call('complete', summary='wrong', verification_ids=[verification])

    def test_resume_invalidates_completed_output_changed_outside_runtime(self):
        self.output(); verification = self.verify()
        self.call('complete',summary='done',verification_ids=[verification])
        (self.root/'summary.md').write_text('changed outside runtime')
        self.assertFalse(self.call('resume')['completion_current'])

    def test_changed_material_is_detected_across_restart(self):
        (self.root/'input.txt').write_text('old')
        self.grant('read', paths=['input.txt']); self.act('read', paths=['input.txt'])
        (self.root/'input.txt').write_text('new')
        self.c.close(); self.c = Controller(self.state)
        self.assertEqual(self.call('resume')['material_changes'][0]['state'], 'changed')
        self.act('read', paths=['input.txt'])
        self.assertEqual(self.call('snapshot')['material_changes'], [])

    def test_no_arbitrary_success_flag_or_host_receipt_completes_task(self):
        self.call('observe', tool='fake service', scope='test only', summary='connected:true', reference='caller supplied')
        with self.assertRaisesRegex(WorkError, 'unverified_completion'):
            self.call('complete', summary='invented', verification_ids=['made-up'])
        self.assertEqual(self.call('snapshot')['task']['capabilities'][0]['verification'], 'not_independently_verified')

    def test_authorization_is_exact_and_reused_after_restart(self):
        with self.assertRaisesRegex(WorkError, 'scope_not_authorized'):
            self.act('write', path='summary.md', content='no')
        self.output()
        self.c.close(); self.c = Controller(self.state)
        h = digest((self.root/'summary.md').read_bytes())
        self.act('write', path='summary.md', content='updated', expected_sha256=h)
        with self.assertRaisesRegex(WorkError, 'scope_not_authorized'):
            self.act('write', path='elsewhere.md', content='no')

    def test_overwrite_requires_observed_content_hash(self):
        self.output()
        r = self.act('write', path='summary.md', content='not authorized overwrite')
        self.assertEqual(r['operation']['payload']['status'], 'failed')
        self.assertEqual((self.root/'summary.md').read_text(), 'confirmed result\n')

    def test_real_command_exit_code_and_failure_are_recorded(self):
        argv = [sys.executable, '-c', 'print("actual execution"); raise SystemExit(7)']
        self.grant('run', argv=argv)
        result = self.act('run', argv=argv)
        self.assertEqual(result['operation']['payload']['status'], 'failed')
        self.assertEqual(result['output']['returncode'], 7)
        self.assertIn('actual execution', result['output']['stdout'])
        with self.assertRaisesRegex(WorkError, 'duplicate_action'):
            self.act('run', argv=argv)

    def test_process_timeout_is_real_and_recoverable(self):
        argv=[sys.executable, '-c', 'import time; time.sleep(3)']
        self.grant('run', argv=argv)
        result = self.act('run', argv=argv, timeout=1)
        self.assertTrue(result['output']['timed_out'])
        self.assertEqual(result['operation']['payload']['status'], 'failed')

    def test_questions_do_not_repeat_and_have_consequence(self):
        self.call('question', key='delivery', question='交付时间？', why='决定本次周报的日期范围')
        self.call('answer', key='delivery', answer='本周')
        with self.assertRaisesRegex(WorkError, 'question_already_asked'):
            self.call('question', key='delivery', question='再问一次', why='repeat')

    def test_tasks_switch_without_leaking_context(self):
        self.call('reflect', item={'kind':'user_statement','text':'Only task one'})
        other = self.call('create', root=str(self.root),goal='second',output='other',criteria=['different'])['task']
        self.assertEqual(other['understanding'], [])
        self.assertEqual(self.call('resume', task_id=self.task['id'])['task']['understanding'][0]['text'],'Only task one')

    def test_pause_prevents_actions_and_forget_preserves_workspace(self):
        self.output(); self.call('pause')
        with self.assertRaisesRegex(WorkError, 'task_paused'): self.verify()
        self.call('resume'); self.call('forget', confirmed=True)
        self.assertTrue((self.root/'summary.md').is_file())
        self.assertEqual(self.call('list')['tasks'], [])

    def test_path_escape_and_private_files_are_not_read(self):
        (self.base/'secret.txt').write_text('secret')
        self.grant('read', paths=['../secret.txt'])
        self.assertEqual(self.act('read', paths=['../secret.txt'])['operation']['payload']['error'], 'outside_work_scope')
        (self.root/'escape.txt').symlink_to(self.base/'secret.txt')
        self.grant('read', paths=['escape.txt'])
        self.assertEqual(self.act('read', paths=['escape.txt'])['operation']['payload']['error'], 'outside_work_scope')

    def test_interrupted_operation_is_not_replayed_or_called_successful(self):
        e = self.c.journal.add(self.task['id'],'attempt',{'tool':'write','args':{'path':'summary.md'},'fingerprint':'x'})
        self.assertEqual(len(self.call('resume')['interrupted_attempts']),1)
        self.call('resolve_interrupted',attempt_id=e['id'],review='Reviewed disk; no file created')
        self.assertEqual(self.call('resume')['interrupted_attempts'],[])
        self.assertEqual(self.c.journal.events(self.task['id'])[-1]['payload']['status'],'reviewed_unknown')

    def test_changed_goal_requires_new_verification(self):
        self.output(); v=self.verify()
        self.call('update',changes={'goal':'A new goal'})
        with self.assertRaisesRegex(WorkError,'new_work_since_verification'):
            self.call('complete',summary='stale',verification_ids=[v])

    def test_revision_conflict_does_not_overwrite(self):
        self.call('update',changes={'goal':'first'})
        with self.assertRaisesRegex(WorkError,'revision_conflict'):
            self.call('update',expected_revision=0,changes={'goal':'stale'})
        self.assertEqual(self.call('snapshot')['task']['goal'],'first')

    def test_csv_verification_compares_actual_rows(self):
        (self.root/'data.csv').write_text('name,total\na,3\nb,5\n')
        result=self.act('verify',checks=[{'path':'data.csv','csv_columns':['name','total'],
                            'csv_rows':[{'name':'a','total':'3'},{'name':'b','total':'5'}]}])
        self.assertTrue(result['output']['passed'])
        result=self.act('verify',checks=[{'path':'data.csv','csv_rows':[]}])
        self.assertFalse(result['output']['passed'])

    def test_network_unavailable_preserves_progress(self):
        # Network failure branch is tested without pretending to have a live connection.
        from unittest.mock import patch
        self.grant('fetch',url='https://example.org/public')
        with patch('worktools.socket.getaddrinfo',side_effect=OSError()):
            r=self.act('fetch',url='https://example.org/public')
        self.assertEqual(r['operation']['payload']['status'],'blocked')
        self.assertEqual(self.call('snapshot')['task']['goal'],'整理实际材料')

    def test_private_network_destination_is_rejected(self):
        self.grant('fetch',url='https://127.0.0.1/')
        result=self.act('fetch',url='https://127.0.0.1/')
        self.assertEqual(result['operation']['payload']['error'],'non_public_destination')

    def test_checkpoints_branch_reasoning_without_regranting_or_replaying(self):
        self.grant('write',path='summary.md')
        checkpoint=self.call('checkpoint',reason='Before trying an alternative')['event']
        self.call('revoke',grant_id=self.call('snapshot')['task']['grants'][0]['id'])
        self.call('update',changes={'goal':'Alternative approach'})
        self.call('restore_checkpoint',checkpoint_id=checkpoint['id'],reason='Alternative did not fit')
        task=self.call('snapshot')['task']
        self.assertEqual(task['goal'],'整理实际材料')
        self.assertEqual(task['grants'],[])
        self.assertFalse((self.root/'summary.md').exists())


if __name__ == '__main__': unittest.main()
