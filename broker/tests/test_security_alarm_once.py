"""A drifted deployed file alarms once per (release, file, content), then once a day while it lasts.

Gloria, 12 November: a live hot-patch outside the deploy put the same "deployed_code_changed" on her phone every
hour all day for three files. New changes must stay loud. Scratch HOME; delivery is a stub; no socket opens.
"""
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[2]
SCRATCH = tempfile.TemporaryDirectory(prefix='security-once-')
os.environ['HOME'] = SCRATCH.name
os.environ['SPARK_WORKSPACE'] = str(Path(SCRATCH.name)/'workspace')
sys.path.insert(0, str(REPO/'scripts'))
def forbidden(*a, **k): raise AssertionError('network forbidden in security suite')
socket.socket.connect = forbidden
socket.create_connection = forbidden
import paid_http as P
import security_alarm as A

HOUR, DAY = 3600, 86400


def snap(release='r1.json', **files):
    return {'files': {'user-crontab': 'c'}, 'release': release, 'deploying': False,
            'deployed': {p: {'actual': sha, 'expected': 'good', 'matches_release': sha == 'good'} for p, sha in files.items()}}


class DriftOnce(unittest.TestCase):
    def setUp(self):
        for p in Path(SCRATCH.name).rglob('*'):
            if p.is_file(): p.unlink()
        P.workspace().joinpath('memory').mkdir(parents=True, exist_ok=True)
        self.now = 2000000000
        self.sent = []
        self.ok = True
        self.assertTrue(str(A.paths()[0]).startswith(SCRATCH.name))

    def sender(self, *a, **k):
        if not self.ok: return {'state': 'failed'}
        self.sent.append(k); return {'state': 'sent'}

    def tick(self, at, s):
        return A.tend(now=self.now + at, snapshot=s, logins=[], sender=self.sender)

    def titles(self):
        return [k['title'].split(': ', 1)[1] for k in self.sent]

    def test_same_drift_is_one_alert_then_a_daily_digest(self):
        s = snap(**{'/w/a.py': 'h1', '/w/b.py': 'h2', '/w/c.py': 'good'})
        for h in range(0, 24):                      # a pass every hour for a day
            self.tick(h * HOUR, s)
        self.assertEqual(self.titles(), ['deployed_code_changed'] * 2)
        self.assertEqual(sorted(k['message'].rsplit(': ', 1)[1] for k in self.sent), ['/w/a.py', '/w/b.py'])
        self.tick(DAY, s)
        self.assertEqual(self.titles()[2:], ['deployed_code_unresolved'])
        digest = self.sent[2]['message']
        self.assertIn('2 deployed file(s) still differ from release r1.json', digest)
        self.assertIn('/w/a.py (since ', digest); self.assertIn('/w/b.py (since ', digest)
        for h in range(25, 48):
            self.tick(h * HOUR, s)
        self.assertEqual(len(self.sent), 3)        # no repeats inside the day
        self.tick(2 * DAY, s)
        self.assertEqual(self.titles()[3:], ['deployed_code_unresolved'])

    def test_new_content_new_file_and_new_release_are_loud_at_once(self):
        self.tick(0, snap(**{'/w/a.py': 'h1'}))
        self.tick(60, snap(**{'/w/a.py': 'h2'}))                      # patched again
        self.tick(120, snap(**{'/w/a.py': 'h2', '/w/b.py': 'h9'}))    # another file
        self.tick(180, snap('r2.json', **{'/w/a.py': 'h2', '/w/b.py': 'h9'}))   # a release that did not adopt them
        msgs = [k['message'] for k in self.sent]
        self.assertEqual(len(msgs), 5, msgs)
        self.assertTrue(all('deployed code differs from release' in m for m in msgs))
        self.assertEqual(sum('r2.json' in m for m in msgs), 2)

    def test_resolved_drift_is_forgotten_and_a_return_alarms_again(self):
        self.tick(0, snap(**{'/w/a.py': 'h1'}))
        self.tick(HOUR, snap(**{'/w/a.py': 'good'}))
        self.assertEqual(json.loads(A.paths()[0].read_text())['code_drift'], {})
        self.tick(2 * HOUR, snap(**{'/w/a.py': 'h1'}))
        self.assertEqual(len(self.sent), 2)
        self.tick(DAY + 2 * HOUR, snap(**{'/w/a.py': 'good'}))
        self.assertEqual(len(self.sent), 2)        # nothing unresolved, no digest

    def test_a_drift_that_returns_within_the_hour_is_loud_again(self):
        # review: the earlier episode's hourly cooldown and delivery receipt swallowed the return for good
        self.tick(0, snap(**{'/w/a.py': 'h1'}))
        self.tick(600, snap(**{'/w/a.py': 'good'}))
        self.tick(1200, snap(**{'/w/a.py': 'h1'}))
        self.assertEqual(len(self.sent), 2, 'the return alarms on the pass that sees it, not an hour later')
        for h in range(1, 20): self.tick(h * HOUR, snap(**{'/w/a.py': 'h1'}))
        self.assertEqual(len(self.sent), 2, [k['message'] for k in self.sent])

    def test_a_revert_to_earlier_content_is_loud(self):
        self.tick(0, snap(**{'/w/a.py': 'h1'}))
        self.tick(60, snap(**{'/w/a.py': 'h2'}))
        self.tick(120, snap(**{'/w/a.py': 'h1'}))
        self.assertEqual(len(self.sent), 3, 'the revert alarms on the pass that sees it')
        for h in range(1, 20): self.tick(h * HOUR, snap(**{'/w/a.py': 'h1'}))
        self.assertEqual(len(self.sent), 3, [k['message'] for k in self.sent])

    def test_undelivered_first_alert_is_retried_until_delivered(self):
        self.ok = False
        s = snap(**{'/w/a.py': 'h1'})
        self.tick(0, s); self.tick(HOUR, s)
        self.assertEqual(self.sent, [])
        self.ok = True
        self.tick(2 * HOUR + 1, s)
        self.assertEqual(self.titles(), ['deployed_code_changed'])
        for h in range(3, 20): self.tick(h * HOUR, s)
        self.assertEqual(len(self.sent), 1)

    def test_deferred_snapshot_keeps_the_record(self):
        s = snap(**{'/w/a.py': 'h1'})
        self.tick(0, s)
        deferred = dict(s, deploying=True, deferred='install lock held')
        self.tick(60, deferred)
        self.assertEqual(len(json.loads(A.paths()[0].read_text())['code_drift']), 1)
        self.tick(120, s)
        self.assertEqual(len(self.sent), 1)

    def test_upgrade_does_not_reannounce_drifts_already_alarmed(self):
        A.paths()[0].write_text(json.dumps({'last_alert': {'code:/w/a.py:h1': self.now - 600}}))
        s = snap(**{'/w/a.py': 'h1', '/w/b.py': 'h2'})
        self.tick(0, s)
        self.assertEqual([k['message'].rsplit(': ', 1)[1] for k in self.sent], ['/w/b.py'])
        self.tick(DAY, s)
        self.assertIn('/w/a.py (since ', self.sent[-1]['message'])

    def test_other_alarms_keep_their_hourly_behaviour(self):
        s = dict(snap(), files={'user-crontab': 'c'})
        self.tick(0, s)
        changed = dict(s, files={'user-crontab': 'new'})
        self.tick(60, changed)
        self.assertEqual(self.titles(), ['schedule_changed'])

    def test_watched_files_are_unchanged(self):
        # the fix changes how often, never which files: the same mismatch is still an event
        ev = A.host_events(None, snap(**{'/w/a.py': 'h1', '/w/b.py': 'good'}))
        self.assertEqual([(e[1], e[2].rsplit(': ', 1)[1]) for e in ev], [('deployed_code_changed', '/w/a.py')])


if __name__ == '__main__': unittest.main()
