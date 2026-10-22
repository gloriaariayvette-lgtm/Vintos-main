"""Provider surges and host changes, delivered to Gloria and the existing fault loop.

No model, shell execution of event text, or automatic containment. The only
call history is compute-ledger.jsonl. This file keeps baselines and delivery state.
"""
import collections
import contextlib
import hashlib
import fcntl
import ipaddress
import json
import math
import os
from pathlib import Path
import re
import subprocess
import time

import paid_http

PAUSE = 'python3 ~/.vintos/workspace/scripts/paid_http.py pause'
FLOORS = {'brave': 60, 'kie': 30, 'atlascloud': 30, 'nvidia': 6}


def paths():
    mem = paid_http.workspace() / 'memory'
    return mem / 'security-alarm-state.json', mem / 'security-alarm.json'


def load(path, default):
    try:
        value = json.loads(Path(path).read_text())
        if not isinstance(value, type(default)): raise ValueError('wrong state type')
        return value
    except FileNotFoundError: return default


def provider_rates(now, ledger=None):
    """Rolling 60s attempt counts; p95 of *earlier* minutes, zeros included.

    Completion/reservation/refund rows never count. Historical success ledgers
    undercount failures and are deliberately not blended into this attempt series.
    """
    current = collections.Counter(); scripts = collections.defaultdict(collections.Counter)
    history = collections.defaultdict(collections.Counter); earliest = {}
    ledger = ledger or paid_http.workspace() / 'memory/compute-ledger.jsonl'
    try: stream = open(ledger)
    except FileNotFoundError: return []
    with stream:
        for line in stream:
            try: row = json.loads(line)
            except ValueError: continue
            if not isinstance(row, dict) or row.get('class') != 'outbound' or row.get('stage') != 'attempt': continue
            name = row.get('provider')
            if name not in set(paid_http.HOSTS.values()): continue
            at = row.get('epoch')
            if not isinstance(at, (int, float)) or not math.isfinite(at) or at > now or at < now - 7 * 86400: continue
            earliest[name] = min(earliest.get(name, at), at)
            if now - 60 < at <= now:
                current[name] += 1
                script = re.sub(r'[^A-Za-z0-9_./-]', '_', str(row.get('script') or 'unattributed'))[:120]
                scripts[name][script] += 1
            elif at <= now - 300:  # don't train the baseline on the developing surge
                history[name][int(at // 60)] += 1
    out = []
    for name, rate in current.items():
        minutes = max(1, int((now - 300 - earliest[name]) // 60))
        counts = sorted(history[name].values())
        zeros = max(0, minutes - len(counts)); index = math.ceil(minutes * .95) - 1 - zeros
        p95 = counts[min(index, len(counts)-1)] if index >= 0 and counts else 0
        # A learned baseline cannot silence an extreme surge. Cold start is explicit.
        threshold = min(60, max(FLOORS.get(name, 12), p95 * 5))
        out.append({'provider': name, 'rate': rate, 'threshold': threshold, 'baseline_p95': p95,
                    'baseline_minutes': minutes, 'cold_start': now - earliest[name] < 86400,
                    'scripts': scripts[name].most_common(3)})
    return out


def accounting_health(now, runner=None, since=None):
    """Existing fault input plus journald fallback; no alternate request ledger."""
    from fault_sweep import _tail
    rows = _tail(str(paid_http.workspace() / 'memory/organ-failures.jsonl'))
    if runner is not None:
        lines = runner(['journalctl', '--user', '--since', '@'+str(int(since or now-120)),
                        '-o', 'json', '--no-pager', '-n', '100', '-g', '^'+paid_http.FAILURE_PREFIX])
        for line in lines.splitlines():
            try:
                message = json.loads(line).get('MESSAGE', '')
                if message.startswith(paid_http.FAILURE_PREFIX):
                    rows.append(json.loads(message[len(paid_http.FAILURE_PREFIX):]))
            except (ValueError, TypeError, AttributeError): pass
    out = {}
    for row in rows:
        if not isinstance(row, dict) or row.get('organ')!='paid-http' or row.get('what')!='provider_accounting_failed': continue
        at, name = row.get('at'), row.get('provider')
        if name not in paid_http.HOSTS.values() or not isinstance(at, (float,int)) or not now-120 <= at <= now: continue
        script = re.sub(r'[^A-Za-z0-9_./-]', '_', str(row.get('script', 'unknown')))[:120]
        error = re.sub(r'[^A-Za-z0-9_]', '_', str(row.get('error', 'unknown')))[:60]
        out[name] = ('provider:'+name, 'provider_accounting_failed',
            name+' outbound rate UNKNOWN: accounting failed ('+error+'); script '+script+
            '. Calls continue. Pause: '+PAUSE)
    return list(out.values())


def run(args):
    p = subprocess.run(args, capture_output=True, text=True, timeout=12)
    # journalctl --grep exits 1 when nothing matched: a clean hour, not a blind monitor (22 October)
    if p.returncode == 1 and args[0] == 'journalctl' and '-g' in args and not p.stdout.strip(): return ''
    if p.returncode: raise RuntimeError('probe failed: ' + Path(args[0]).name)
    return p.stdout


def digest(path):
    p = Path(path)
    try:
        if p.is_symlink(): return 'symlink:' + str(p.resolve())
        with p.open('rb') as f:
            h = hashlib.sha256()
            for chunk in iter(lambda: f.read(1024*1024), b''): h.update(chunk)
        return h.hexdigest()
    except FileNotFoundError: return 'absent'


def deploying():
    path = Path.home()/'.vintos/deploy/security-install.lock'
    try:
        with path.open('r') as f:
            try: fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError: return True
            fcntl.flock(f, fcntl.LOCK_UN)
    except FileNotFoundError: pass
    return False


def host_snapshot(runner=run):
    """Only hashes and names; never persist a key, cron command, or unit body."""
    h = Path.home()
    files = {}
    for base, patterns in [(h/'.config/systemd/user', ['*.service','*.timer','*.socket','*.path','*.target','*.d/*.conf']),
                           (Path('/usr/lib/systemd/system'), ['*.service','*.timer','*.socket','*.path','*.target','*.d/*.conf']),
                           (Path('/run/systemd/system'), ['*.service','*.timer','*.socket','*.path','*.target','*.d/*.conf']),
                           (Path('/etc/systemd/system'), ['*.service','*.timer','*.socket','*.path','*.target','*.d/*.conf']),
                           (Path('/etc/cron.d'), ['*']), (Path('/etc/cron.daily'), ['*']),
                           (Path('/etc/cron.hourly'), ['*']), (Path('/etc/cron.weekly'), ['*']),
                           (Path('/etc/cron.monthly'), ['*'])]:
        for pattern in patterns:
            for p in base.glob(pattern):
                if p.is_file() or p.is_symlink(): files[str(p)] = digest(p)
    for p in [h/'.ssh/authorized_keys', Path('/etc/crontab'), Path('/etc/anacrontab')]:
        files[str(p)] = digest(p)
    # crontab -l uses status 1 for no table. Other failures must be visible.
    try: cron = runner(['crontab','-l'])
    except RuntimeError:
        if (h/'.vintos').exists(): raise
        cron = ''
    files['user-crontab'] = hashlib.sha256(cron.encode()).hexdigest()
    releases = sorted((h/'.vintos/deploy/releases').glob('*.json'))
    receipt = load(releases[-1], {}) if releases else {}
    deployed = {}
    for row in receipt.get('files', []):
        p = Path(row.get('installed_at', ''))
        # Sealed content is never opened. Only executable code is monitored.
        if p.suffix not in ('.py','.sh','.js','.service','.timer'): continue
        allowed = [h/'.vintos/workspace/scripts', h/'.vintos/bin', h/'.vintos/workspace/bin', h/'.config/systemd/user', h/'Vintos', h/'Vintos-main/bin', h/'Vintos-main/scripts']
        if not any(str(p).startswith(str(b)+'/') for b in allowed): continue
        expected = row.get('sha256')
        actual = digest(p)
        deployed[str(p)] = {'actual': actual, 'expected': expected,
                            'matches_release': bool(expected) and actual.startswith(expected)}
    return {'files': files, 'deployed': deployed, 'release': releases[-1].name if releases else None, 'deploying': deploying()}


def ssh_logins(since, runner=run):
    text = runner(['journalctl','-u','ssh.service','--since','@'+str(int(since)), '-o','json','--no-pager'])
    out = []
    for line in text.splitlines():
        try: row = json.loads(line)
        except ValueError: continue
        msg = row.get('MESSAGE', '')
        match = re.search(r'Accepted (?:publickey|password|keyboard-interactive(?:/pam)?) for [^ ]+ from ([^ ]+)', str(msg))
        if match:
            try: address = str(ipaddress.ip_address(match.group(1)))
            except ValueError: continue
            out.append((str(row.get('__CURSOR') or row.get('__REALTIME_TIMESTAMP')), address))
    return out


def host_events(previous, current):
    out = []
    if current.get('deploying'):
        if previous:
            for p, value in current['files'].items():
                if p.endswith('/.ssh/authorized_keys') and previous['files'].get(p) != value:
                    out.append(('authorized_keys_changed:'+p+':'+value, 'authorized_keys_changed', 'changed '+p))
        return out
    if previous is not None:
        for p in sorted(set(previous['files']) | set(current['files'])):
            if previous['files'].get(p) != current['files'].get(p):
                if (previous.get('release') != current.get('release') and current.get('deployed', {}).get(p, {}).get('matches_release')): continue
                kind = 'authorized_keys_changed' if p.endswith('/.ssh/authorized_keys') else 'schedule_changed'
                verb = 'new' if p not in previous['files'] else 'removed' if p not in current['files'] else 'changed'
                out.append((kind+':'+p+':'+current['files'].get(p,'absent'), kind, verb+' '+p))
    for p, d in current['deployed'].items():
        if not d['matches_release']:
            out.append(('code:'+p+':'+d['actual'], 'deployed_code_changed', 'deployed code differs from release '+str(current['release'])+': '+p))
    if not current['release']:
        out.append(('missing-release', 'monitor_blind', 'No deployment receipt; deployed-code coverage unavailable'))
    return out


def remember(state, key, kind, why, now, cooldown=3600):
    """Reserve notification once, record to fault input *before* attempting delivery."""
    from fault_sweep import clean
    sent = state.setdefault('last_alert', {})
    if now - sent.get(key, -1e20) < cooldown: return False
    why = clean(why, 900)
    event_id = hashlib.sha256((key+':'+str(now)).encode()).hexdigest()[:20]
    event = {'at': now, 'organ': 'security-alarm', 'what': kind, 'why': why}
    p = paid_http.workspace()/'memory/organ-failures.jsonl'; p.parent.mkdir(parents=True, exist_ok=True)
    with p.open('a') as f:
        f.write(json.dumps(event)+'\n'); f.flush(); os.fsync(f.fileno())
    state.setdefault('pending', {})[event_id] = {'why': why, 'kind': kind, 'at': now, 'key': key}
    sent[key] = now
    return True


def tend(now=None, dry=False, runner=run, sender=None, snapshot=None, logins=None):
    from store_guard import transaction, save_json
    now = time.time() if now is None else now
    state_path, config_path = paths()
    # The monitor is serial across concurrent manual/timer invocations.
    with (contextlib.nullcontext() if dry else transaction(str(state_path))):
        state = load(state_path, {})
        config = load(config_path, {})
        events = []
        try:
            rates = provider_rates(now)
            for r in rates:
                if r['rate'] > r['threshold']:
                    why = '%s: %d outbound calls/min; script %s. Pause: %s' % (
                        r['provider'], r['rate'], ', '.join('%s (%d)' % tuple(s) for s in r['scripts']), PAUSE)
                    events.append(('provider:'+r['provider'], 'provider_surge', why))
        except Exception as e:
            rates = []; events.append(('accounting-unreadable','monitor_blind','Provider accounting unreadable: '+type(e).__name__))
        try:
            current = snapshot if snapshot is not None else host_snapshot(runner)
            events += host_events(state.get('host'), current)
        except Exception as e:
            current = None; events.append(('host-unreadable','monitor_blind','Host baseline unreadable: '+type(e).__name__))
        try:
            seen = state.setdefault('ssh_seen', {})
            for cursor, address in (logins if logins is not None else ssh_logins(state.get('checked_at', now-300)-1, runner)):
                if cursor not in seen and address not in config.get('known_ssh_addresses', []):
                    events.append(('ssh:'+address,'unfamiliar_ssh','New SSH login from unfamiliar address '+address))
                seen[cursor] = now
            state['ssh_seen'] = {k:v for k,v in seen.items() if now-v < 86400}
        except Exception as e:
            events.append(('ssh-unreadable','monitor_blind','SSH login journal unreadable: '+type(e).__name__))
        try:
            events += accounting_health(now, runner if snapshot is None else None, state.get('checked_at', now-120)-1)
        except Exception as e:
            events.append(('accounting-health-unreadable','monitor_blind','Accounting health evidence unreadable: '+type(e).__name__))
        if dry: return {'rates': rates, 'events': [e[1:] for e in events], 'dry': True}
        for key,kind,why in events: remember(state,key,kind,why,now)
        if current is not None and not current.get('deploying'): state['host'] = current
        if current is not None and current.get('deploying'):
            state.setdefault('deploy_started', now)
            if now - state['deploy_started'] > 900:
                remember(state, 'deploy-stalled', 'monitor_blind', 'Installation lock held more than 15 minutes; deployment drift monitoring deferred', now)
        else: state.pop('deploy_started', None)
        state['checked_at'] = now
        # Persist pending before sending. Crash after send is deduplicated by deliver's receipt.
        save_json(str(state_path), state)
        if sender is None:
            from deliver import deliver
            sender = deliver
        sent = 0
        for event_id, row in sorted(state.setdefault('pending', {}).items(), key=lambda item: (item[1]['kind'] != 'provider_surge', item[1]['at']))[:3]:
            # An undeliverable alert from an earlier hour is superseded, not sent as a burst later.
            if now - row['at'] >= 3600:
                del state['pending'][event_id]; continue
            delivered = state.setdefault('delivered', {})
            if now - delivered.get(row['key'], -1e20) < 3600:
                del state['pending'][event_id]; continue
            receipt = sender('security-'+event_id, 'ntfy', message=row['why'], title='Vintos security: '+row['kind'],
                authority=lambda: (True, 'Gloria requested infrastructure security alarms'), retries=1, priority='high')
            if receipt.get('state') in ('sent','acknowledged'):
                del state['pending'][event_id]; delivered[row['key']] = now; sent += 1
        # Bound long-term suppression metadata; no event history is stored here.
        state['last_alert'] = {k:v for k,v in state.get('last_alert',{}).items() if now-v < 7*86400}
        save_json(str(state_path), state)
        return {'rates': rates, 'events': len(events), 'sent': sent, 'pending': len(state['pending']), 'dry': False}
