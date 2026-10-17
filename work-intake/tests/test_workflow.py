import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('workflow', ROOT / 'workflow.py')
workflow = importlib.util.module_from_spec(spec); spec.loader.exec_module(workflow)


def schedule(**kwargs):
    req = {'action': 'schedule', 'supported': True, 'approved': False,
           'proposal': {'topic': '公開の研究情報', 'schedule': 'weekly Monday 09:00',
                        'timezone': 'Asia/Tokyo', 'output_language': 'ja',
                        'source_scope': 'Official public research and source links'}}
    req.update(kwargs)
    return req


class HostWorkflowTests(unittest.TestCase):
    def test_weekly_summary_needs_real_host_receipt(self):
        req = schedule()
        self.assertEqual(workflow.handle(req)['state'], 'awaiting_user_choice')
        req['approved'] = True
        self.assertEqual(workflow.handle(req)['state'], 'ready_for_host_action')
        req['receipt'] = {'id': 'synthetic-task', 'enabled': True,
                          'schedule': req['proposal']['schedule'], 'timezone': 'Asia/Tokyo'}
        result = workflow.handle(req)
        self.assertEqual(result['state'], 'host_reported_active')
        self.assertTrue(result['validation_only'])
        self.assertFalse(result['performed'])

    def test_unavailable_scheduler_is_never_reported_as_started(self):
        self.assertEqual(workflow.handle(schedule(supported=False, approved=True))['state'], 'unavailable')
        self.assertEqual(workflow.handle(schedule(supported=None))['state'], 'discover_host_capability')

    def test_incomplete_schedule_does_not_trigger_scope_questionnaire(self):
        result = workflow.handle(schedule(approved=True, proposal={'topic': '公開研究'}))
        self.assertEqual(result['state'], 'draft')
        self.assertEqual(result['next_action'], 'prepare_concrete_proposal')

    def test_disabled_or_mismatched_schedule_is_not_active(self):
        req = schedule(approved=True)
        req['receipt'] = {'id': 'test', 'enabled': False, 'schedule': req['proposal']['schedule'], 'timezone': 'Asia/Tokyo'}
        self.assertEqual(workflow.handle(req)['state'], 'not_active')
        req['receipt'].update(enabled=True, timezone='UTC')
        self.assertEqual(workflow.handle(req)['state'], 'needs_review')

    def test_connection_discovery_and_existing_access(self):
        req = {'action': 'connection', 'tool': 'synthetic-notes'}
        self.assertEqual(workflow.handle(req)['state'], 'discover_host_capability')
        req['supported'] = True
        self.assertEqual(workflow.handle(req)['state'], 'awaiting_user_choice')
        req['receipt'] = {'id': 'existing-synthetic-connection', 'connected': True}
        self.assertEqual(workflow.handle(req)['state'], 'host_reported_connected')

    def test_consent_is_not_a_fake_connection_result(self):
        req = {'action': 'connection', 'tool': 'synthetic-notes', 'supported': True, 'approved': True}
        self.assertEqual(workflow.handle(req)['state'], 'ready_for_host_action')
        req['receipt'] = {'id': 'failed-test', 'connected': False}
        self.assertEqual(workflow.handle(req)['state'], 'not_active')

    def test_bad_receipts_or_schema_are_rejected(self):
        for changes in ({'supported': 'yes'}, {'approved': 'yes'}, {'receipt': {'id': 'test', 'enabled': 'yes'}}, {'proposal': {'secret': 'x'}}):
            with self.assertRaises(workflow.WorkflowError): workflow.handle(schedule(**changes))
