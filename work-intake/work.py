#!/usr/bin/env python3
"""Host-native work controller: JSON stdin, actual I/O and resumable evidence.

The host model chooses actions; this process neither pretends to be a model nor
accepts model-supplied success as verified execution. See docs/runtime.md.
"""
import argparse
import json
from pathlib import Path
import sys
from workstate import Journal, WorkError, require, text, digest, encoded, stamp
import worktools

ROOT = Path(__file__).resolve().parent
VERSION = '0.2.0'
READ_ONLY = {'snapshot', 'list', 'export', 'capabilities'}
TOOLS = {'read', 'fetch', 'write', 'run', 'verify'}


def fingerprint(tool, args):
    return digest(encoded({'tool': tool, 'args': args}).encode())


class Controller:
    def __init__(self, directory=None):
        self.journal = Journal(directory or ROOT / '.private')

    def close(self):
        self.journal.close()

    def snapshot(self, task):
        events = self.journal.events(task['id'])
        latest = {}
        for event in events:
            p = event['payload']
            if event['kind'] == 'result' and p.get('tool') == 'read' and p['status'] == 'returned':
                for item in p['result']['files']: latest[item['path']] = item['sha256']
        if task.get('completion'):
            selected = set(task['completion']['verification_ids'])
            for event in events:
                if event['id'] in selected:
                    for item in event['payload']['result']['checks']:
                        latest[item['path']] = item['sha256']
        changes = []
        for name, expected in latest.items():
            try:
                p = Path(name)
                actual = digest(p.read_bytes()) if p.stat().st_size <= worktools.MAX_FILE else None
                if actual != expected: changes.append({'path': name, 'state': 'changed'})
            except OSError:
                changes.append({'path': name, 'state': 'missing'})
        pending = {e['id']: e for e in events if e['kind'] == 'attempt'}
        for e in events:
            if e['kind'] == 'result': pending.pop(e['payload']['attempt_id'], None)
        recent = events[-30:]
        unanswered = [q for q in task['questions'] if q['status'] == 'open']
        return {'task': task, 'material_changes': changes, 'interrupted_attempts': list(pending.values()),
                'completion_current': task['status'] == 'completed' and not changes and not pending,
                'recent_events': recent, 'event_count': len(events), 'unanswered_questions': unanswered,
                'decision_context': {'goal': task['goal'], 'criteria': task['criteria'],
                    'next_actions': task['next_actions'], 'requires_model_judgment': True,
                    'available_actions': sorted(TOOLS | {'reflect', 'question', 'answer', 'observe', 'complete'}),
                    'instruction': 'Choose the next useful action from current evidence. No mandatory sequence. '
                                   'Re-read changed sources; never replay interrupted side effects blindly.'}}

    def task(self, req):
        task_id = req.get('task_id') or self.journal.active()
        require(task_id is not None, 'no_active_task')
        task = self.journal.load(task_id)
        if 'expected_revision' in req:
            require(req['expected_revision'] == task['revision'], 'revision_conflict')
        return task

    def handle(self, req):
        require(isinstance(req, dict) and text(req.get('action'), 50), 'invalid_request')
        action = req['action']
        if action == 'capabilities':
            return {'version': VERSION, 'local_tools': sorted(TOOLS), 'model': 'existing_host',
                    'direct_fetch': 'available_in_code_not_network_verified',
                    'search': 'requires_actual_host_search_tool', 'scheduler': 'requires_actual_host_tool',
                    'host_memory': 'only_if_exposed_by_host', 'extra_dependencies': [],
                    'security_boundary': 'host OS permissions; subprocess is not sandboxed by this package'}
        if action == 'list':
            return {'active_task': self.journal.active(), 'tasks': [
                {k: t[k] for k in ('id', 'root', 'goal', 'status', 'revision', 'updated_at')}
                for t in self.journal.tasks()]}
        if action == 'create':
            require(all(text(req.get(k)) for k in ('root', 'goal', 'output')), 'missing_work_context')
            root = Path(req['root']).expanduser().resolve()
            require(root.is_dir(), 'missing_work_directory')
            criteria = req.get('criteria')
            require(isinstance(criteria, list) and criteria and all(text(s) for s in criteria), 'missing_completion_criteria')
            return self.snapshot(self.journal.create(root, req['goal'], req['output'], criteria))
        task = self.task(req)
        if action in ('snapshot', 'resume'):
            if action == 'resume':
                self.journal.activate(task['id'])
                if task['status'] == 'paused':
                    task['status'] = 'working'
                    task = self.journal.save(task)
            return self.snapshot(task)
        if action == 'export':
            return {'task': task, 'events': self.journal.events(task['id']),
                    'warning': 'Private task data. Redact before sharing.'}
        if action == 'forget':
            require(req.get('confirmed') is True, 'forget_confirmation_required')
            return self.journal.forget(task['id'])
        if action == 'pause':
            task['status'] = 'paused'
            return {'task': self.journal.save(task)}
        require(task['status'] != 'paused', 'task_paused')
        if action == 'update':
            changes = req.get('changes', {})
            require(isinstance(changes, dict) and changes and set(changes) <= {'goal', 'output', 'criteria', 'next_actions'}, 'invalid_changes')
            for key, value in changes.items():
                require(text(value) if key in ('goal', 'output') else
                        isinstance(value, list) and all(text(v) for v in value), 'invalid_changes')
            task.update(changes)
            task['completion'] = None
            task['status'] = 'working'
            task = self.journal.save(task)
            self.journal.add(task['id'], 'updated', changes)
            return {'task': task}
        if action == 'reflect':
            return self.reflect(task, req)
        if action == 'checkpoint':
            require(text(req.get('reason')), 'checkpoint_reason_required')
            previous = [e for e in self.journal.events(task['id']) if e['kind'] == 'checkpoint']
            return {'event': self.journal.add(task['id'], 'checkpoint', {'reason': req['reason'],
                'parent_id': previous[-1]['id'] if previous else None, 'task': task})}
        if action == 'restore_checkpoint':
            checkpoint = next((e for e in self.journal.events(task['id'])
                               if e['id'] == req.get('checkpoint_id') and e['kind'] == 'checkpoint'), None)
            require(checkpoint is not None and text(req.get('reason')), 'checkpoint_and_reason_required')
            # Restore reasoning state only; never roll back revocations, execution records or disk.
            old = checkpoint['payload']['task']
            for key in ('goal', 'output', 'criteria', 'understanding', 'candidates', 'next_actions'):
                task[key] = old[key]
            task['status'], task['completion'] = 'working', None
            task = self.journal.save(task)
            self.journal.add(task['id'], 'updated', {'restored_checkpoint': checkpoint['id'], 'reason': req['reason']})
            return {'task': task, 'disk_rolled_back': False, 'authorization_rolled_back': False}
        if action in ('question', 'answer'):
            return self.question(task, req)
        if action in ('grant', 'revoke'):
            return self.authorization(task, req)
        if action == 'observe':
            # A host tool's report is useful evidence but NOT independently verified by Python.
            require(all(text(req.get(k)) for k in ('tool', 'scope', 'summary', 'reference')), 'invalid_observation')
            reported = {k: req[k] for k in ('tool', 'scope', 'summary', 'reference')}
            reported.update(origin='host_report', verification='not_independently_verified', at=stamp())
            task['capabilities'] = [c for c in task['capabilities'] if (c['tool'],c['scope']) != (req['tool'],req['scope'])] + [reported]
            task = self.journal.save(task)
            return {'task': task, 'event': self.journal.add(task['id'], 'host_report', reported)}
        if action == 'resolve_interrupted':
            require(text(req.get('attempt_id')) and text(req.get('review')), 'review_required')
            pending = self.snapshot(task)['interrupted_attempts']
            attempt = next((e for e in pending if e['id'] == req['attempt_id']), None)
            require(attempt is not None, 'no_interrupted_attempt')
            return {'event': self.journal.add(task['id'], 'result', {'attempt_id': attempt['id'],
                'tool': attempt['payload']['tool'], 'fingerprint': attempt['payload']['fingerprint'],
                'status': 'reviewed_unknown', 'review': req['review'],
                'next': 'Re-read outputs and independently verify before completion; do not assume success.'})}
        if action == 'act':
            return self.execute(task, req)
        if action == 'complete':
            return self.complete(task, req)
        raise WorkError('unknown_action')

    def reflect(self, task, req):
        item = req.get('item')
        require(isinstance(item, dict) and set(item) <= {'id', 'kind', 'text', 'sources', 'status', 'rationale', 'locator'}, 'invalid_reflection')
        require(text(item.get('text')) and item.get('kind') in {'user_statement','file_observation','external_finding','inference','candidate'}, 'invalid_reflection')
        sources = item.get('sources', [])
        require(isinstance(sources, list) and all(text(s) for s in sources), 'invalid_sources')
        require(item['kind'] in {'inference', 'user_statement'} or sources, 'sources_required')
        item = dict(item, id=item.get('id') or digest(item['text'].encode())[:12], recorded_at=stamp())
        key = 'candidates' if item['kind'] == 'candidate' else 'understanding'
        if key == 'candidates':
            require(item.get('status') in {'investigating','proposed','selected','rejected','integrated'}, 'invalid_candidate_status')
            require(text(item.get('rationale')) and text(item.get('locator')), 'candidate_needs_rationale_and_locator')
            # Adoption is a model judgment; execution evidence is separate.
            item['execution_verified'] = False
        task[key] = [i for i in task[key] if i['id'] != item['id']] + [item]
        require(len(task[key]) <= 200, 'summarize_state_before_adding_more')
        task = self.journal.save(task)
        return {'task': task, 'event': self.journal.add(task['id'], 'reflection', item)}

    def question(self, task, req):
        key = req.get('key')
        require(text(key, 100), 'invalid_question_key')
        previous = next((q for q in task['questions'] if q['key'] == key), None)
        if req['action'] == 'question':
            require(text(req.get('question')) and text(req.get('why')), 'question_needs_work_consequence')
            require(previous is None, 'question_already_asked_use_existing_answer')
            record = {'key': key, 'question': req['question'], 'why': req['why'], 'status': 'open'}
            task['questions'].append(record)
        else:
            require(previous is not None and previous['status'] == 'open', 'no_open_question')
            require(req.get('declined') is True or text(req.get('answer')), 'missing_answer')
            previous.update(status='declined' if req.get('declined') else 'answered', answer=req.get('answer'))
        return {'task': self.journal.save(task)}

    def authorization(self, task, req):
        if req['action'] == 'revoke':
            task['grants'] = [g for g in task['grants'] if g['id'] != req.get('grant_id')]
        else:
            tool = req.get('tool')
            require(tool in TOOLS - {'verify'}, 'invalid_grant_tool')
            require(text(req.get('basis')), 'authorization_basis_required')
            # The host maps actual user authorization to this record. This is not a consent UI.
            selector = req.get('selector')
            require(isinstance(selector, dict), 'exact_selector_required')
            allowed = {'read': {'paths'}, 'fetch': {'url'}, 'write': {'path'}, 'run': {'argv'}}[tool]
            require(set(selector) == allowed, 'exact_selector_required')
            value = {'id': fingerprint(tool, selector)[:16], 'tool': tool, 'selector': selector,
                     'basis': req['basis'], 'recorded_at': stamp()}
            task['grants'] = [g for g in task['grants'] if g['id'] != value['id']] + [value]
        return {'task': self.journal.save(task)}

    def execute(self, task, req):
        tool, args = req.get('tool'), req.get('args', {})
        require(tool in TOOLS and isinstance(args, dict), 'unknown_tool')
        require(text(req.get('why')), 'action_needs_reason')
        if tool != 'verify':
            keys = {'read': ('paths',), 'fetch': ('url',), 'write': ('path',), 'run': ('argv',)}[tool]
            selector = {k: args.get(k) for k in keys}
            require(any(g['tool'] == tool and g['selector'] == selector for g in task['grants']), 'scope_not_authorized')
        if tool in ('write', 'run') and task['status'] == 'completed':
            task['status'], task['completion'] = 'working', None
            task = self.journal.save(task)
        signature = fingerprint(tool, args)
        history = self.journal.events(task['id'])
        same = [e for e in history if e['kind'] == 'result' and e['payload'].get('fingerprint') == signature]
        failed = [e for e in same if e['payload']['status'] in ('failed', 'blocked')]
        require(tool in ('read', 'verify') or len(failed) < 3, 'repeat_budget_exhausted_change_approach')
        if same and tool not in ('read', 'verify'):
            require(text(req.get('retry_reason')), 'duplicate_action_needs_changed_evidence')
        attempt = self.journal.add(task['id'], 'attempt', {'tool': tool, 'args': args, 'why': req['why'], 'fingerprint': signature})
        try:
            if tool == 'read':
                files = worktools.inspect(task['root'], args['paths'])
                result = {'files': [{k:v for k,v in f.items() if k != 'content'} for f in files]}
                visible = {'files': files}
            elif tool == 'fetch':
                visible = worktools.fetch(args['url'])
                result = {k:v for k,v in visible.items() if k != 'content'}
            elif tool == 'write':
                result = visible = worktools.write_file(task['root'], args['path'], args['content'], args.get('expected_sha256'))
            elif tool == 'run':
                result = visible = worktools.run(task['root'], args['argv'], args.get('timeout', 30))
            else:
                result = visible = worktools.verify(task['root'], args['checks'])
            status = ('failed' if (tool == 'run' and result['returncode'] != 0) or
                       (tool == 'verify' and not result['passed']) else 'returned')
            event = self.journal.add(task['id'], 'result', {'attempt_id': attempt['id'], 'tool': tool,
                    'status': status, 'fingerprint': signature, 'result': result})
            return {'operation': event, 'output': visible, 'task_id': task['id'],
                    'next': 'Host must judge result and choose next useful action; operation success is not task completion.'}
        except (OSError, ValueError, KeyError, TypeError) as exc:
            error = str(exc) if isinstance(exc, WorkError) else type(exc).__name__
            event = self.journal.add(task['id'], 'result', {'attempt_id': attempt['id'], 'tool': tool,
                    'status': 'blocked' if error in {'network_or_dns_unavailable_use_host_search','fetch_failed_use_host_search'} else 'failed',
                    'fingerprint': signature, 'error': error})
            return {'operation': event, 'task_id': task['id'], 'recoverable': True}

    def complete(self, task, req):
        require(text(req.get('summary')), 'completion_summary_required')
        ids = req.get('verification_ids')
        require(isinstance(ids, list) and ids, 'local_verification_required')
        events = self.journal.events(task['id'])
        by_id = {e['id']: e for e in events}
        for event_id in ids:
            e = by_id.get(event_id, {})
            p = e.get('payload', {})
            require(e.get('kind') == 'result' and p.get('tool') == 'verify' and p.get('status') == 'returned', 'unverified_completion')
            for c in p['result']['checks']:
                require(worktools.read_file(task['root'], c['path'])['sha256'] == c['sha256'], 'artifact_changed_since_verification')
            require(not any(x['at'] > e['at'] and (x['kind'] == 'updated' or
                       x['kind'] == 'attempt' and x['payload']['tool'] in {'run','write'}) for x in events), 'new_work_since_verification')
        snap = self.snapshot(task)
        require(not snap['material_changes'], 'materials_changed_reassess_before_completion')
        require(not snap['interrupted_attempts'], 'interrupted_operation_needs_review')
        task['status'] = 'completed'
        task['completion'] = {'summary': req['summary'], 'verification_ids': ids, 'at': stamp(),
                              'scope': 'specified local artifact checks; semantic quality assessed by host/user'}
        return {'task': self.journal.save(task)}


def main():
    parser = argparse.ArgumentParser(description='Work Intake local host controller')
    parser.add_argument('--state-dir', type=Path, default=ROOT / '.private')
    options = parser.parse_args()
    engine = None
    try:
        raw = sys.stdin.buffer.read(2 * 1024 * 1024 + 1)
        require(len(raw) <= 2 * 1024 * 1024, 'request_too_large')
        req = json.loads(raw)
        engine = Controller(options.state_dir)
        result = engine.handle(req)
        print(json.dumps({'ok': True, **result}, ensure_ascii=False))
        return 0
    except (WorkError, ValueError, OSError, KeyError, TypeError) as exc:
        print(json.dumps({'ok': False, 'error': str(exc) if isinstance(exc, WorkError) else type(exc).__name__}, ensure_ascii=False))
        return 1
    finally:
        if engine: engine.close()


if __name__ == '__main__':
    sys.exit(main())
