"""Passive phone-distance routing for lights. No model calls or device commands.

Only live enrolled-phone MQTT messages count; retained, stale, non-finite and
ambiguous evidence never select a room. Bathroom reports are steam-qualified by
house-steam firmware and are invalidated immediately by steam_end/near=off.
"""
import json
import math
import os
import tempfile
import time

WS = os.environ.get('SPARK_WORKSPACE') or os.path.expanduser('~/.vintos/workspace')
STATE = os.path.join(WS, 'memory', 'room-proximity.json')
ROOMS = ('bedroom', 'bathroom', 'office', 'balcony', 'living_room', 'kitchen', 'laundry_room')
ALIASES = {'house-steam': 'bathroom', 'house-touch': 'office',
           'house-press-mic': 'living_room', 'living': 'living_room', 'laundry': 'laundry_room'}
FRESH_S = 30
MAX_DISTANCE_M = 3.0


def room_key(room):
    raw = str(room or '').strip().lower()
    # Board topic aliases have hyphens; ordinary room names accept spaces/hyphens.
    return ALIASES.get(raw, ALIASES.get(raw.replace('-', '_').replace(' ', '_'),
                                     raw.replace('-', '_').replace(' ', '_')))


def _load():
    try:
        with open(STATE) as f:
            value = json.load(f)
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(value):
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    fd, path = tempfile.mkstemp(prefix='.room-proximity-', dir=os.path.dirname(STATE))
    try:
        with os.fdopen(fd, 'w') as f:
            json.dump(value, f)
        os.replace(path, STATE)
    finally:
        if os.path.exists(path):
            os.unlink(path)


def reset():
    """A restarted subscriber must hear fresh readings before controlling a room."""
    _save({'rooms': {}})


def observe(topic, payload, retained=False, now=None):
    if retained:
        return False
    now = time.time() if now is None else now
    text = payload.decode('utf-8', 'replace') if isinstance(payload, bytes) else str(payload)
    if topic in ('vintos/board/house-steam/near', 'vintos/board/house-steam/event'):
        if text.strip() in ('off', 'steam_end'):
            st = _load()
            st.setdefault('rooms', {}).pop('bathroom', None)
            _save(st)
            return True
        return False
    parts = topic.split('/')
    if len(parts) != 4 or parts[:2] != ['espresense', 'devices'] or parts[2] != 'gloria-phone':
        return False
    room = room_key(parts[3])
    if room not in ROOMS:
        return False
    # Only the existing steam-qualified board may supply bathroom proximity.
    if room == 'bathroom' and parts[3] != 'house-steam':
        return False
    try:
        raw = json.loads(text).get('distance')
        if isinstance(raw, bool):
            return False
        distance = float(raw)
        if not math.isfinite(distance) or distance < 0:
            return False
    except (ValueError, TypeError, AttributeError):
        return False
    st = _load()
    st.setdefault('rooms', {})[room] = {'distance': distance, 'seen': now}
    _save(st)
    return True


def nearest(now=None, state=None):
    now = time.time() if now is None else now
    st = _load() if state is None else state
    candidates = []
    for room, row in st.get('rooms', {}).items():
        if room not in ROOMS or not isinstance(row, dict):
            continue
        d, seen = row.get('distance'), row.get('seen')
        if (type(d) not in (int, float) or type(seen) not in (int, float)
                or not math.isfinite(d) or not math.isfinite(seen)
                or not 0 <= now - seen <= FRESH_S or not 0 <= d <= MAX_DISTANCE_M):
            continue
        candidates.append((d, room))
    candidates.sort()
    if not candidates:
        raise ValueError('no fresh nearby phone reading; name a room explicitly')
    if len(candidates) > 1 and candidates[1][0] - candidates[0][0] <= max(0.3, candidates[0][0] * 0.15):
        raise ValueError('phone proximity is ambiguous between rooms; name a room explicitly')
    return candidates[0][1]
