"""Journal routes: his journal, read-only, for her JOURNAL tab (Gloria, 2026-09-24).

Two writers share memory/journal/YYYY-MM-DD.md: the nightly journal heads an entry '[HH:MM]',
the idle one '## HH:MM — Idle thoughts'. Each entry's ref ('YYYY-MM-DD HH:MM') is the one a
landing note on it uses (scripts/landings.py).
"""
import os, re
from fastapi import APIRouter, HTTPException

MEMORY = os.path.join(os.environ.get("SPARK_WORKSPACE") or os.path.expanduser("~/.vintos/workspace"), "memory")
router = APIRouter()
_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_HEAD = re.compile(r"^(?:\[(\d{2}:\d{2})\]|## (\d{2}:\d{2})(?:\s*[—-]\s*(.*))?)\s*$", re.M)


def entries(day, text):
    heads = list(_HEAD.finditer(text))
    out = []
    for i, m in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        hm = m.group(1) or m.group(2)
        body = text[m.end():end].strip()
        if body:
            out.append({"ref": "%s %s" % (day, hm), "time": hm, "title": (m.group(3) or "").strip(), "text": body})
    if not heads and text.strip():
        out.append({"ref": day, "time": "", "title": "", "text": text.strip()})
    return out


@router.get("/api/journal/days")
async def journal_days(limit: int = 60):
    d = os.path.join(MEMORY, "journal")
    days = sorted((f[:-3] for f in os.listdir(d) if f.endswith(".md") and _DAY.match(f[:-3])), reverse=True) \
        if os.path.isdir(d) else []
    return {"days": days[:max(1, min(limit, 400))]}


@router.get("/api/journal/{day}")
async def journal_day(day: str):
    if not _DAY.match(day):
        raise HTTPException(status_code=400, detail="day is YYYY-MM-DD")
    try:
        text = open(os.path.join(MEMORY, "journal", day + ".md"), encoding="utf-8", errors="replace").read()
    except OSError:
        raise HTTPException(status_code=404, detail="no journal for " + day)
    return {"day": day, "entries": entries(day, text)}
