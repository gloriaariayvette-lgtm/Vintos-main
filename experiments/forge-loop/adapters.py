"""Explicit local adapters. No defaults that could discover household credentials."""
import hashlib
import json
from pathlib import Path
import sys

SCRIPTS = Path(__file__).resolve().parents[2] / 'scripts'
sys.path.insert(0, str(SCRIPTS))


class UnconnectedUSDWallet:
    def snapshot(self):
        return {'currency': 'USD', 'dedicated': True, 'account_id': None,
                'available_cents': None, 'status': 'account_not_connected'}

    def reserve(self, **kwargs):
        raise RuntimeError('a real dedicated USD account and payment adapter are required')


class ForgeSandboxBuilder:
    """Reuse Forge generation/review/OS tests, but never its household payer defaults.

    astra and fable MUST be explicitly supplied, with a dedicated payment capability
    for paid use. This local adapter only supports zero-cost fixtures/local inference.
    It does not install a capability into the live house or claim live verification.
    """
    def __init__(self, astra, fable, evaluator):
        self.astra, self.fable, self.evaluator = astra, fable, evaluator

    def __call__(self, claim, context):
        if claim['maximum_cents'] != 0:
            raise RuntimeError('paid Forge adapter is not commissioned; household fallback forbidden')
        import forge_build
        proposal = {'capability': claim['capability'], 'why': context['intent'],
                    'tests': 'Self-contained scratch tests; no network or host writes.',
                    'granted': {'scope': {'execution': 'OS sandbox only'}, 'permissions': []}}
        # Explicit previous source/evaluation is a continuation, not a fresh unrelated build.
        if context['previous']:
            proposal['why'] += '\nPrevious accepted artifact and evaluation:\n'+json.dumps(context['previous'])
        code = forge_build.generate(proposal, astra=self.astra)
        ok, reason = forge_build.review(proposal, code, fable=self.fable)
        if not ok:
            return {'artifact': {'module': code['module'], 'test': code['test'],
                                  'verified': False, 'review': reason},
                    'complete': False, 'receipt': {'charged_cents': 0, 'payer': 'local'}}
        ok, output = forge_build.sandbox_test(code['module'], code['test'], code['name'])
        if not ok:
            return {'artifact': {'module': code['module'], 'test': code['test'],
                                  'verified': False, 'sandbox_output': output[-2000:]},
                    'complete': False, 'receipt': {'charged_cents': 0, 'payer': 'local'}}
        evaluation = self.evaluator(code, context)
        if not isinstance(evaluation, dict) or type(evaluation.get('complete')) is not bool:
            raise RuntimeError('evaluator must make an explicit completion decision')
        return {'artifact': {'module': code['module'], 'test': code['test'],
                             'verified': True, 'sha256': hashlib.sha256(code['module'].encode()).hexdigest(),
                             'evaluation': evaluation, 'review': reason, 'sandbox_output': output},
                'complete': evaluation['complete'], 'receipt': {'charged_cents': 0, 'payer': 'local'}}


def publish_pending(controller, owner_token, pid, cancel_token, topic, send):
    """send is an explicitly configured authenticated ntfy transport. No default sender.
    At-least-once delivery: a crash after sending may duplicate, never drop, an event.
    The notification dispatcher must run within the same private owner boundary.
    """
    sent = 0
    for item in controller.notifications(owner_token, pid, cancel_token, topic):
        event_id = item.pop('event_id')
        if send(item) is not True:
            raise RuntimeError('notification delivery unconfirmed; retained for retry')
        controller.acknowledge_notification(owner_token, event_id)
        sent += 1
    return sent
