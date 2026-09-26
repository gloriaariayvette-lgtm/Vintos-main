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
    eligible.sort(key=lambda s: (str(s.get('seen', '')), str(s['key'])))
    if not eligible:
        return None
    # Rotate sources first, then take the oldest unoffered occasion in that source.
    # Row-count rotation let a busy source occupy consecutive passes.
    by_source = {}
    for row in eligible:
        by_source.setdefault(str(row.get('source', '')), []).append(row)
    source_order = sorted(by_source)
    source = source_order[int(now.timestamp() // 3600) % len(source_order)]
    s = by_source[source][0]
    return {'source': s['source'], 'source_event_id': 'spark:' + s['key'],
            'context': 'SOURCE OCCASION (not a want; you may decline):\n' + str(s['text'])[:700]}
