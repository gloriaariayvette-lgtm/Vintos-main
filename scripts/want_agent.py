"""Join concrete wants to the existing agent room and its delivery/ending doors.

No model, transport, or worker is started here. dot_channel supplies its existing
paused/authorized transport; tests supply stubs. Requests live on their source
rows, room work stays in room_work, and endings use want_completion.
"""
from pathlib import Path
import hashlib
import json
import math
import os
import re
import time
import uuid

RESULT = re.compile(r'^\s*WANT RESULT (WA-[0-9a-f]{24})\s*$', re.M)
BUY = re.compile(r'\b(?:buy|purchase|subscribe|subscription|paid account)\b', re.I)
SCHEMA = 'want-agent-result-v1'
# The rolling window (Gloria, 10 November: "he should work on the newest wants and promises. That's supposed to be on a
# rolling window"). Wants are taken newest first; a bound want from more than WINDOW_DAYS before the newest one that was
# never handed over ages out - marked aged_out on the want, counted and said, never dropped. One in work keeps going.
# Promises he owes become wants ADOPT_OPEN at a time, newest first: as one is finished, the next comes in.
WINDOW_DAYS = 7
ADOPT_OPEN = 3
# An adopted want whose agent never answers gives its place back after this long, said and counted (it keeps its
# request, and goes on if the agent answers later): one silent handoff no longer holds a place for good.
ADOPT_ANSWER_HOURS = 48

_PROCESS_ARTIFACT_CLOCK = uuid.uuid4().hex


def _artifact_clock_domain():
    try:
        boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
        if re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', boot):
            return 'boot:' + boot + ':time-ns:' + str(os.stat('/proc/self/ns/time').st_ino)
    except OSError:
        pass
    return 'process:' + _PROCESS_ARTIFACT_CLOCK + ':' + str(os.getpid())


def _artifact_clock_sample():
    before = time.monotonic()
    wall = time.time()
    after = time.monotonic()
    if (any(type(v) not in (int, float) or not math.isfinite(v) for v in (before, wall, after))
            or not 0 <= before <= after or wall <= 0):
        raise ValueError('artifact clock unavailable')
    return dict(schema='artifact-clock-anchor-v1', domain=_artifact_clock_domain(),
                wall_at=wall, monotonic_before=before, monotonic_after=after)


def _artifact_time(request, mtime):
    created = request.get('created_at')
    current = _artifact_clock_sample()
    if (type(created) not in (int, float) or not math.isfinite(created) or created <= 0
            or not math.isfinite(mtime) or mtime < created - 2):
        raise ValueError('deliverable modification time is outside this request window')
    observed = dict(schema='artifact-time-check-v1', status='wall_window_observed',
                    modified_at=mtime, request_wall_at=created, checked_wall_at=current['wall_at'])
    if mtime <= current['wall_at'] + 1:
        return observed
    anchor = request.get('artifact_clock')
    if isinstance(anchor, dict) and anchor.get('schema') == current['schema'] and anchor.get('domain') == current['domain']:
        before, after = anchor.get('monotonic_before'), anchor.get('monotonic_after')
        if (anchor.get('wall_at') == created
                and all(type(v) in (int, float) and math.isfinite(v) for v in (before, after))
                and 0 <= before <= after <= current['monotonic_before']):
            lower = created + current['monotonic_before'] - after
            upper = created + current['monotonic_after'] - before
            if all(math.isfinite(v) for v in (lower, upper)) and current['wall_at'] < lower and mtime <= upper + 1:
                observed.update(status='unknown_order', reason='measured_backward_wall_discrepancy',
                                anchored_upper_at=upper, backward_discrepancy_min=lower-current['wall_at'],
                                elapsed_seconds_min=current['monotonic_before']-after,
                                elapsed_seconds_max=current['monotonic_after']-before)
                return observed
    raise ValueError('deliverable modification time is outside this request window')


def workspace():
    return Path(os.environ.get('SPARK_WORKSPACE', Path.home() / '.vintos/workspace')).resolve()


def read(path, default):
    try:
        return json.loads(Path(path).read_text())
    except FileNotFoundError:
        return default


def fingerprint(text):
    return hashlib.sha256(str(text).encode()).hexdigest()


def specific(want):
    """This lane requires a literal operational goal bound to a journal/email source."""
    from journal_wants import operational, source_receipt
    if (not isinstance(want, dict) or not isinstance(want.get('id'), str) or not want['id']
            or not isinstance(want.get('want'), str) or not isinstance(want.get('source'), str)
            or not (operational(want['want']) or _promised_work(want))):
        return False
    kind = {'idle-journal':'journal', 'email':'email', 'letter-promise':'email'}.get(want.get('source'))
    if kind is None or want.get('dream_only'):
        return False
    refs = want.get('source_refs')
    if not isinstance(refs, list):
        return False
    for ref in refs:
        if not isinstance(ref, dict) or ref.get('kind') != kind:
            continue
        try:
            expected = source_receipt(kind, ref.get('id'), want['want'])
        except (TypeError, ValueError):
            continue
        if (ref.get('text_sha256') == expected['source_refs'][0]['text_sha256']
                and want.get('source_event_id') == expected['source_event_id']):
            return True
    return False


def _promised_work(want):
    """An email promise of his own work (email_commitments keeps only first-person promises to make, run, write, test
    ...) that is not worded as a literal task, adopted with what would show it done; that evidence is its acceptance
    (10 November: "I'll write up the comparison" is a commitment, and it never reached an agent)."""
    from journal_wants import _NOT_WORK, _POETIC, _METAPHOR
    pid, text, done = want.get('adopted_from'), str(want.get('want') or ''), want.get('done_when')
    return bool(isinstance(pid, str) and pid.startswith('EC-') and isinstance(done, str) and done.strip()
                and any(isinstance(r, dict) and r.get('kind') == 'commitment' and r.get('id') == pid for r in want.get('source_refs') or [])
                and not (_NOT_WORK.search(text) or _POETIC.search(text) or _METAPHOR.search(text)))


def bypass(want):
    return bool(want.get('timer_bypass') or ((want.get('journal_seeded') or want.get('source') == 'idle-journal') and specific(want)))


def request(want, reason='', *, ws=None):
    """Bind the entire literal goal; preserve its plan as context, never count a handoff as done."""
    if not specific(want):
        return None
    ws = Path(ws or workspace())
    from store_guard import locked_update
    found = []
    def mutate(rows):
        for row in rows:
            if not specific(row) or row.get('id') != want.get('id') or row.get('want') != want.get('want') or row.get('fulfilled') or row.get('dismissed'):
                continue
            goal = row.get('want', '')
            digest = fingerprint(goal)
            old = row.get('agent_work') or {}
            if old.get('goal_sha256') == digest:
                found.append(old); return None
            rid = 'WA-' + fingerprint(str(row['id']) + '\0' + digest)[:24]
            clock = _artifact_clock_sample()
            rec = dict(request_id=rid, goal_sha256=digest, goal=goal, status='queued',
                       reason=str(reason)[:300], agent='muse' if BUY.search(goal) else 'dot', created_at=clock['wall_at'], artifact_clock=clock)
            # Exact commitment identity only. Related topics or one shared email
            # must never close a different promised experiment.
            commitments = read(ws / 'memory/email-commitments.json', [])
            explicit = {r.get('id') for r in row.get('source_refs', []) if r.get('kind') == 'commitment'}
            rec['commitment_ids'] = [c['id'] for c in commitments if c.get('id') and
                (c['id'] in explicit or any(str(c.get(k, '')).strip() == goal.strip() for k in ('what', 'quote')))]
            promised = [r.get('id') for r in row.get('source_refs', []) if r.get('kind') == 'promise' and r.get('id')]
            if promised: rec['promise_ids'] = promised     # his journal's promise, kept when this is finished
            row['agent_work'] = rec
            if specific(row) and (row.get('journal_seeded') or row.get('source') == 'idle-journal'):
                row['timer_bypass'] = True
            found.append(rec); return rows
        return None
    locked_update(str(ws / 'memory/current-wants.json'), mutate, default=[], reader='want_agent.request')
    return found[0] if found else None


def _update(wid, rid, changes, ws, *, expected_result=None):
    from store_guard import locked_update
    accepted = []
    def mutate(rows):
        for row in rows:
            a = row.get('agent_work') or {}
            if row.get('id') == wid and a.get('request_id') == rid and a.get('goal_sha256') == fingerprint(row.get('want', '')):
                if expected_result is not None and a.get('result_sha256') != expected_result:
                    return None
                a.update(changes); accepted.append(True); return rows
        return None
    locked_update(str(ws / 'memory/current-wants.json'), mutate, default=[], reader='want_agent.update')
    return bool(accepted)


def directory(rid, ws=None):
    if not re.fullmatch(r'WA-[0-9a-f]{24}', rid):
        raise ValueError('exact request ID required')
    path = Path(ws or workspace()) / 'memory/want-artifacts/requests' / rid
    if path.resolve() != path.absolute():
        raise ValueError('linked result directory refused')
    return path


def _artifact(ws, relative, want, *, clock_checks=None):
    if not isinstance(relative, str):
        raise ValueError('relative artifact path required')
    path = ws / relative
    if Path(relative).is_absolute() or '..' in Path(relative).parts or path.resolve() != path.absolute():
        raise ValueError('artifact path must be a nonlinked workspace-relative file')
    request = want.get('agent_work') or {}
    root = directory(request.get('request_id'), ws)
    if not path.is_relative_to(root) or any(part.startswith('.') for part in path.relative_to(root).parts):
        raise ValueError('deliverable must belong to this exact request directory')
    if path.name in ('result.json', 'working-thread.json') or path.name.endswith('.lock'):
        raise ValueError('request control records are not deliverables')
    if not path.is_file() or not 0 < path.stat().st_size <= 32 * 1024 * 1024:
        raise ValueError('artifact missing, empty or above the delivery budget')
    # Keep the filesystem wall comparison and existing precision allowances.
    # An interval anchor can expose uncertainty, never prove a file's causality.
    check = _artifact_time(request, path.stat().st_mtime)
    if clock_checks is not None: clock_checks.append(dict(check, path=relative))
    return path


def known_artifact_hashes(ws, want):
    """Read recorded output hashes only; copying known bytes is not new work."""
    known=set(); remaining=[300000]
    def scan(value):
        remaining[0]-=1
        if remaining[0]<0: raise ValueError('artifact history exceeds verification budget')
        if isinstance(value,dict):
            digest=value.get('sha256')
            if isinstance(digest,str) and re.fullmatch(r'[0-9a-fA-F]{64}',digest): known.add(digest.lower())
            for child in value.values():
                if isinstance(child,(dict,list)): scan(child)
        elif isinstance(value,list):
            for child in value: scan(child)
    def metadata(path, limit=16*1024*1024):
        if not os.path.lexists(path): return []
        if path.resolve()!=path.absolute() or not path.is_file() or path.stat().st_size>limit:
            raise ValueError('artifact history is linked or exceeds verification budget')
        return read(path,[])
    for relative in ('art/gallery.json','art/video/video-gallery.json','art/video/video-queue.json',
                     'art/music/music.json','fulfilled-wants.json'):
        scan(metadata(ws/'memory'/relative))
    request=want['agent_work']['request_id']
    for row in metadata(ws/'memory/current-wants.json'):
        if row.get('id')==want['id'] and (row.get('agent_work') or {}).get('request_id')==request:
            scan((row.get('agent_work') or {}).get('result_revisions',[]))
        else: scan(row)
    root=ws/'memory/want-artifacts/requests'
    paths=list(root.glob('WA-*/result.json'))
    if len(paths)>10000: raise ValueError('artifact manifest history exceeds verification budget')
    for path in paths:
        if path.parent.name!=request: scan(metadata(path,32000))
    return known


def verify(want, ws=None, *, clock_checks=None):
    """A trusted agent's attestation plus actual hashed files, not a prose 'done'."""
    ws = Path(ws or workspace())
    if not specific(want):
        raise ValueError('agent result requires a bound journal/email source')
    a = want['agent_work']; root = directory(a['request_id'], ws)
    manifest = root / 'result.json'
    if manifest.resolve() != manifest.absolute() or manifest.stat().st_size > 32000:
        raise ValueError('invalid result manifest')
    result = read(manifest, {})
    if (result.get('schema') != SCHEMA or result.get('request_id') != a['request_id']
            or result.get('goal_sha256') != fingerprint(want['want']) or result.get('status') != 'completed'):
        raise ValueError('result does not complete this exact goal')
    if not isinstance(result.get('summary'), str) or not result['summary'].strip() or not isinstance(result.get('acceptance'), str) or not result['acceptance'].strip():
        raise ValueError('agent must describe the result and how it meets the task')
    artifacts = result.get('artifacts')
    if not isinstance(artifacts, list) or not 1 <= len(artifacts) <= 8:
        raise ValueError('completed work must include one to eight deliverables')
    paths = []
    known = known_artifact_hashes(ws, want)
    for entry in artifacts:
        path = _artifact(ws, entry['path'], want, clock_checks=clock_checks)
        if hashlib.sha256(path.read_bytes()).hexdigest() != entry.get('sha256'):
            raise ValueError('artifact changed after the agent reported completion')
        if entry.get('sha256') in known:
            raise ValueError('artifact bytes already recorded on a shelf or earlier deliverable')
        paths.append(path)
    if len(set(paths)) != len(paths) or sum(p.stat().st_size for p in paths) > 64 * 1024 * 1024:
        raise ValueError('duplicate artifacts or total delivery budget exceeded')
    return result, paths


def opening(want, a, wid):
    # JSON quoting prevents a journal's newlines from becoming room control lines.
    return ('WORK REQUEST %s (%s; want %s)\nExact task: %s\n' % (a['request_id'], wid, want['id'], json.dumps(want['want'], ensure_ascii=False))
            + ('Done when this exists (what he promised would show it): %s\n' % json.dumps(want['done_when'], ensure_ascii=False)
               if want.get('done_when') else '')
            + ('His journal on this same want (context, not the task): %s\n'
               % json.dumps([{'at': c.get('at'), 'text': c.get('text')} for c in want['journal_context'][-4:]], ensure_ascii=False)
               if want.get('journal_context') else '') +
            'Source references: %s\nExisting step results (context, not proof of this task): %s\n'
            'Work with me until this deliverable exists. Keep the named tools, inputs, flags and acceptance requirements. '
            'If a download, dependency, account or code change is needed, handle it with your existing permissions; '
            'ask for only an authorization or credential the owner must supply. Code changes remain review branches; '
            'Gloria deploys. Purchases go to @Muse, who uses the existing BUY approval path; this is not permission to spend. '
            'A setup step, a new song, a journal reflection or a plan is not the requested analysis. '
            'Report blockers in this thread and keep working on the other steps. '
            'When the whole task is complete, use scripts/want_agent.py result %s --summary "what was made" '
            '--acceptance "how the exact task was checked, including limits" --artifact memory/want-artifacts/requests/%s/output-file '
            '(repeat --artifact for each deliverable), then post WANT RESULT %s on its own line IN THIS THREAD. '
            'That verifies files, delivers them to Gloria and records that I did it. Never put secrets in the artifacts.'
            % (json.dumps(want.get('source_refs', []), ensure_ascii=False),
               json.dumps(want.get('step_history', [])[-4:], ensure_ascii=False)[:1800], a['request_id'], a['request_id'], a['request_id']))


def intake(state, post, save_state, now, *, ws=None, identity=None, prepare=None):
    """One new handoff per room pass, respecting room capacity and source identity."""
    import room_work
    ws = Path(ws or workspace()); lines = []
    wants = read(ws / 'memory/current-wants.json', [])
    aged = age_out(wants, ws=ws)
    if aged:
        lines.append('want window: %d aged out (bound, never handed over, older than %d days before the newest)' % (aged, WINDOW_DAYS))
    for w in sorted(wants, key=lambda w: _when(w) or 0, reverse=True):     # newest first
        if not specific(w):
            continue
        if w.get('aged_out') and not w.get('agent_work'):
            continue
        if w.get('adoption_released') and not w.get('agent_work'):
            continue        # gave its place back before any agent had it: not handed over later (review, 10 November)
        if w.get('fulfilled') or w.get('dismissed') or w.get('gloria_routed') or w.get('board') == 'awaiting_gloria':
            continue
        pursuit = w.get('pursuit') or {}
        if pursuit.get('state') == 'PAUSED' and float(pursuit.get('paused_until') or 0) > now:
            continue
        a = w.get('agent_work')
        if not a and specific(w):
            if not bypass(w):
                from datetime import datetime
                try:
                    if now - datetime.fromisoformat(w.get('timestamp', '')).timestamp() < 8 * 3600:
                        continue
                except ValueError:
                    pass
            a = request(w, 'literal operational task from journal or email', ws=ws)
        if not a or a.get('goal_sha256') != fingerprint(w.get('want', '')) or a.get('status') in ('completed', 'dropped'):
            continue
        rid = a['request_id']; w['agent_work'] = a
        board = room_work.board(state)
        work = next((x for x in board['open'] if x.get('want_request_id') == rid), None)
        if not work:
            work = next((x for x in board['open'] if not x.get('want_request_id')
                         and room_work.norm(x.get('goal', '')) == room_work.norm(w['want'])), None)
            if work:
                work.update(want_id=w['id'], want_request_id=rid)
                save_state(state)
        if not work:
            closed = next((x for x in board['history'] if x.get('want_request_id') == rid), None)
            if closed:
                # A room claim alone cannot fulfill the source want; keep its outcome visible.
                _update(w['id'], rid, {'room_outcome': closed.get('state'), 'status': 'dropped' if closed.get('state') == 'dropped' else 'needs_result'}, ws)
                continue
            if len(room_work.in_hand(state, now)) >= room_work.MAX_OPEN or len(board['open']) >= room_work.MAX_HELD:
                continue
            wid = 'RW-' + fingerprint(rid)[:8]
            work = dict(id=wid, goal=w['want'][:300], done_when='Exact requested deliverable with bound files and acceptance receipt',
                        opened=now, touched=now, by='want', asks=[], returns=[], steps=[], next='',
                        want_id=w['id'], want_request_id=rid)
            board['open'].append(work)
            save_state(state)  # recover this same work after a crash before the transport reply
        import want_working_thread as working
        if room_work.paused(work, now): continue
        working.load(w, work, ws, identity)
        if a.get('thread'):
            continue
        body = opening(w, a, work['id'])
        if prepare is not None:
            try:
                body = prepare(w, work, body) + '\n\n' + body
            except WantHeld as held:
                lines.append('want %s not handed over yet: %s' % (w['id'], held.reason))
                if held.reason in DAY_WIDE or held.reason == 'pass_call_limit':
                    break           # no working call is left for this pass or day: nothing else can be prepared
                continue
        body = '[want:%s] %s\n%s' % (w['id'], work['id'], body)
        sent = post(body, a['agent'], str(uuid.uuid5(uuid.NAMESPACE_URL, rid)))
        if not isinstance(sent, dict) or not sent.get('ts') or sent.get('ok') is False:
            lines.append('want agent request not acknowledged; retained for retry'); break
        thread = str(sent['ts'])
        _update(w['id'], rid, {'thread': thread, 'status': 'in_work', 'work_id': work['id']}, ws)
        a.update(thread=thread, status='in_work', work_id=work['id'])
        working.append(w, work, ws, 'opening', 'vintos', body, at=now, details={'thread': thread})
        room_work.posted(state, work['id'] + '\n' + body, thread, thread, now, to=[a['agent']], by='want')
        state['threads'] = list(dict.fromkeys(list(state.get('threads') or []) + [thread]))[-60:]
        save_state(state)
        lines.append('specific want handed to its agent with exact result binding'); break
    return lines


def _when(w):
    from datetime import datetime
    try:
        return datetime.fromisoformat(str(w.get('timestamp') or '')[:19]).timestamp()
    except (ValueError, AttributeError):
        return None


def age_out(wants, *, ws=None):
    """Mark the bound wants that left the window unworked; how many now. The window ends WINDOW_DAYS before the newest
    bound want, so nothing ages while nothing new comes."""
    from store_guard import locked_update
    bound = [(w, _when(w)) for w in wants if isinstance(w, dict) and not w.get('fulfilled') and not w.get('dismissed') and specific(w)]
    times = [t for _, t in bound if t is not None]
    if not times:
        return 0
    edge = max(times) - WINDOW_DAYS * 86400
    late = {w['id'] for w, t in bound if t is not None and t < edge and not w.get('agent_work') and not w.get('aged_out')}
    if not late:
        return 0
    marked = []; mark = {'at': time.time(), 'window_days': WINDOW_DAYS}
    def mutate(rows):
        for row in rows:
            if row.get('id') in late and not row.get('agent_work') and not row.get('aged_out'):
                row['aged_out'] = dict(mark); marked.append(row['id'])
        return rows if marked else None
    locked_update(str(Path(ws or workspace()) / 'memory/current-wants.json'), mutate, default=[], reader='want_agent.age_out')
    for w in wants:
        if w.get('id') in marked: w['aged_out'] = dict(mark)
    return len(marked)


class WantHeld(Exception):
    """One bound want cannot move now. Only it waits: the other wants and the handoff go on in the same pass
    (10 November: one want at its call cap raised WorkBlocked out of the whole pass, 146 passes in a row, and three
    adopted email promises were never handed to an agent)."""
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


# Blocks that stop the whole lane (the stop file, a broken policy or budget store); every other block holds one want.
LANE_WIDE = ('want_lane_stopped', 'invalid_work_policy', 'invalid_work_budget', 'linked_work_budget')
# The day's call cap stops model calls for the day, not the lane; a handoff that needs a call waits for tomorrow.
DAY_WIDE = ('daily_call_cap',)
# Blocks raised before any model call (want_working_thread.generate, want_work_budget.reserve): a want held on one of
# these does not use one of the pass's working calls (review, 10 November: two wants held on such a block, met first
# every pass, used both calls and left none to prepare a handoff - the lane stuck again, one want at a time).
# interrupted_call_needs_review is one of these when it is raised on its own, not from a call that just failed.
NO_CALL_MADE = ('per_want_call_cap', 'attempt_already_reserved', 'daily_call_cap', 'provider_retry_backoff',
                'context_needs_continuation', 'working_call_already_recorded')


def hold(w, reason, now, *, ws=None):
    """Mark one bound want held on its own block, on the want where it shows: the reason, since when, and how many
    passes it has been held. Returns the record."""
    ws = Path(ws or workspace()); a = w.get('agent_work') or {}
    old = a.get('blocked') or {}
    same = old.get('reason') == reason
    rec = {'reason': reason, 'since': old.get('since', now) if same else now, 'last': now,
           'passes': (int(old.get('passes') or 0) + 1) if same else 1}
    if a.get('request_id'):
        _update(w['id'], a['request_id'], {'blocked': rec}, ws)
    a['blocked'] = rec
    return rec


def unhold(w, *, ws=None):
    """A want whose working call went through again is no longer held."""
    a = w.get('agent_work') or {}
    if a.get('blocked') and a.get('request_id'):
        _update(w['id'], a['request_id'], {'blocked': None}, Path(ws or workspace()))
        a['blocked'] = None
        if str((w.get('adoption_released') or {}).get('reason', '')).startswith('blocked_'):
            from store_guard import locked_update
            def back(rows):
                for row in rows:
                    if isinstance(row, dict) and row.get('id') == w['id']:
                        row.pop('adoption_released', None); return rows
                return None
            locked_update(str(Path(ws or workspace()) / 'memory/current-wants.json'), back, default=[], reader='want_agent.unhold')


# Blocks that cannot clear by themselves: the want's call cap, and a reply or call that needs a person. Such a want
# gives its places back on the very next pass (11 November: three held or silent wants filled room_work.MAX_OPEN and
# two adopted promises waited two days for the 48 h release). A context limit or a provider backoff keeps the 48 h.
STUCK_BLOCKS = ('per_want_call_cap', 'response_needs_review', 'interrupted_call_needs_review')
QUIET_HOURS = 24          # a bound want whose agent has not answered for this long gives its place back
RECHECK_HOURS = 6         # a place given back is looked at again after this long (one cheap check, no model call)
FULL_WHY = 'waiting for a place: the room holds %d works in hand'


def _thread_events(w, ws):
    a = w.get('agent_work') or {}
    try:
        return json.loads((directory(a['request_id'], ws) / 'working-thread.json').read_text()).get('events', [])
    except (OSError, ValueError, KeyError, TypeError):
        return []


def _agent_last_at(w, ws):
    """When its agent last wrote in the want's working thread (or when the request was made), or None. This is the
    quiet spell's identity: a new agent message starts a new spell."""
    a = w.get('agent_work') or {}
    times = [float(e.get('at') or 0) for e in _thread_events(w, ws)
             if isinstance(e, dict) and str(e.get('key', '')).startswith('agent:')]
    if times:
        return max(times)
    try:
        return float(a.get('created_at') or a.get('thread'))
    except (TypeError, ValueError):
        return None


def _quiet_since(w, ws):
    """Since when the thread has been quiet: the latest word in it from either side, the request, its posting, or its
    re-ping (the latest of them; a transport timestamp that is not a time only loses the max)."""
    a = w.get('agent_work') or {}
    times = [float(e.get('at') or 0) for e in _thread_events(w, ws) if isinstance(e, dict)]
    for v in (a.get('created_at'), a.get('thread'), (a.get('reping') or {}).get('at')):   # thread: when it was posted
        try:
            times.append(float(v))
        except (TypeError, ValueError):
            pass
    return max(times) if times else _agent_last_at(w, ws)


def reping_due(w, ws, now):
    """The quiet spell (when its agent last wrote) for which a bound want is owed its one re-opening message, or None:
    in work in its thread, not held, its agent silent QUIET_HOURS, and not yet re-pinged for this spell (12 November:
    a re-adopted or quiet want gets one message in its existing thread, never a second until its agent writes)."""
    a = (w.get('agent_work') or {}) if isinstance(w, dict) else {}
    if (not a.get('thread') or a.get('status') != 'in_work' or a.get('blocked') or w.get('fulfilled')
            or w.get('dismissed')):
        return None
    last, since = _agent_last_at(w, ws), _quiet_since(w, ws)
    if last is None or since is None or now - since < QUIET_HOURS * 3600:
        return None
    if (a.get('reping') or {}).get('spell') == last:
        return None
    return last


def mark_repinged(w, spell, now, *, ws=None):
    """Record the one re-opening message of this quiet spell on the want."""
    a = w.get('agent_work') or {}
    rec = {'spell': spell, 'at': now}
    _update(w['id'], a.get('request_id'), {'reping': rec}, Path(ws or workspace()))
    a['reping'] = rec


def release_blocked(state, now, *, ws=None, save_state=None):
    """Give back the places of wants that cannot move: held on a block that cannot clear by itself (at once), held on
    another block for ADOPT_ANSWER_HOURS, or bound with no agent reply for QUIET_HOURS. Its room work is paused for
    that cause (out of room_work.MAX_OPEN) and it is marked adoption_released (out of ADOPT_OPEN); its context, request
    and single notice are kept. A quiet want comes back the pass its agent answers; a held one is looked at again
    every RECHECK_HOURS and comes back when its block is gone. Log lines."""
    import room_work
    from store_guard import locked_update
    ws = Path(ws or workspace()); lines = []; board = room_work.board(state); changed = False
    give, back = {}, set()
    for w in read(ws / 'memory/current-wants.json', []):
        if not isinstance(w, dict) or w.get('fulfilled') or w.get('dismissed'):
            continue
        a = w.get('agent_work') or {}
        b = a.get('blocked') or {}
        if b.get('reason') and b['reason'] not in DAY_WIDE:
            wait = 0 if b['reason'] in STUCK_BLOCKS else ADOPT_ANSWER_HOURS * 3600
            if now - float(b.get('since') or now) >= wait:
                give[w['id']] = (a.get('request_id'), 'blocked_' + b['reason'])
            continue
        if a.get('thread') and a.get('status') == 'in_work':
            since = _quiet_since(w, ws)          # a re-ping restarts the day it holds its place for
            if since is not None and now - since >= QUIET_HOURS * 3600:
                give[w['id']] = (a.get('request_id'), 'agent_quiet_%dh' % QUIET_HOURS)
            elif (w.get('adoption_released') or {}).get('reason', '').startswith('agent_quiet'):
                back.add(w['id'])                    # its agent answered: it takes its place again
    for item in board['open']:
        for wid, (rid, why) in give.items():
            if item.get('want_request_id') == rid and not room_work.paused(item, now):
                item.update(paused_until=float(now) + RECHECK_HOURS * 3600,
                            pause_why=('held: %s; its place is given back until that changes' % why)[:300])
                changed = True
                lines.append('want %s gave its room place back: %s' % (wid, why))
        for wid in back:
            if (item.get('want_id') == wid and str(item.get('pause_why', '')).startswith('held: agent_quiet')
                    and room_work.paused(item, now)):
                if len(room_work.in_hand(state, now)) < room_work.MAX_OPEN:
                    item.update(paused_until=0, pause_why='')
                    lines.append('want %s takes its room place again: its agent answered' % wid)
                else:
                    item.update(paused_until=float(now) + RECHECK_HOURS * 3600, pause_why=FULL_WHY % room_work.MAX_OPEN)
                    lines.append('want %s waits for a room place: its agent answered, the room is full' % wid)
                changed = True
    # A want that comes back - its block cleared, or the recheck pause it was given ran out - waits while the room is
    # full: the room never holds more than room_work.MAX_OPEN works in hand (review, 11 November). Only works that gave
    # their place back are put to wait; the others are never paused here.
    hand = room_work.in_hand(state, now)
    if len(hand) > room_work.MAX_OPEN:
        returning = [x for x in hand if str(x.get('pause_why', '')).startswith(('held:', FULL_WHY[:20]))]
        for item in returning[:len(hand) - room_work.MAX_OPEN]:
            item.update(paused_until=float(now) + RECHECK_HOURS * 3600, pause_why=FULL_WHY % room_work.MAX_OPEN)
            changed = True
            lines.append('want %s waits for a room place: the room holds %d works in hand' % (item.get('want_id'), room_work.MAX_OPEN))
    if changed and save_state:
        save_state(state)
    marked = []
    def mutate(rows):
        for w in rows:
            if not isinstance(w, dict):
                continue
            if w.get('id') in give and not w.get('adoption_released'):
                w['adoption_released'] = {'at': now, 'reason': give[w['id']][1],
                                          'hours': 0 if give[w['id']][1][len('blocked_'):] in STUCK_BLOCKS
                                          else (QUIET_HOURS if give[w['id']][1].startswith('agent_quiet') else ADOPT_ANSWER_HOURS)}
                if give[w['id']][1].startswith('agent_quiet'):
                    (w.get('agent_work') or {})['quiet'] = {'since': _agent_last_at(w, ws), 'marked_at': now}
                marked.append(w['id'])
            elif w.get('id') in back:
                w.pop('adoption_released', None)
                (w.get('agent_work') or {}).pop('quiet', None)
                marked.append(w['id'])
        return rows if marked else None
    if give or back:
        locked_update(str(ws / 'memory/current-wants.json'), mutate, default=[], reader='want_agent.release_blocked')
    lines += ['want %s marked: %s' % (wid, give[wid][1]) for wid in marked if wid in give]
    return lines


def _silent_hours(w, ws, now):
    """Hours an adopted want has waited on an agent that never answered (0 once one has, or once a result came)."""
    a = w.get('agent_work') or {}
    if a.get('status') in ('result_ready', 'completed', 'dropped') or a.get('result'):
        return 0.0
    start = _when(w)
    if a:
        try: start = float(a.get('thread') or a.get('created_at'))
        except (TypeError, ValueError): pass
        try:
            events = json.loads((directory(a['request_id'], ws) / 'working-thread.json').read_text()).get('events', [])
        except (OSError, ValueError, KeyError, TypeError):
            events = []
        if any(str(e.get('key', '')).startswith('agent:') for e in events if isinstance(e, dict)):
            return 0.0
    return max(0.0, (now - start) / 3600.0) if start else 0.0


JOURNAL_CONTEXT_MAX = 8


def _live(w):
    return isinstance(w, dict) and not any(w.get(k) for k in ('fulfilled', 'dismissed', 'aged_out', '_delete',
                                                               'adoption_released'))


def _from_letters(w):
    """A want from his mail: read in a letter, or an email promise adopted as a want."""
    return w.get('source') in ('email', 'letter-promise') or str(w.get('adopted_from') or '').startswith('EC-')


def fold_journal(text, receipt=None, *, ws=None, now=None):
    """A journal want that is the same as a live want from his letters is that want (Gloria, 10 November: "it does not
    duplicate but the journal becomes additional context for the want"). The journal's sentence is kept on the email
    want as journal_context, with its source receipt, once per journal entry; no second want is made. Returns the email
    want's id, or None (the journal want then forms as before)."""
    from datetime import datetime
    from journal_wants import twin
    from store_guard import locked_update
    ws = Path(ws or workspace()); receipt = receipt or {}; hit = []
    stamp = datetime.fromtimestamp(now or time.time()).isoformat(timespec='seconds')
    # an owed email promise that says the same more closely wins (review, 10 November: on the live copy a journal want
    # matched its own promise at 5 shared words and all of the shorter, and a different letter want at 4 and 0.8; it
    # was folded into the looser one and the promise it repeated was left to become a second want)
    try:
        pid = promise_twin(text)
        import email_commitments
        p = next((r for r in email_commitments._load() if isinstance(r, dict) and r.get('id') == pid), None) if pid else None
    except Exception:
        p = None
    def mutate(rows):
        w = twin(text, [r for r in rows if _live(r) and _from_letters(r)])
        if w is None:
            return None
        if p is not None and _twin_score(text, p.get('what', '')) > _twin_score(text, w.get('want', '')):
            return None                                 # the promise is the closer twin: express_want carries it
        hit.append(w.get('id'))
        ctx = w.setdefault('journal_context', [])
        sid = receipt.get('source_event_id')
        if any((sid and c.get('source_event_id') == sid) or c.get('text') == str(text)[:600] for c in ctx):
            return None                                 # this journal sentence is already its context
        ctx.append({'text': str(text)[:600], 'at': stamp, 'source_event_id': sid,
                    'source_refs': [r for r in (receipt.get('source_refs') or []) if isinstance(r, dict)][:2]})
        w['journal_context'] = ctx[-JOURNAL_CONTEXT_MAX:]
        return rows
    locked_update(str(ws / 'memory/current-wants.json'), mutate, default=[], reader='want_agent.fold_journal')
    return hit[0] if hit else None


def _twin_score(a, b):
    """(share of the shorter, shared content words) - the order journal_wants.twin ranks twins by."""
    from journal_wants import _content
    x, y = _content(a), _content(b)
    return (len(x & y) / max(1, min(len(x), len(y))), len(x & y))


def promise_twin(text):
    """The id of an email promise he still owes (open, or in room work) that says the same as this journal want, or None.
    The journal want then carries the promise, so adopt_promises does not make the same work a second want."""
    import email_commitments
    from journal_wants import twin
    rows = [r for r in email_commitments._load() if isinstance(r, dict) and r.get('id')
            and r.get('state') in ('open', 'in work')]
    r = twin(text, rows, key=lambda r: r.get('what', ''))
    return r.get('id') if r else None


def adopt_promises(*, ws=None, now=None, paused=False):
    """The newest promises he owes - in his email replies and his journal - that are literal work an agent can do
    become source-bound wants, once each, ADOPT_OPEN at a time (10 November: none ever had; about a hundred email
    promises were owed and not one reached this lane). The want keeps the promise's id, so finishing it keeps the
    promise. While the room is paused, an email promise linked to room work by likeness is adopted too: that work
    cannot move until she starts the day. The link is kept, and whichever finishes first keeps the promise, once
    (close_sources and email_commitments.sync each close only a promise still owed). A want whose promise was kept
    another way, or whose agent has not answered in ADOPT_ANSWER_HOURS, gives its place back. Log lines."""
    from datetime import datetime
    from journal_wants import operational, source_receipt
    from store_guard import locked_update
    ws = Path(ws or workspace()); found = []; now = now or time.time(); closed = set()
    try:
        import email_commitments
        for r in email_commitments.open_rows():            # owed, newest first, inside its window
            linked = r.get('state') == 'in work' and r.get('work_id') and paused
            if ((r.get('state') == 'open' or linked) and r.get('id') and r.get('letter_id')
                    and (operational(r.get('what', '')) or str(r.get('evidence') or '').strip())):
                found.append(('commitment', r['id'], 'email', 'email', str(r['letter_id']), r['what'], r.get('at'), r.get('agent') or '',
                              str(r.get('evidence') or '').strip()[:300]))
        closed |= {r.get('id') for r in email_commitments._load() if r.get('state') in ('done', 'dropped')}
    except Exception:
        pass
    try:
        import promise_keeper
        for i in reversed(promise_keeper.load().get('items', [])):
            if i.get('state') == 'open' and not i.get('thread') and not i.get('want_id') and operational(i.get('what', '')):
                found.append(('promise', i['id'], 'idle-journal', 'journal', 'promise:' + i['id'], i['what'], i.get('opened'), '', ''))
            elif i.get('state') != 'open':
                closed.add(i.get('id'))
    except Exception:
        pass
    taken = set()
    for w in read(ws / 'memory/fulfilled-wants.json', []):
        for ref in (w.get('source_refs') or []) if isinstance(w, dict) else []:
            if isinstance(ref, dict) and ref.get('kind') in ('commitment', 'promise'): taken.add(ref.get('id'))
    # A promise left "in work" whose want is gone (dismissed or archived; 12 November: the population cap dismissed
    # one in work) is adopted again, ahead of the others and past the window it already held a place in, with its
    # request and working context kept when they are still on disk. Its earlier want is found in the archives.
    gone = {}
    for name in ('dismissed-wants.json', 'merged-wants.json'):
        for w in read(ws / 'memory' / name, []):
            if isinstance(w, dict) and str(w.get('adopted_from') or '').startswith(('EC-', 'PR-')):
                gone[w['adopted_from']] = w
    orphans = set()
    try:
        import email_commitments
        _live_refs = set()
        for w in read(ws / 'memory/current-wants.json', []):
            if isinstance(w, dict) and not w.get('dismissed') and not w.get('fulfilled'):
                _live_refs.add(w.get('adopted_from'))
                _live_refs |= {r.get('id') for r in (w.get('source_refs') or []) if isinstance(r, dict)}
        for r in email_commitments._load():
            pid = r.get('id')
            if (r.get('state') == 'in work' and pid in gone and pid not in _live_refs and pid not in taken
                    and r.get('letter_id')):
                orphans.add(pid)
                found[:] = [f for f in found if f[1] != pid]      # it may be listed already (paused, linked): once, first
                found.insert(0, ('commitment', pid, 'email', 'email', str(r['letter_id']), r['what'], r.get('at'),
                                 r.get('agent') or '', str(r.get('evidence') or '').strip()[:300]))
    except Exception:
        pass
    made = []; released = []; joined = []
    from journal_wants import twin
    def mutate(rows):
        open_now = 0
        for w in rows:
            for ref in (w.get('source_refs') or []) if isinstance(w, dict) else []:
                if isinstance(ref, dict) and ref.get('kind') in ('commitment', 'promise'): taken.add(ref.get('id'))
            a = (w.get('agent_work') or {}) if isinstance(w, dict) else {}
            if (isinstance(w, dict) and w.get('adopted_from') and not w.get('fulfilled') and not w.get('dismissed')
                    and not w.get('aged_out') and not w.get('adoption_released') and w['adopted_from'] in closed
                    and not a):
                # its promise was kept (or dropped) another way - by its room work - before any agent had it: it is
                # not handed over to be done again (review, 10 November)
                w['adoption_released'] = {'at': now, 'reason': 'kept_another_way', 'hours': 0}
                released.append(w); continue
            if (isinstance(w, dict) and w.get('adopted_from') and not w.get('fulfilled') and not w.get('dismissed')
                    and not w.get('aged_out') and not w.get('adoption_released') and w['adopted_from'] not in closed
                    and a.get('status') not in ('completed', 'dropped')):
                if _silent_hours(w, ws, now) >= ADOPT_ANSWER_HOURS:
                    w['adoption_released'] = {'at': now, 'reason': 'no_answer' if a.get('thread') else 'never_handed_over',
                                              'hours': ADOPT_ANSWER_HOURS}
                    released.append(w); continue
                open_now += 1
        for kind, pid, source, rkind, sid, text, at, agent, done in found:
            if pid in taken: continue
            if kind == 'commitment':
                # the same work already stands as a journal want: the promise joins it, once; no second want
                jw = twin(text, [w for w in rows if _live(w) and w.get('source') == 'idle-journal'])
                if jw is not None:
                    jw.setdefault('source_refs', []).append({'kind': 'commitment', 'id': pid})
                    if isinstance(jw.get('agent_work'), dict):
                        jw['agent_work'].setdefault('commitment_ids', []).append(pid)
                    joined.append((pid, jw.get('id'))); taken.add(pid); continue
            if open_now + len(made) >= ADOPT_OPEN and pid not in orphans: continue
            row = dict(id=('ec-' if kind == 'commitment' else 'pr-') + pid.split('-', 1)[-1], want=text, source=source,
                       urgency='normal', intensity=3, timestamp=datetime.fromtimestamp(now or time.time()).isoformat(timespec='seconds'),
                       promised_at=str(at or '')[:19], fulfilled=False, outreach_count=0, adopted_from=pid, timer_bypass=True,
                       reasoning=('promised in my reply to %s' % (agent or 'an agent') if kind == 'commitment' else 'promised in my journal'))
            if done: row['done_when'] = done
            row.update(source_receipt(rkind, sid, text))
            row['source_refs'].append({'kind': kind, 'id': pid})
            if not specific(row): continue           # neither literal work nor promised work with its evidence
            old = (gone.get(pid) or {}).get('agent_work') if pid in orphans else None
            if isinstance(old, dict) and old.get('goal_sha256') == fingerprint(row['want']) and old.get('request_id'):
                # its request, its thread with the agent and its working context are kept (a working thread is bound
                # to one transport thread); it is that want again, bound to its room work, and its agent's next
                # word reaches it. A quiet or held mark it had is the release rules' to set again.
                row['agent_work'] = {k: v for k, v in old.items() if k not in ('quiet', 'blocked')}
                row['readopted'] = {'at': now, 'previous': (gone.get(pid) or {}).get('dismissed_by') or 'archived'}
            rows.append(row); made.append(row); taken.add(pid)
        return rows if (made or released or joined) else None
    locked_update(str(ws / 'memory/current-wants.json'), mutate, default=[], reader='want_agent.adopt')
    for row in made:
        if row['adopted_from'].startswith('PR-'):
            try:
                import promise_keeper; promise_keeper.adopted(row['adopted_from'], row['id'])
            except Exception:
                pass
    total = sum(1 for w in read(ws / 'memory/current-wants.json', []) if isinstance(w, dict) and w.get('adoption_released'))
    return (['adopted want %s gave its place back: %s%s (%d released so far)'
             % (w['id'], w['adoption_released']['reason'].replace('_', ' '),
                (' after %d h' % ADOPT_ANSWER_HOURS) if w['adoption_released']['hours'] else '', total) for w in released]
            + ['promise %s became a want for the work lane' % row['adopted_from'] for row in made]
            + ['promise %s joined journal want %s (one want, not two)' % j for j in joined]
            + (['promises re-adopted after their want was gone: %d (%s)' % (
                len([r for r in made if r['adopted_from'] in orphans]),
                ', '.join(r['adopted_from'] for r in made if r['adopted_from'] in orphans))]
               if any(r['adopted_from'] in orphans for r in made) else []))


def threads(ws=None):
    return [w['agent_work']['thread'] for w in read(Path(ws or workspace()) / 'memory/current-wants.json', [])
            if isinstance(w.get('agent_work'), dict) and w['agent_work'].get('thread')]


def result_digest(result):
    return fingerprint(json.dumps(result, sort_keys=True, separators=(',', ':'), allow_nan=False))


_RESULT_FIELDS = ('result', 'result_sha256', 'result_source', 'result_ts', 'result_error',
                  'stage_result_sha256', 'publishing', 'publication', 'delivery',
                  'completed_at', 'completion_message', 'artifact_clock_checks')


def _retain_unknown_checks(prior, current):
    unknown = {c.get('path'): c for c in (prior if isinstance(prior, list) else [])
               if isinstance(c, dict) and c.get('status') == 'unknown_order'}
    return [unknown.get(c['path'], c) for c in current]


def _receive_result(want, result, arrival, ws, *, clock_checks=None):
    """Replace a result atomically; its previous stage receipts remain historical."""
    from copy import deepcopy
    from store_guard import locked_update
    accepted = []
    expected = want['agent_work']
    def mutate(rows):
        for w in rows:
            a = w.get('agent_work') or {}
            if (w.get('id') != want['id'] or not specific(w) or w.get('fulfilled') or w.get('dismissed')
                    or a.get('request_id') != expected['request_id'] or a.get('thread') != arrival.get('thread')
                    or a.get('goal_sha256') != fingerprint(w.get('want', ''))
                    or a.get('goal_sha256') != result.get('goal_sha256')):
                continue
            old = a.get('result')
            if any(a.get(key) for key in ('publishing', 'publication', 'delivery')) and (
                    old is None or a.get('stage_result_sha256') != result_digest(old)):
                raise ValueError('existing publication has no matching result version; reconcile before resuming')
            if old != result:

                if old is not None:
                    a.setdefault('result_revisions', []).append(
                        deepcopy({key:a[key] for key in _RESULT_FIELDS if key in a}))
                for key in _RESULT_FIELDS: a.pop(key, None)
            if clock_checks is not None:
                a['artifact_clock_checks'] = _retain_unknown_checks(a.get('artifact_clock_checks'), clock_checks)
            a.update(status='result_ready', result=result, result_sha256=result_digest(result),
                     result_source=arrival.get('who'), result_ts=arrival.get('ts'))
            accepted.append(True); return rows
        return None
    locked_update(str(ws / 'memory/current-wants.json'), mutate, default=[], reader='want_agent.receive')
    return bool(accepted)


def receive(rows, *, ws=None):
    """Only the configured room's dot or signed reviewer, in the bound request thread."""
    ws = Path(ws or workspace()); changed = 0
    wants = read(ws / 'memory/current-wants.json', [])
    for r in rows:
        if not (r.get('who') == 'dot' or (r.get('who') == 'agent' and r.get('agent_authenticated') is True and r.get('name') in ('Claude Code', 'Muse'))):
            continue
        for m in RESULT.finditer(str(r.get('text', ''))):
            for w in wants:
                a = w.get('agent_work') or {}
                if a.get('request_id') != m[1] or not a.get('thread') or r.get('thread') != a['thread']:
                    continue
                if r.get('name') == 'Muse' and a.get('agent') != 'muse':
                    continue
                try:
                    checks = []
                    result, _ = verify(w, ws, clock_checks=checks)
                    changed += _receive_result(w, result, r, ws, clock_checks=checks)
                except (OSError, ValueError, KeyError, TypeError) as exc:
                    _update(w['id'], m[1], {'result_error': str(exc)[:240]}, ws)
    return changed


def finish(state, publish, notify, complete, save_state, now, *, ws=None, review=None):
    """Publish verified files, then ntfy through deliver, then the existing ending door.

    Every stage is retained on its want; a failed upload/notification is retried
    without fulfilling it. Notification is not evidence Gloria opened it.
    """
    import room_work
    ws = Path(ws or workspace()); lines = []
    for archived in read(ws / 'memory/fulfilled-wants.json', []):
        a = archived.get('agent_work') or {}
        if specific(archived) and archived.get('fulfilled') and a.get('result') and a.get('delivery', {}).get('state') in ('sent', 'acknowledged'):
            close_sources(archived, a['result']['summary'], a.get('publication', {}).get('url', ''), ws)
            item = next((x for x in room_work.board(state)['open'] if x.get('want_request_id') == a.get('request_id')), None)
            if item:
                room_work._close(state, item, 'done', a.get('publication', {}).get('url', ''), now)
                save_state(state)
    for w in read(ws / 'memory/current-wants.json', []):
        a = w.get('agent_work') or {}; rid = a.get('request_id')
        if a.get('status') != 'result_ready':
            continue
        try:
            checks = []
            result, paths = verify(w, ws, clock_checks=checks)
            if result != a.get('result'):
                raise ValueError('result manifest changed after its authenticated arrival')
            revision = result_digest(result)
            if a.get('result_sha256') != revision:
                raise ValueError('result version is not bound to its authenticated arrival')
            if any(a.get(key) for key in ('publishing', 'publication', 'delivery')) and a.get('stage_result_sha256') != revision:
                raise ValueError('publication stages belong to a different or unknown result version')
            if review is not None:
                message = review(w, result)
                if message is None: continue
                result = dict(result, summary=message)
            checks = _retain_unknown_checks(a.get('artifact_clock_checks'), checks)
            if not _update(w['id'], rid, {'stage_result_sha256': revision, 'artifact_clock_checks': checks}, ws, expected_result=revision):
                continue
            a['stage_result_sha256'] = revision
            publication = a.get('publication')
            if not publication:
                publication = publish(w, result, paths)
                if not publication or not publication.get('url'):
                    raise ValueError('deliverables were not published')
                if not _update(w['id'], rid, {'publication': publication}, ws, expected_result=revision):
                    continue
                a['publication'] = publication
            # Keep the first successful receipt stable across local ending retries.
            # Re-entering the delivery door may add repeat metadata, which is not
            # a new event in the persistent working conversation.
            delivery = a.get('delivery')
            if not delivery or delivery.get('state') not in ('sent', 'acknowledged'):
                delivery = notify(rid, result['summary'], publication['url'])
            if not delivery or delivery.get('state') not in ('sent', 'acknowledged'):
                raise ValueError('ntfy delivery unconfirmed; result retained for retry')
            # Persist result before the existing ending door archives the full want.
            if not _update(w['id'], rid, {'delivery': delivery, 'status': 'result_ready', 'completed_at': now, 'completion_message': result['summary']}, ws, expected_result=revision):
                continue
            import want_working_thread as working
            item = working.binding(w, state)
            if item:
                working.append(w, item, ws, 'delivered:' + revision, 'delivery', result['summary'], at=now,
                               details={'publication': publication, 'delivery': delivery, 'acceptance': result['acceptance']})
            outcome = complete(w, result['summary'] + '\nDeliverables: ' + publication['url'])
            if not outcome or outcome.get('result') != 'fulfilled':
                raise ValueError('ending door has not confirmed fulfillment')
            close_sources(w, result['summary'], publication['url'], ws)
            item = next((x for x in room_work.board(state)['open'] if x.get('want_request_id') == rid), None)
            if item:
                room_work._close(state, item, 'done', publication['url'], now)
                save_state(state)
            lines.append('want completed: delivered artifacts and source ending recorded')
        except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
            _update(w['id'], rid, {'result_error': str(exc)[:240]}, ws)
            lines.append('want result retained: ' + str(exc)[:140])
    return lines


def close_sources(want, summary, url, ws):
    from store_guard import locked_update
    promised = (want.get('agent_work') or {}).get('promise_ids') or []
    if promised:
        try:
            import promise_keeper; promise_keeper.close_ids(promised, summary + ((' ' + url) if url else ''))
        except Exception:
            pass
    ids = set((want.get('agent_work') or {}).get('commitment_ids', []))
    if not ids: return
    def mutate(rows):
        changed = False
        for row in rows:
            if row.get('id') in ids and row.get('state') in ('open', 'in work', 'aged out'):
                row.update(state='done', closed_said=summary[:300], result_url=url,
                           fulfilled_want_id=want['id'], closed_at=time.strftime('%Y-%m-%dT%H:%M:%S'))
                changed = True
        return rows if changed else None
    locked_update(str(ws / 'memory/email-commitments.json'), mutate, default=[], reader='want_agent.close_sources')


def block(*, ws=None, limit=6):
    """Durable factual recall in his existing context and email drafts, without generating prose."""
    ws = Path(ws or workspace())
    done = read(ws / 'memory/fulfilled-wants.json', [])
    lines = []
    for w in reversed(done):
        a = w.get('agent_work') or {}
        if w.get('fulfilled') and a.get('result') and a.get('delivery', {}).get('state') in ('sent', 'acknowledged'):
            lines.append('- Completed: %s\n  Result: %s\n  Deliverables: %s' % (w.get('want', '')[:500],
                         a['result'].get('summary', '')[:450], a.get('publication', {}).get('url', '')))
        if len(lines) >= limit: break
    return ('== WORK ALREADY COMPLETED (receipts, not intentions) ==\n' + '\n'.join(lines)
            + '\nThese tasks are done. In letters, report their results; do not promise them again. A new version is new work.') if lines else ''


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('result'); p.add_argument('request_id'); p.add_argument('--summary', required=True)
    p.add_argument('--acceptance', required=True); p.add_argument('--artifact', action='append', required=True)
    p = sub.add_parser('binding'); p.add_argument('request_id'); p.add_argument('--thread', required=True)
    p = sub.add_parser('continue-context'); p.add_argument('request_id')
    p.add_argument('--summary-file', required=True); p.add_argument('--through-event', required=True)
    p = sub.add_parser('reconcile'); p.add_argument('request_id'); p.add_argument('--call', required=True)
    p.add_argument('--outcome', choices=('observed','failed'), required=True)
    p.add_argument('--evidence-file', required=True); p.add_argument('--response-file')
    p.add_argument('--confirm-stopped', action='store_true', required=True)
    args = parser.parse_args(); ws = workspace()
    w = next((w for w in read(ws / 'memory/current-wants.json', [])
              if (w.get('agent_work') or {}).get('request_id') == args.request_id), None)
    if w is None: parser.error('no current want with this exact request')
    if not specific(w): parser.error('request lacks a bound journal/email source')
    if args.command == 'reconcile':
        import want_working_thread as working
        work = working.binding(w, read(ws / 'memory/dot-channel/state.json', {}), respect_pause=False)
        if work is None: parser.error('no current want-room binding')
        root = directory(args.request_id, ws)
        def private_text(filename, limit):
            source=Path(filename).absolute()
            if (source.resolve()!=source or not source.is_relative_to(root)
                    or not source.is_file() or source.stat().st_size>limit):
                parser.error('reconciliation input must be a bounded private file in the request directory')
            return source.read_text()
        evidence=private_text(args.evidence_file,48000)
        response=private_text(args.response_file,60000) if args.response_file else None
        try: working.reconcile(w,work,ws,args.call,args.outcome,evidence,response)
        except ValueError as exc: parser.error(str(exc))
        print(json.dumps({'reconciled':True,'outcome':args.outcome}))
        return
    if args.command == 'continue-context':
        import want_working_thread as working
        work = working.binding(w, read(ws / 'memory/dot-channel/state.json', {}), respect_pause=False)
        if work is None: parser.error('no current want-room binding')
        root = directory(args.request_id, ws)
        source = Path(args.summary_file).absolute()
        if (source.resolve() != source or not source.is_relative_to(root)
                or not source.is_file() or source.stat().st_size > 48000):
            parser.error('summary must be a bounded file in this private request directory')
        data = working.continue_context(w, work, ws, source.read_text(), args.through_event)
        print(json.dumps({'continued':True,'covered_events':data['continuation']['covered_count']}))
        return
    if args.command == 'binding':
        import want_working_thread as working
        work = working.binding(w, read(ws / 'memory/dot-channel/state.json', {}), args.thread)
        if work is None: parser.error('no matching active want-room-thread binding')
        print(json.dumps({'bound': True, 'want_id': w['id'], 'work_id': work['id'], 'request_id': args.request_id}))
        return
    root = directory(args.request_id, ws); root.mkdir(parents=True, exist_ok=True, mode=0o700)
    result = dict(schema=SCHEMA, request_id=args.request_id, goal_sha256=fingerprint(w['want']), status='completed',
                  summary=args.summary[:2000], acceptance=args.acceptance[:4000], artifacts=[])
    for relative in args.artifact:
        checks = []
        path = _artifact(ws, relative, w, clock_checks=checks)
        result['artifacts'].append(dict(path=relative, sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                                        artifact_time=checks[0]))
    if not 1 <= len(result['artifacts']) <= 8: parser.error('one to eight artifacts required')
    from store_guard import write_json
    write_json(str(root / 'result.json'), result)
    verify(w, ws)
    print('WANT RESULT ' + args.request_id)


if __name__ == '__main__':
    main()
