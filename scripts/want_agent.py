"""Join concrete wants to the existing agent room and its delivery/ending doors.

No model, transport, or worker is started here. dot_channel supplies its existing
paused/authorized transport; tests supply stubs. Requests live on their source
rows, room work stays in room_work, and endings use want_completion.
"""
from pathlib import Path
import hashlib
import json
import os
import re
import time
import uuid

RESULT = re.compile(r'^\s*WANT RESULT (WA-[0-9a-f]{24})\s*$', re.M)
BUY = re.compile(r'\b(?:buy|purchase|subscribe|subscription|paid account)\b', re.I)
SCHEMA = 'want-agent-result-v1'


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
    from journal_wants import operational
    return bool(want.get('id') and (want.get('journal_seeded') or want.get('source') in ('idle-journal', 'email', 'letter-promise'))
                and operational(want.get('want', '')))


def bypass(want):
    return bool(want.get('timer_bypass') or ((want.get('journal_seeded') or want.get('source') == 'idle-journal') and specific(want)))


def request(want, reason='', *, ws=None):
    """Bind the entire literal goal; preserve its plan as context, never count a handoff as done."""
    ws = Path(ws or workspace())
    from store_guard import locked_update
    found = []
    def mutate(rows):
        for row in rows:
            if row.get('id') != want.get('id') or row.get('want') != want.get('want') or row.get('fulfilled') or row.get('dismissed'):
                continue
            goal = row.get('want', '')
            digest = fingerprint(goal)
            old = row.get('agent_work') or {}
            if old.get('goal_sha256') == digest:
                found.append(old); return None
            rid = 'WA-' + fingerprint(str(row['id']) + '\0' + digest)[:24]
            rec = dict(request_id=rid, goal_sha256=digest, goal=goal, status='queued',
                       reason=str(reason)[:300], agent='muse' if BUY.search(goal) else 'dot', created_at=time.time())
            # Exact commitment identity only. Related topics or one shared email
            # must never close a different promised experiment.
            commitments = read(ws / 'memory/email-commitments.json', [])
            explicit = {r.get('id') for r in row.get('source_refs', []) if r.get('kind') == 'commitment'}
            rec['commitment_ids'] = [c['id'] for c in commitments if c.get('id') and
                (c['id'] in explicit or any(str(c.get(k, '')).strip() == goal.strip() for k in ('what', 'quote')))]
            row['agent_work'] = rec
            if specific(row) and (row.get('journal_seeded') or row.get('source') == 'idle-journal'):
                row['timer_bypass'] = True
            found.append(rec); return rows
        return None
    locked_update(str(ws / 'memory/current-wants.json'), mutate, default=[], reader='want_agent.request')
    return found[0] if found else None


def _update(wid, rid, changes, ws):
    from store_guard import locked_update
    accepted = []
    def mutate(rows):
        for row in rows:
            a = row.get('agent_work') or {}
            if row.get('id') == wid and a.get('request_id') == rid and a.get('goal_sha256') == fingerprint(row.get('want', '')):
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


def _artifact(ws, relative):
    if not isinstance(relative, str):
        raise ValueError('relative artifact path required')
    path = ws / relative
    if Path(relative).is_absolute() or '..' in Path(relative).parts or path.resolve() != path.absolute():
        raise ValueError('artifact path must be a nonlinked workspace-relative file')
    if not any(path.is_relative_to(ws / prefix) for prefix in ('memory/art', 'memory/want-artifacts')):
        raise ValueError('only output shelves can be delivered')
    if not path.is_file() or not 0 < path.stat().st_size <= 32 * 1024 * 1024:
        raise ValueError('artifact missing, empty or above the delivery budget')
    return path


def verify(want, ws=None):
    """A trusted agent's attestation plus actual hashed files, not a prose 'done'."""
    ws = Path(ws or workspace())
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
    for entry in artifacts:
        path = _artifact(ws, entry['path'])
        if hashlib.sha256(path.read_bytes()).hexdigest() != entry.get('sha256'):
            raise ValueError('artifact changed after the agent reported completion')
        paths.append(path)
    if len(set(paths)) != len(paths) or sum(p.stat().st_size for p in paths) > 64 * 1024 * 1024:
        raise ValueError('duplicate artifacts or total delivery budget exceeded')
    return result, paths


def opening(want, a, wid):
    # JSON quoting prevents a journal's newlines from becoming room control lines.
    return ('WORK REQUEST %s (%s; want %s)\nExact task: %s\n'
            'Source references: %s\nExisting step results (context, not proof of this task): %s\n'
            'Work with me until this deliverable exists. Keep the named tools, inputs, flags and acceptance requirements. '
            'If a download, dependency, account or code change is needed, handle it with your existing permissions; '
            'ask for only an authorization or credential the owner must supply. Code changes remain review branches; '
            'Gloria deploys. Purchases go to @Muse, who uses the existing BUY approval path; this is not permission to spend. '
            'A setup step, a new song, a journal reflection or a plan is not the requested analysis. '
            'Report blockers in this thread and keep working on the other steps. '
            'When the whole task is complete, use scripts/want_agent.py result %s --summary "what was made" '
            '--acceptance "how the exact task was checked, including limits" --artifact memory/art/path '
            '(repeat --artifact for each deliverable), then post WANT RESULT %s on its own line IN THIS THREAD. '
            'That verifies files, delivers them to Gloria and records that I did it. Never put secrets in the artifacts.'
            % (a['request_id'], wid, want['id'], json.dumps(want['want'], ensure_ascii=False), json.dumps(want.get('source_refs', []), ensure_ascii=False),
               json.dumps(want.get('step_history', [])[-4:], ensure_ascii=False)[:1800], a['request_id'], a['request_id']))


def intake(state, post, save_state, now, *, ws=None, identity=None, prepare=None):
    """One new handoff per room pass, respecting room capacity and source identity."""
    import room_work
    ws = Path(ws or workspace()); lines = []
    wants = read(ws / 'memory/current-wants.json', [])
    for w in wants:
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
            body = prepare(w, work, body) + '\n\n' + body
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


def threads(ws=None):
    return [w['agent_work']['thread'] for w in read(Path(ws or workspace()) / 'memory/current-wants.json', [])
            if isinstance(w.get('agent_work'), dict) and w['agent_work'].get('thread')]


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
                    result, _ = verify(w, ws)
                    changed += _update(w['id'], m[1], {'status': 'result_ready', 'result': result,
                                                      'result_source': r.get('who'), 'result_ts': r.get('ts')}, ws)
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
        if archived.get('fulfilled') and a.get('result') and a.get('delivery', {}).get('state') in ('sent', 'acknowledged'):
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
            result, paths = verify(w, ws)
            if result != a.get('result'):
                raise ValueError('result manifest changed after its authenticated arrival')
            if review is not None:
                message = review(w, result)
                if message is None: continue
                result = dict(result, summary=message)
            publication = a.get('publication')
            if not publication:
                publication = publish(w, result, paths)
                if not publication or not publication.get('url'):
                    raise ValueError('deliverables were not published')
                if not _update(w['id'], rid, {'publication': publication}, ws):
                    continue
                a['publication'] = publication
            delivery = notify(rid, result['summary'], publication['url'])
            if not delivery or delivery.get('state') not in ('sent', 'acknowledged'):
                raise ValueError('ntfy delivery unconfirmed; result retained for retry')
            # Persist result before the existing ending door archives the full want.
            if not _update(w['id'], rid, {'delivery': delivery, 'status': 'result_ready', 'completed_at': now, 'completion_message': result['summary']}, ws):
                continue
            import want_working_thread as working
            item = working.binding(w, state)
            if item:
                working.append(w, item, ws, 'delivered', 'delivery', result['summary'], at=now,
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
    ids = set((want.get('agent_work') or {}).get('commitment_ids', []))
    if not ids: return
    def mutate(rows):
        changed = False
        for row in rows:
            if row.get('id') in ids and row.get('state') in ('open', 'in work'):
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
    args = parser.parse_args(); ws = workspace()
    w = next((w for w in read(ws / 'memory/current-wants.json', [])
              if (w.get('agent_work') or {}).get('request_id') == args.request_id), None)
    if w is None: parser.error('no current want with this exact request')
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
        path = _artifact(ws, relative)
        result['artifacts'].append(dict(path=relative, sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    if not 1 <= len(result['artifacts']) <= 8: parser.error('one to eight artifacts required')
    from store_guard import write_json
    write_json(str(root / 'result.json'), result)
    verify(w, ws)
    print('WANT RESULT ' + args.request_id)


if __name__ == '__main__':
    main()
