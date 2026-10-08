"""Owner-authorized, one-day operational quotas. No counter or authority changes.

The reviewed October 7 ceiling and October 8 fresh-credit grants are supported.
Missing, malformed, excessive or expired configuration retains ordinary limits.
This does not grant paid execution, permissions, or authority over any project.
"""
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ZONE = ZoneInfo("America/Chicago")
AUTHORIZED_DAY = "2026-10-07"
AUTHORIZATION = "slack:1791402204.566209"
CREDIT_DAY = "2026-10-08"
CREDIT_AUTHORIZATION = "chatgpt:Sentinel_5f64eaa33e78819181faaa8077e5dcd9"
CONFIG = Path(__file__).with_name("software-quota-override.json")


def today():
    return datetime.now(ZONE).date().isoformat()


def _unique(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError("duplicate quota field")
        out[key] = value
    return out


def preserves_usage(day):
    """Both approved campaign dates count all submissions, even with an old reset."""
    return day in (AUTHORIZED_DAY, CREDIT_DAY)


def _credit(data, day, historical):
    fields = {"schema", "date", "timezone", "authorization", "limits", "usage_baseline",
              "recorded_at", "expires_at", "meaning"}
    if not isinstance(data, dict) or set(data) != fields:
        return None
    if type(data["schema"]) is not int or data["schema"] != 2:
        return None
    if (data["date"], data["timezone"], data["authorization"]) != (CREDIT_DAY, "America/Chicago", CREDIT_AUTHORIZATION):
        return None
    for field, expected in (("limits", {"forge": 10, "study": 10}),
                            ("usage_baseline", {"forge": 3, "study": 1})):
        values = data[field]
        if not isinstance(values, dict) or values != expected or any(type(v) is not int for v in values.values()):
            return None
    recorded = datetime.fromisoformat(data["recorded_at"])
    expires = datetime.fromisoformat(data["expires_at"])
    if recorded.tzinfo is None or expires.tzinfo is None:
        return None
    if recorded.astimezone(ZONE).date().isoformat() != CREDIT_DAY:
        return None
    if expires.isoformat() != "2026-10-09T05:00:00+00:00" or recorded >= expires:
        return None
    if not historical and not recorded <= datetime.now(ZONE) < expires:
        return None
    return data


def campaign(day=None):
    """Validated dated grant, or None. Never writes or resets a ledger."""
    selected = day or today()
    if not preserves_usage(selected):
        return None
    try:
        with open(CONFIG, "rb") as stream:
            raw = stream.read(4097)
        if len(raw) > 4096:
            return None
        data = json.loads(raw, object_pairs_hook=_unique)
        if selected == CREDIT_DAY:
            return _credit(data, selected, day is not None)
        if not isinstance(data, dict) or set(data) != {"schema", "date", "timezone", "authorization", "limits"}:
            return None
        if type(data["schema"]) is not int or data["schema"] != 1:
            return None
        if (data["date"], data["timezone"], data["authorization"]) != (AUTHORIZED_DAY, "America/Chicago", AUTHORIZATION):
            return None
        limits = data["limits"]
        if not isinstance(limits, dict) or set(limits) != {"forge", "study"}:
            return None
        if any(type(v) is not int or not 3 <= v <= 10 for v in limits.values()):
            return None
        return data
    except (OSError, ValueError, TypeError, KeyError, AttributeError, UnicodeError, RecursionError):
        return None


def limit(lane, ordinary, day=None):
    grant = campaign(day)
    if not grant or lane not in grant["limits"]:
        return ordinary
    return grant["limits"][lane] + grant.get("usage_baseline", {}).get(lane, 0)
