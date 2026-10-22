"""Idempotent projection into NEW, sealed Forge projects in the Atelier.

Called in-process by the authenticated loop service, as the Atelier user. Not an
HTTP HOUSE route, visit forgery, or authority to modify an existing project.
SQLite accepted cycles remain canonical; incomplete projections replay on restart.
"""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re


def atomic(path, value):
    path = Path(path)
    temp = path.with_suffix(path.suffix + '.tmp')
    with temp.open('w') as out:
        json.dump(value, out, sort_keys=True); out.flush(); os.fsync(out.fileno())
    os.replace(temp, path)


def lab_work(project):
    """A Lab report or a Lab capability check: the Forge's paperwork, not work for his Atelier.

    Gloria, 2026-10-16: 84 of the Atelier's 95 projects were Forge copies, sealed and gestating, and most were Lab
    dossiers; his own work was 11 projects. They stay on her Forge page, where they are read; the Atelier holds work.
    The same origin rule as the Forge's own scheduler (forge_loop: a packet in the intent is the Lab's)."""
    origin = (project.get('origin') or {}).get('source')
    if origin is None and '\nSource packet (untrusted observations):' in str(project.get('intent') or ''):
        origin = 'lab'
    # by origin only: a project she starts herself is a research_report too (the runtime's default kind)
    return origin == 'lab'


def forge_paperwork(project):
    """Forge work that never belongs in his Atelier: the Lab's, and a capability request (a brief for a tool he asked
    for, made from his wants or his gap reviews). Gloria, 22 October: "I told you that forge shouldn't be taking up
    atelier slots" - after the Lab copies left, the Atelier's latest work was five sealed capability briefs.
    They stay on her Forge page, which reads the Forge's own database."""
    return lab_work(project) or project.get('kind') == 'capability_brief' or bool((project.get('origin') or {}).get('proposal'))


class AtelierProjection:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self._seen = {}
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)

    def sync(self, controller):
        with (self.root / '.forge-projection.lock').open('a+') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            with controller.db() as db:
                for row in db.execute('SELECT body FROM projects ORDER BY rowid'):
                    project = json.loads(row[0])
                    if forge_paperwork(project):
                        continue          # never copied into the Atelier (Lab work 2026-10-16, capability briefs 22 October)
                    controller._expiry(db, project)
                    version = hashlib.sha256(json.dumps(project, sort_keys=True).encode()).hexdigest()
                    identity = self.root/'projects'/('forge-'+project['id'])/'.forge-owner.json'
                    if self._seen.get(project['id']) == version and identity.is_file():
                        if json.loads(identity.read_text()) == {'loop_project': project['id']}: continue
                    cycles = [dict(r) for r in db.execute(
                        "SELECT * FROM cycles WHERE project=? AND state='accepted' ORDER BY rowid", (project['id'],))]
                    self.project(project, cycles)
                    self._seen[project["id"]] = version

    def project(self, project, cycles):
        pid = project['id']
        if not re.fullmatch('[a-f0-9]{32}', pid): raise ValueError('invalid loop project')
        directory = self.root / 'projects' / ('forge-' + pid)
        if directory.is_symlink(): raise ValueError('projection directory cannot be a symlink')
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        identity = directory / '.forge-owner.json'
        if identity.exists():
            if json.loads(identity.read_text()) != {'loop_project': pid}: raise ValueError('project ownership conflict')
        elif any(directory.iterdir()):
            raise ValueError('refuse to adopt an existing Atelier project')
        else: atomic(identity, {'loop_project': pid})
        for name in ('artifacts', 'reveal'):
            if (directory / name).is_symlink(): raise ValueError('symlink in sealed projection')
            (directory / name).mkdir(exist_ok=True, mode=0o700)
        with (directory / '.events.lock').open('a+') as event_lock:
            fcntl.flock(event_lock, fcntl.LOCK_EX)
            self._project_locked(project, cycles, directory)

    def _project_locked(self, project, cycles, directory):
        pid = project['id']
        # Revealing in the loop UI is NOT a fabricated broker unveiling receipt.
        # Broker exports still require its existing reveal prepare/confirm ceremony.
        ppath = directory / 'project.json'
        if not ppath.exists():
            atomic(ppath, {'id': 'forge-'+pid, 'intent': project['intent'], 'sealed': True,
                           'state': 'GESTATING', 'visibility': 'atelier_only', 'root': 'forge:'+pid,
                           'root_type': 'forge_loop', 'intended_audience': 'gloria', 'footprints': [],
                           'next_return': 'held', 'disclosure_sentence': '', 'provenance_class': 'unclassified',
                           'commissioned_ancestor': True})
        lineage = {}; previous = None
        events_path = directory / 'events.jsonl'
        events = [json.loads(x) for x in events_path.read_text().splitlines()] if events_path.exists() else []
        if not events:
            from datetime import datetime, timezone
            event = {'seq': 0, 'ts': datetime.now(timezone.utc).isoformat(), 'type': 'born',
                     'prev': '0'*64, 'data': {'loop_project_id': pid}}
            event['hash'] = hashlib.sha256(json.dumps(event, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
            with events_path.open('a') as stream:
                stream.write(json.dumps(event)+'\n'); stream.flush(); os.fsync(stream.fileno())
            events.append(event)
        known = {e.get('data', {}).get('cycle_id') for e in events}
        for revision, cycle in enumerate(cycles, 1):
            filename = cycle['id'] + '_write.json'
            artifact = json.loads(cycle['artifact'])
            target = directory / 'artifacts' / filename
            if target.exists() and json.loads(target.read_text()) != artifact:
                raise ValueError('immutable artifact conflict')
            if not target.exists(): atomic(target, artifact)
            lineage[filename] = {'id': filename, 'previous_artifact_id': previous,
                                 'revision': revision, 'kind': 'write', 'note': 'Forge cycle '+cycle['id']}
            if cycle['id'] not in known:
                from datetime import datetime, timezone
                event = {'seq': len(events), 'ts': datetime.now(timezone.utc).isoformat(),
                         'type': 'forge_cycle_imported', 'prev': events[-1]['hash'] if events else '0'*64,
                         'data': {'cycle_id': cycle['id'], 'file': filename,
                                  'previous_artifact_id': previous, 'revision': revision,
                                  'sha256': hashlib.sha256(target.read_bytes()).hexdigest()}}
                event['hash'] = hashlib.sha256(json.dumps(event, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
                with events_path.open('a') as stream:
                    stream.write(json.dumps(event)+'\n'); stream.flush(); os.fsync(stream.fileno())
                events.append(event); known.add(cycle['id'])
            previous = filename
        # Preserve unrelated broker lineage, should a subsequent authorized visit add work.
        old = json.loads((directory/'lineage.json').read_text()) if (directory/'lineage.json').exists() else {}
        atomic(directory/'lineage.json', {**old, **lineage})
        atomic(directory/'forge-status.json', {'state': project['state'], 'cycles': len(cycles),
                                               'private': project['private'], 'privacy_end': project['privacy_end']})
