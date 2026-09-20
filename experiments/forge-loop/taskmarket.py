"""Read-only Taskmarket discovery and evidence-based local screening.

No claims, signatures, bids, submissions, payments or marketplace-supplied commands.
USDC amounts are integer micro-USDC, never the controller's USD cents.
"""
from datetime import datetime, timezone
import hashlib
import json
import re
import time
from urllib.parse import urlencode

BASE = 'https://api.taskmarket.dev'
CHAIN_ID = 8453
USDC = '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913'
ID = re.compile(r'0x[0-9a-fA-F]{64}\Z')


def micro_usdc(value):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9]{1,30}', value):
        raise ValueError('expected a decimal base-unit USDC string')
    return int(value)


def task_digest(task):
    return hashlib.sha256(json.dumps(task, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def epoch(value):
    if not isinstance(value, str):
        raise ValueError('expected an ISO timestamp')
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('timestamp must include timezone')
    return parsed.timestamp()


class ReadOnlyMarket:
    def __init__(self, get_json):
        self.get_json = get_json  # injected read-only transport, no signer or payer

    def discover(self, cursor=None):
        query = {'status': 'open', 'phase': 'active', 'sort': 'newest', 'limit': 20}
        if cursor is not None:
            epoch(cursor)
            query['cursor'] = cursor
        response = self.get_json(BASE+'/api/tasks?'+urlencode(query))
        if not isinstance(response, dict) or not isinstance(response.get('tasks'), list):
            raise ValueError('unrecognized marketplace response')
        return response

    def detail(self, task_id):
        if not isinstance(task_id, str) or not ID.fullmatch(task_id):
            raise ValueError('invalid task identity')
        return self.get_json(BASE+'/api/tasks/'+task_id)


def screen(task, assessment, inventory, *, max_cost_micro=0, now=None):
    """Assessment is produced by a trusted local evaluator, never read from task tags.
    Gemma may nominate a capability; admission needs a fresh task-bound probe receipt.
    Suitable means eligible for a local work trial, not authorized to claim or submit.
    """
    now = time.time() if now is None else now
    reasons = []
    try:
        if not ID.fullmatch(task['id']):reasons.append('invalid_identity')
        if task['status'] != 'open' or task.get('phase') != 'active':reasons.append('not_open')
        reward = micro_usdc(task['reward'])
        expiry = epoch(task['expiryTime'])
        # Start with contests only; no stake, bids, exclusivity or assignment obligation.
        if task.get('mode') != 'bounty':reasons.append('mode_requires_separate_admission')
        if task.get('submissionWindowOpen') is not True:reasons.append('window_closed')
        if task.get('stakeRequired') is not False:reasons.append('stake_unknown_or_required')
        if task.get('taskVisibility') != 'public':reasons.append('access_not_established')
        if assessment.get('task_sha256') != task_digest(task):reasons.append('stale_assessment')
        cap = inventory.get(assessment.get('capability'), {})
        probe = assessment.get('probe', {})
        if not cap or cap.get('enabled') is not True:reasons.append('capability_unavailable')
        if (probe.get('passed') is not True or probe.get('task_sha256') != task_digest(task)
            or probe.get('runtime_sha256') != cap.get('runtime_sha256')
            or not cap.get('runtime_sha256') or not 0 <= now-probe.get('at', 0) <= 86400):
            reasons.append('fresh_measured_probe_required')
        required = assessment.get('required_tools')
        if not isinstance(required, list) or not set(required) <= set(cap.get('tools', [])):
            reasons.append('tools_unavailable')
        if assessment.get('acceptance_check') not in cap.get('acceptance_checks', []):
            reasons.append('acceptance_unverifiable')
        if assessment.get('public_inputs_only') is not True or assessment.get('external_effects') is not False:
            reasons.append('scope_not_safe_for_local_trial')
        cost, seconds = assessment.get('cost_micro'), assessment.get('seconds')
        if type(cost) is not int or cost < 0 or cost > max_cost_micro:reasons.append('cost_unfunded')
        if type(seconds) is not int or seconds <= 0 or now+seconds+300 >= expiry:
            reasons.append('insufficient_deadline_margin')
        fee = task.get('platformFeeBps')
        if type(fee) is not int or not 0 <= fee <= 10000:reasons.append('fee_unknown')
        elif type(cost) is int and reward*(10000-fee)//10000 <= cost:reasons.append('nonpositive_nominal_margin')
    except (KeyError, TypeError, ValueError, OverflowError):
        reasons.append('malformed_or_incomplete_evidence')
    return {'task_id': task.get('id'), 'eligible_local_trial': not reasons,
            'reasons': sorted(set(reasons)), 'authority': 'local_trial_only',
            'payout_guaranteed': False}
