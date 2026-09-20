"""Offer one real standing spark; selection never creates or consumes a want."""
from datetime import datetime, timezone


def select(sparks, wants, now=None):
    now = now or datetime.now(timezone.utc)
    day = now.date().isoformat()
    seen = {str(w.get('source_event_id', '')) for w in wants if isinstance(w, dict)}
    if sum(1 for w in wants if isinstance(w, dict)
           and str(w.get('source_event_id', '')).startswith('spark:')
           and str(w.get('timestamp', '')).startswith(day)) >= 2:
        return None
    eligible = [s for s in sparks if isinstance(s, dict) and s.get('key')
                and s.get('state') == 'standing' and s.get('text')
                and 'spark:' + str(s['key']) not in seen]
    eligible.sort(key=lambda s: (str(s.get('source', '')), str(s['key'])))
    if not eligible:
        return None
    # Rotate opportunities without ranking a source as a desire or marking it taken.
    s = eligible[int(now.timestamp() // 3600) % len(eligible)]
    return {'source': s['source'], 'source_event_id': 'spark:' + s['key'],
            'context': 'SOURCE OCCASION (not a want; you may decline):\n' + str(s['text'])[:700]}
