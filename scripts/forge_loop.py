"""Local Forge/Atelier controller. No implicit network, credentials, or live paths.

The SQLite file belongs inside an Atelier-owned directory, not the house memory.
Adapters are trusted host code. Model output can request work, never grant authority.
Amounts are integer USD cents. Reservations are NOT a bank balance or a wallet.
"""
from contextlib import contextmanager
from pathlib import Path
import hashlib
import hmac
import json
import secrets
import sqlite3
import time
import uuid


class Refused(Exception):
    pass


def cents(value):
    if type(value) is not int or value < 0:
        raise Refused('USD amounts must be non-negative integer cents')
    return value


def validate_settings(owner_token, worker_token, public_base):
    if min(len(owner_token), len(worker_token)) < 32 or owner_token == worker_token:
        raise Refused('distinct owner and worker secrets are required')
    if not public_base.startswith('https://') or any(c in public_base for c in '\r\n?#'):
        raise Refused('a configured HTTPS control origin is required')


class Controller:
    def __init__(self, database, owner_token, worker_token, public_base):
        validate_settings(owner_token, worker_token, public_base)
        self.path = Path(database).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.owner_token, self.worker_token = owner_token, worker_token
        self.base = public_base.rstrip('/')
        with self.db() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS projects (
              id TEXT PRIMARY KEY, body TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS cycles (
              id TEXT PRIMARY KEY, project TEXT NOT NULL, state TEXT NOT NULL,
              quote INTEGER NOT NULL, receipt TEXT, artifact TEXT);
            CREATE TABLE IF NOT EXISTS intake (digest TEXT PRIMARY KEY, project TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS controls (project TEXT PRIMARY KEY, cancel TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS events (
              id INTEGER PRIMARY KEY, project TEXT NOT NULL, kind TEXT NOT NULL,
              body TEXT NOT NULL, sent INTEGER NOT NULL DEFAULT 0);
            ''')
        self.path.chmod(0o600)

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        db.row_factory = sqlite3.Row
        try:
            db.execute('BEGIN IMMEDIATE')
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def auth(self, token, owner=False):
        allowed = [self.owner_token] if owner else [self.worker_token]
        if not isinstance(token, str) or not any(hmac.compare_digest(token, k) for k in allowed):
            raise Refused('unauthorized')

    def _get(self, db, pid):
        row = db.execute('SELECT body FROM projects WHERE id=?', (pid,)).fetchone()
        if not row:
            raise Refused('no such project')
        return json.loads(row['body'])

    def _save(self, db, p):
        db.execute('UPDATE projects SET body=? WHERE id=?', (json.dumps(p), p['id']))

    def _event(self, db, pid, kind, body):
        db.execute('INSERT INTO events(project,kind,body) VALUES (?,?,?)',
                   (pid, kind, json.dumps(body)))

    def create(self, token, intent, capabilities, ceiling_cents=0, private=False,
               private_until=None, recurring=False, dedupe_key=None):
        self.auth(token, owner=True)
        cents(ceiling_cents)
        if not isinstance(intent, str) or not intent.strip():
            raise Refused('a project intention is required')
        if not isinstance(capabilities, list) or not capabilities or not all(isinstance(x, str) and x for x in capabilities):
            raise Refused('named capability scope is required')
        if private and (type(private_until) not in (int, float) or not time.time() < private_until < time.time()+31*86400):
            raise Refused('private interval needs an explicit future expiry within 31 days')
        pid, cancel = uuid.uuid4().hex, secrets.token_urlsafe(32)
        p = dict(id=pid, intent=intent, capabilities=capabilities, ceiling=ceiling_cents,
                 private=bool(private), private_until=private_until, recurring=bool(recurring),
                 state='ready', spent=0, active=None, cycles=0,
                 cancel_hash=hashlib.sha256(cancel.encode()).hexdigest(), privacy_end=None)
        with self.db() as db:
            if dedupe_key:
                prior = db.execute('SELECT intake.project,cancel FROM intake JOIN controls ON intake.project=controls.project WHERE digest=?', (dedupe_key,)).fetchone()
                if prior: return {'id': prior[0], 'cancel_token': prior[1], 'cancel_url': self.base+'/cancel/'+prior[0], 'replayed': True}
            db.execute('INSERT INTO projects VALUES (?,?)', (pid, json.dumps(p)))
            db.execute('INSERT INTO controls VALUES (?,?)', (pid, cancel))
            if dedupe_key: db.execute('INSERT INTO intake VALUES (?,?)', (dedupe_key, pid))
            self._event(db, pid, 'created', {'at': time.time()})
        # Only the authenticated owner gets this receipt. Never embed an owner secret.
        return {'id': pid, 'cancel_token': cancel, 'cancel_url': self.base+'/cancel/'+pid}

    def _expiry(self, db, p):
        if p['private'] and time.time() >= p['private_until']:
            p.update(private=False, privacy_end='expired')
            self._event(db, p['id'], 'privacy_ended', {'reason': 'expired'})
            self._save(db, p)

    def status(self, token, pid):
        self.auth(token, owner=True)
        with self.db() as db:
            p = self._get(db, pid)
            self._expiry(db, p)
            return {k: p[k] for k in ('id', 'state', 'cycles', 'private', 'private_until', 'spent', 'ceiling', 'active')}

    def cancel(self, pid, cancel_token):
        if not isinstance(cancel_token, str):
            raise Refused('cancel token required')
        with self.db() as db:
            p = self._get(db, pid)
            if not hmac.compare_digest(p['cancel_hash'], hashlib.sha256(cancel_token.encode()).hexdigest()):
                raise Refused('invalid cancellation capability')
            if p['state'] != 'cancelled':
                p.update(state='cancelled', private=False, privacy_end='cancelled')
                self._event(db, pid, 'cancelled', {'at': time.time()})
                self._save(db, p)
        return {'cancelled': True, 'inflight_may_finish': bool(p['active'])}

    def end_private(self, token, pid, reason):
        self.auth(token, owner=(reason == 'audit'))
        if reason not in ('audit', 'revealed', 'abandoned'):
            raise Refused('unknown privacy transition')
        with self.db() as db:
            p = self._get(db, pid)
            p.update(private=False, privacy_end=reason)
            if reason == 'abandoned':
                p['state'] = 'abandoned'
            self._event(db, pid, reason, {'at': time.time()})
            self._save(db, p)
            rows = db.execute('SELECT id,state,receipt,artifact FROM cycles WHERE project=? ORDER BY rowid', (pid,)).fetchall()
            return [dict(r) for r in rows]

    def authorize(self, token, pid, capabilities, ceiling_cents, recurring=False):
        """Replace the project mandate explicitly; uncertain calls need reconciliation first."""
        self.auth(token, owner=True)
        cents(ceiling_cents)
        if not isinstance(capabilities, list) or not capabilities or not all(isinstance(x, str) and x for x in capabilities):
            raise Refused('named capability scope required')
        with self.db() as db:
            p = self._get(db, pid)
            if p['active'] or p['state'] != 'needs_authorization' or ceiling_cents < p['spent']:
                raise Refused('cannot reauthorize a running, uncertain, or terminal project')
            p.update(capabilities=capabilities, ceiling=ceiling_cents, recurring=bool(recurring), state='ready')
            self._event(db, pid, 'authorized', {'at': time.time()})
            self._save(db, p)

    def context(self, token, pid):
        self.auth(token)
        with self.db() as db:
            p = self._get(db, pid)
            self._expiry(db, p)
            # Last accepted artifact is the input to the next cycle.
            row = db.execute("SELECT artifact FROM cycles WHERE project=? AND state='accepted' ORDER BY rowid DESC LIMIT 1", (pid,)).fetchone()
            return {'intent': p['intent'], 'previous': json.loads(row[0]) if row else None,
                    'state': p['state'], 'cycles': p['cycles']}

    def claim(self, token, pid, capability, quote_cents=0, recurring=False, wallet=None):
        self.auth(token)
        quote = cents(quote_cents)
        # No cache or locally invented credit. A paid adapter needs a dedicated account.
        account = wallet.snapshot() if quote and wallet else None
        with self.db() as db:
            p = self._get(db, pid)
            self._expiry(db, p)
            if p['state'] != 'ready' or p['active']:
                return None
            reason = None
            if capability not in p['capabilities'] or (recurring and not p['recurring']):
                reason = 'scope_or_recurring_authority'
            if p['spent'] + quote > p['ceiling']:
                reason = 'project_spending_ceiling'
            if quote:
                # Paid execution is deliberately unavailable in this local prototype.
                # A balance snapshot is not an enforceable payment authorization.
                reason = 'paid_adapter_not_commissioned'
                if not account or account.get('currency') != 'USD' or not account.get('dedicated') or not account.get('account_id'):
                    reason = 'dedicated_usd_wallet_unconnected'
                elif type(account.get('available_cents')) is not int or account['available_cents'] < 0 or not 0 <= time.time()-account.get('observed_at', 0) <= 30:
                    reason = 'wallet_snapshot_invalid_or_stale'
                else:
                    # Shared DB reservations serialize competing projects. Unknown charges stay reserved.
                    reserved = db.execute("SELECT coalesce(sum(quote),0) FROM cycles WHERE state IN ('running','uncertain')").fetchone()[0]
                    if quote+reserved > account['available_cents']:
                        reason = 'wallet_insufficient_funds'
            if reason:
                p['state'] = 'needs_authorization'
                self._event(db, pid, 'authorization', {'reason': reason})
                self._save(db, p)
                return None
            cid = uuid.uuid4().hex
            db.execute("INSERT INTO cycles(id,project,state,quote) VALUES (?,?,'running',?)", (cid, pid, quote))
            p.update(active=cid, state='running')
            self._save(db, p)
            return {'cycle_id': cid, 'capability': capability, 'maximum_cents': quote,
                    'account_id': account['account_id'] if account else None}

    def accept(self, token, pid, cid, artifact, complete, receipt):
        self.auth(token)
        if type(complete) is not bool or not isinstance(artifact, dict) or len(json.dumps(artifact).encode()) > 1024*1024:
            raise Refused('bounded artifact and explicit completion decision required')
        actual = cents(receipt.get('charged_cents'))
        with self.db() as db:
            p = self._get(db, pid)
            row = db.execute('SELECT * FROM cycles WHERE id=? AND project=?', (cid, pid)).fetchone()
            if not row or p['active'] != cid or row['state'] != 'running':
                raise Refused('cycle is not owned or already accepted')
            if actual > row['quote'] or (row['quote'] and not receipt.get('provider_receipt')):
                raise Refused('charge exceeds reservation or lacks provider receipt')
            db.execute("UPDATE cycles SET state='accepted',artifact=?,receipt=? WHERE id=?",
                       (json.dumps(artifact), json.dumps(receipt), cid))
            p.update(active=None, spent=p['spent']+actual, cycles=p['cycles']+1)
            if p['state'] not in ('cancelled', 'abandoned'):
                p['state'] = 'complete' if complete else 'ready'
            self._event(db, pid, 'cycle', {'cycle_id': cid, 'complete': complete,
                                         'summary': str((artifact.get('report') or {}).get('title', 'Cycle completed'))[:100]})
            self._save(db, p)

    def uncertain(self, token, pid, cid):
        self.auth(token)
        with self.db() as db:
            p = self._get(db, pid)
            if p['active'] != cid:
                raise Refused('not the active cycle')
            db.execute("UPDATE cycles SET state='uncertain' WHERE id=? AND state='running'", (cid,))
            if p['state'] not in ('cancelled', 'abandoned'):
                p['state'] = 'reconciliation_required'
            self._save(db, p)
            self._event(db, pid, 'authorization', {'reason': 'uncertain_external_outcome'})

    def drive(self, token, pid, planner, builder, wallet=None):
        """No scheduled sleep or per-cycle owner gate. Trusted adapters are injected.
        Builder must cap cost before effects and use cycle_id as idempotency key.
        Cancellation cannot unsend an already dispatched call; it prevents the next.
        """
        while True:
            context = self.context(token, pid)
            if context['state'] != 'ready':
                return context['state']
            plan = planner(context)
            claim = self.claim(token, pid, wallet=wallet, **plan)
            if not claim:
                return self.context(token, pid)['state']
            try:
                result = builder(claim, context)
                self.accept(token, pid, claim['cycle_id'], **result)
            except BaseException:
                self.uncertain(token, pid, claim['cycle_id'])
                raise

    def projects(self, token):
        self.auth(token, owner=True)
        with self.db() as db:
            ids = [r[0] for r in db.execute('SELECT id FROM projects ORDER BY rowid')]
        return [self.status(token, pid) for pid in ids]

    def artifacts(self, token, pid):
        self.auth(token, owner=True)
        with self.db() as db:
            p = self._get(db, pid); self._expiry(db, p)
            if p['private']: raise Refused('private interval: use explicit audit to end it')
            return [dict(r) for r in db.execute(
                'SELECT id,state,receipt,artifact FROM cycles WHERE project=? ORDER BY rowid', (pid,))]

    def reconcile(self, token, pid, cid, evidence):
        """Owner attests a stopped zero-cost worker. Never silently replay an uncertain call."""
        self.auth(token, owner=True)
        if not isinstance(evidence, str) or len(evidence.strip()) < 12:
            raise Refused('record evidence that the old worker stopped and its outcome was inspected')
        with self.db() as db:
            p = self._get(db, pid)
            row = db.execute('SELECT * FROM cycles WHERE id=? AND project=?', (cid, pid)).fetchone()
            if not row or row['state'] not in ('running', 'uncertain') or row['quote'] != 0 or p['active'] != cid:
                raise Refused('only the active zero-cost interrupted cycle can be reconciled')
            db.execute("UPDATE cycles SET state='aborted',receipt=? WHERE id=?",
                       (json.dumps({'charged_cents': 0, 'reconciliation': evidence}), cid))
            p['active'] = None
            if p['state'] not in ('cancelled', 'abandoned'): p['state'] = 'ready'
            self._save(db, p)
            self._event(db, pid, 'reconciled', {'cycle_id': cid, 'evidence': evidence})

    def recover_interrupted(self, token):
        self.auth(token)
        with self.db() as db:
            rows = [dict(r) for r in db.execute("SELECT project,id FROM cycles WHERE state='running'")]
        for row in rows: self.uncertain(token, row['project'], row['id'])
        return len(rows)

    def notifications(self, token, pid, cancel_token, topic):
        self.auth(token, owner=True)
        with self.db() as db:
            p = self._get(db, pid)
            if not hmac.compare_digest(p['cancel_hash'], hashlib.sha256(cancel_token.encode()).hexdigest()):
                raise Refused('invalid cancellation capability')
            self._expiry(db, p)
            if p['private']:
                return []
            events = db.execute("SELECT * FROM events WHERE project=? AND sent=0 AND kind IN ('cycle','revealed','authorization')", (pid,)).fetchall()
            return [{'event_id': e['id'], 'topic': topic, 'title': 'Forge: '+str(json.loads(e['body']).get('summary') or e['kind'])[:100],
                     'message': 'Atelier project '+pid+' has an update.',
                     'priority': 4 if e['kind']=='authorization' else 3,
                     'actions': [
                         {'action': 'view', 'label': 'View', 'url': self.base+'/projects/'+pid},
                         {'action': 'http', 'label': 'Cancel', 'url': self.base+'/cancel/'+pid,
                          'method': 'POST', 'headers': {'Authorization': 'Bearer '+cancel_token}, 'clear': True}]
                     } for e in events]

    def acknowledge_notification(self, token, event_id):
        self.auth(token, owner=True)
        with self.db() as db:
            db.execute('UPDATE events SET sent=1 WHERE id=?', (event_id,))


class ControlAPI:
    """Transport-independent POST handler; never attach this to an unauthenticated proxy.
    A cancel credential grants no read, start, audit, or payment authority.
    """
    def __init__(self, controller):
        self.controller = controller

    def handle(self, method, path, authorization):
        if method != 'POST':
            return 405, {'error': 'POST required'}
        if not path.startswith('/cancel/'):
            return 404, {'error': 'unknown route'}
        token = authorization.removeprefix('Bearer ') if authorization.startswith('Bearer ') else ''
        try:
            return 200, self.controller.cancel(path[len('/cancel/'):], token)
        except Refused:
            return 403, {'error': 'invalid cancellation capability'}


class ControlWSGI:
    """Minimal mountable control surface; private work has no unauthenticated read route.
    Live mounting, TLS, origin checks and authenticated owner UI are not commissioned.
    """
    def __init__(self, controller):
        self.controller = controller
        self.cancel_api = ControlAPI(controller)

    def __call__(self, environ, start_response):
        method, path = environ.get('REQUEST_METHOD', ''), environ.get('PATH_INFO', '')
        auth = environ.get('HTTP_AUTHORIZATION', '')
        if path.startswith('/cancel/'):
            status, body = self.cancel_api.handle(method, path, auth)
        elif path.startswith('/projects/') and method == 'GET':
            try:
                body = self.controller.status(auth.removeprefix('Bearer '), path[len('/projects/'):])
                status = 200
            except Refused:
                status, body = 403, {'error': 'owner authentication required'}
        else:
            status, body = 404, {'error': 'unknown route'}
        data = json.dumps(body).encode()
        start_response(str(status)+' '+{200:'OK',403:'Forbidden',404:'Not Found',405:'Method Not Allowed'}[status],
                       [('Content-Type','application/json'),('Content-Length',str(len(data))),
                        ('Cache-Control','no-store'),('Referrer-Policy','no-referrer')])
        return [data]
