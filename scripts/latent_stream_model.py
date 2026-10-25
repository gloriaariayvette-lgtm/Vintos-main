#!/usr/bin/env python3
"""Portable present-moment readout and incremental state; no stores or providers."""
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

SCHEMA = 'present-moment-v1'
SOURCES = ['emotion', 'inner', 'thread', 'creative', 'her', 'him']
AXES = ['Valence', 'Arousal', 'Dominance', 'Safety', 'Desire', 'Connection',
        'Playfulness', 'Curiosity', 'Warmth', 'Tension', 'Groundedness']


def stamp(value):
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, (int, float)):
        dt = datetime.fromtimestamp(value, timezone.utc)
    else:
        dt = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    if dt.tzinfo is None:
        raise ValueError('event timestamps must carry a timezone')
    return dt


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    default=str, allow_nan=False).encode()).hexdigest()


def event_id(event):
    return event.get('id') or digest({k: event[k] for k in ('t', 'source', 'text', 'vec', 'emo') if k in event})


def save(path, arrays, metadata):
    meta = dict(metadata, schema=SCHEMA, history=False, sources=SOURCES, emotion_axes=AXES)
    # Serialize parameters without rounding. The original optimizer uses float64 weights.
    np.savez_compressed(path, meta=json.dumps(meta, sort_keys=True), **arrays)
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class Model:
    def __init__(self, path):
        with np.load(path, allow_pickle=False) as z:
            self.meta = json.loads(str(z['meta']))
            self.a = {k: z[k] for k in z.files if k != 'meta'}
        m, a = self.meta, self.a
        if (m.get('schema') != SCHEMA or m.get('history') is not False or
                m.get('sources') != SOURCES or m.get('emotion_axes') != AXES or
                m.get('clock') not in ('none', 'hour', 'week')):
            raise ValueError('incompatible present-moment schema')
        self.tz = ZoneInfo(m['timezone'])
        self.dim, self.dz = a['P'].shape
        self.hdim = self.dz + len(AXES) + len(SOURCES) + 2 + {'none': 0, 'hour': 2, 'week': 4}[m['clock']]
        shapes = {'mu': (self.dim,), 'emo_mu': (11,), 'emo_sd': (11,),
                  'W': (self.dz, self.hdim), 'Bm': (self.hdim, 11),
                  'beta': (), 'gamma': (), 'scale': ()}
        for k, shape in shapes.items():
            if a[k].shape != shape or not np.isfinite(a[k]).all():
                raise ValueError('invalid parameter ' + k)
        if not np.isfinite(a['P']).all() or np.any(a['emo_sd'] <= 0) or a['scale'] <= 0:
            raise ValueError('invalid projection or scales')
        self.checkpoint_id = hashlib.sha256(Path(path).read_bytes()).hexdigest()

    def scores(self, state, candidates):
        v = np.asarray(candidates, dtype=np.float32)
        if v.ndim != 2 or v.shape[1] != self.dim or not np.isfinite(v).all():
            raise ValueError('invalid candidate vectors')
        a, h = self.a, state.features()
        z = ((v - a['mu']) @ a['P']).astype(np.float32)
        return a['beta'] * (state.last @ v.T) + a['gamma'] * (state.mean() @ v.T) + (h @ a['W'].T) @ z.T

    def query(self, state):
        a = self.a
        return a['beta'] * state.last + a['gamma'] * state.mean() + a['P'] @ (a['W'] @ state.features())

    def emotion(self, state):
        return state.emo + (state.features() @ self.a['Bm']) * self.a['emo_sd']


class State:
    def __init__(self, model, payload=None):
        self.model = model
        self.last = np.zeros(model.dim, np.float32)
        self.six = []
        self.emo = model.a['emo_mu'].copy()
        self.has_emotion = False
        self.at = self.text_at = None
        self.source = 'emotion'
        self.cursor = None
        self.seen = set()
        self._legacy = False
        self.observed_at = None
        if payload:
            if payload['checkpoint_id'] != model.checkpoint_id:
                raise ValueError('state checkpoint mismatch')
            self.last = self._vector(payload['last'], model.dim)
            self.six = [self._vector(v, model.dim) for v in payload['six']][-6:]
            self.emo = self._vector(payload['emo'], 11)
            self.has_emotion = bool(payload['has_emotion'])
            self.at = stamp(payload['at']) if payload['at'] else None
            self.text_at = stamp(payload['text_at']) if payload['text_at'] else None
            self.source, self.cursor = payload['source'], payload['cursor']
            self.seen = set(payload.get('seen', []))
            # Legacy state had only the event-time cursor; its backlog is not re-folded.
            self._legacy = 'seen' not in payload and self.at is not None
            self.observed_at = payload.get('observed_at')
            if self.source not in SOURCES:
                raise ValueError('unknown source')

    @staticmethod
    def _vector(value, dim):
        a = np.asarray(value, np.float32)
        if a.shape != (dim,) or not np.isfinite(a).all():
            raise ValueError('invalid event vector')
        return a

    def mean(self):
        if not self.six:
            return np.zeros_like(self.last)
        v = np.mean(self.six, axis=0)
        return v / (np.linalg.norm(v) or 1.)

    def features(self):
        a, clock = self.model.a, self.model.meta['clock']
        z = (self.last - a['mu']) @ a['P'] if self.six else np.zeros(self.model.dz)
        age = math.log1p(max(0., (self.at - self.text_at).total_seconds() / 60)) if self.text_at else 0.
        loc = self.at.astimezone(self.model.tz) if self.at else datetime(1970, 1, 1, tzinfo=self.model.tz)
        angle = (loc.hour + loc.minute / 60) / 24 * 2 * math.pi
        clk = [math.sin(angle), math.cos(angle)] if clock in ('hour', 'week') else []
        if clock == 'week':
            clk += [math.sin(loc.weekday() / 7 * 2 * math.pi), math.cos(loc.weekday() / 7 * 2 * math.pi)]
        return np.concatenate([z, (self.emo-a['emo_mu'])/a['emo_sd'],
                               [float(self.source == s) for s in SOURCES], [age], clk, [1.]]).astype(np.float32)

    def advance(self, event, observed_at=None):
        """Ingest once, without rewinding the event-time cursor. Score the preceding state once.

        The ingestion cursor (``seen``) is kept separate from the event-time cursor
        (``at``/``cursor``): a true duplicate is one already ingested, not merely one
        whose time precedes the frontier. A late-arriving event (written now but stamped
        before the frontier, e.g. a journal section or a merged turn) still folds into
        ``last``/``six`` so it reaches him, but does not drag the frontier backwards; its
        outcome stays ``replay`` (the caller never relabels an old-timestamped frame
        prospective). Returned errors are raw cosine / standardized MSE, never probabilities.
        """
        at, eid = stamp(event['t']), event_id(event)
        if eid in self.seen:
            return None                              # already ingested
        late = bool(self.at and at < self.at)        # arrived after the frontier passed its time
        if late and self._legacy:
            self.seen.add(eid)                       # no ingestion record carried: do not re-fold the backlog
            return None
        source = event['source']
        if source not in SOURCES:
            raise ValueError('unknown event source')
        vec = self._vector(event['vec'], self.model.dim) if event.get('vec') is not None else None
        emo = self._vector(event['emo'], 11) if event.get('emo') is not None else None
        if vec is None and emo is None:
            raise ValueError('event has no observed content')
        result = {'event_id': eid, 'source': source, 'at': at.isoformat(), 'before_cursor': self.cursor,
                  'checkpoint_id': self.model.checkpoint_id, 'kind': 'replay'}
        if self.at and vec is not None and self.six:
            q = self.model.query(self)
            result['text_error'] = float(1 - (q @ vec) / max(np.linalg.norm(q)*np.linalg.norm(vec), 1e-12))
            result['last_text_error'] = float(1 - self.last @ vec)
            result['target'] = 'next_text'
        if self.at and emo is not None and self.has_emotion:
            sd = self.model.a['emo_sd']
            result['emotion_error'] = float(np.mean(((self.model.emotion(self)-emo)/sd)**2))
            result['persistence_error'] = float(np.mean(((self.emo-emo)/sd)**2))
            result['target'] = 'next_emotion_reading'
        self.seen.add(eid)
        if vec is not None:
            self.last = vec
            self.six = (self.six + [vec])[-6:]
            if not late:
                self.text_at = at
        if emo is not None and not late:
            self.emo, self.has_emotion = emo, True
        if not late:
            self.at, self.source, self.cursor = at, source, eid
        self.observed_at = stamp(observed_at or datetime.now(timezone.utc)).isoformat()
        return result

    def dump(self):
        return {'checkpoint_id': self.model.checkpoint_id, 'last': self.last.tolist(),
                'six': [v.tolist() for v in self.six], 'emo': self.emo.tolist(),
                'has_emotion': self.has_emotion, 'at': self.at.isoformat() if self.at else None,
                'text_at': self.text_at.isoformat() if self.text_at else None,
                'source': self.source, 'cursor': self.cursor, 'seen': sorted(self.seen),
                'observed_at': self.observed_at}
