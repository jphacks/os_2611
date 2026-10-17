#!/usr/bin/env python3
"""Read-only host handoff checks. No connector login, scheduler or network here."""
import json
import sys


class WorkflowError(ValueError):
    pass


def text(value):
    return isinstance(value, str) and 0 < len(value.strip()) <= 2000


def handle(req):
    if not isinstance(req, dict) or req.get('action') not in ('connection', 'schedule'):
        raise WorkflowError('invalid_request')
    action = req['action']
    allowed = {'action', 'supported', 'approved', 'receipt', 'tool', 'proposal'}
    if set(req) - allowed:
        raise WorkflowError('invalid_request')
    supported = req.get('supported')
    if supported is not None and type(supported) is not bool:
        raise WorkflowError('invalid_request')
    if 'approved' in req and type(req['approved']) is not bool:
        raise WorkflowError('invalid_request')
    if action == 'connection' and not text(req.get('tool')):
        raise WorkflowError('invalid_request')
    proposal = req.get('proposal', {})
    if not isinstance(proposal, dict):
        raise WorkflowError('invalid_request')
    fields = ('topic', 'schedule', 'timezone', 'output_language', 'source_scope')
    if set(proposal) - set(fields) or any(not text(v) for v in proposal.values()):
        raise WorkflowError('invalid_request')
    receipt = req.get('receipt')
    if receipt is not None:
        if not isinstance(receipt, dict) or not text(receipt.get('id')):
            raise WorkflowError('invalid_request')
        expected = {'id', 'connected'} if action == 'connection' else {'id', 'enabled', 'schedule', 'timezone'}
        if set(receipt) != expected:
            raise WorkflowError('invalid_request')
        flag = receipt.get('connected' if action == 'connection' else 'enabled')
        if type(flag) is not bool:
            raise WorkflowError('invalid_request')
        if action == 'schedule' and (not text(receipt['schedule']) or not text(receipt['timezone'])):
            raise WorkflowError('invalid_request')
    result = {'ok': True, 'kind': action, 'performed': False,
              'validation_only': True, 'receipt_source': 'host_supplied' if receipt else None}
    if supported is None:
        return dict(result, state='discover_host_capability', next_action='inspect_actual_host_tools')
    if not supported:
        return dict(result, state='unavailable', next_action='explain_limit_and_continue_without_setup')
    if action == 'schedule':
        missing = [field for field in fields if not proposal.get(field)]
        if missing:
            return dict(result, state='draft', missing=missing, next_action='prepare_concrete_proposal')
    # A reported existing connection can be reused without requesting the same access again.
    if action == 'connection' and receipt and receipt['connected']:
        return dict(result, state='host_reported_connected', external_id=receipt['id'],
                    next_action='verify_with_real_host_read_or_functional_call')
    if not req.get('approved'):
        return dict(result, state='awaiting_user_choice', next_action='show_concrete_scope_and_ask')
    if receipt is None:
        return dict(result, state='ready_for_host_action', next_action='call_real_host_tool_then_check_result')
    if action == 'schedule':
        if receipt['schedule'] != proposal['schedule'] or receipt['timezone'] != proposal['timezone']:
            return dict(result, state='needs_review', next_action='reconcile_actual_schedule_before_claiming_active')
        active = receipt['enabled']
    else:
        active = receipt['connected']
    return dict(result, state=('host_reported_active' if action == 'schedule' else 'host_reported_connected') if active else 'not_active',
                external_id=receipt['id'], next_action='verify_with_real_host_read_or_functional_call' if active else 'report_failure')


if __name__ == '__main__':
    try:
        data = sys.stdin.buffer.read(16385)
        if len(data) > 16384: raise WorkflowError('invalid_request')
        print(json.dumps(handle(json.loads(data)), ensure_ascii=False))
    except (WorkflowError, ValueError, TypeError):
        print(json.dumps({'ok': False, 'error': 'invalid_request'}))
        sys.exit(1)
