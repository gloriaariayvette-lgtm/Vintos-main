"""Owner-authorized, one-day operational quotas. No counter or authority changes.

Install the reviewed JSON beside this module to activate the October 7 campaign.
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


def campaign(day=None):
    """Validated dated grant, or None. Never writes or resets a ledger."""
    if (day or today()) != AUTHORIZED_DAY:
        return None
    try:
        with open(CONFIG, "rb") as stream:
            raw = stream.read(4097)
        if len(raw) > 4096:
            return None
        data = json.loads(raw, object_pairs_hook=_unique)
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
    except (OSError, ValueError, TypeError, UnicodeError, RecursionError):
        return None


def limit(lane, ordinary, day=None):
    grant = campaign(day)
    return grant["limits"].get(lane, ordinary) if grant else ordinary
