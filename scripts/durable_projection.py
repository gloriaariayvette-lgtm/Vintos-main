"""Idempotent local projection writes. Corruption is never an empty destination."""
import json
import os
import tempfile
from store_guard import transaction, write_json


def append_once(path, event_id, payload, jsonl=False):
    with transaction(path):
        try:
            with open(path) as handle:
                rows = ([json.loads(line) for line in handle if line.strip()]
                        if jsonl else json.load(handle))
        except FileNotFoundError:
            rows = []
        if not isinstance(rows, list):
            raise ValueError('projection must be a list')
        if any(row.get('transition_id') == event_id for row in rows):
            return event_id
        rows.append(dict(payload, transition_id=event_id))
        if not jsonl:
            write_json(path, rows)
            return event_id
        fd, temporary = tempfile.mkstemp(dir=os.path.dirname(path), prefix='.projection-')
        try:
            with os.fdopen(fd, 'w') as handle:
                for row in rows:
                    handle.write(json.dumps(row, ensure_ascii=False) + '\n')
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        return event_id
