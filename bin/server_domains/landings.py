"""Landings routes: Gloria's notes on how each thing he made landed, and why (2026-09-24).

Her side only. The store lives outside his workspace (scripts/landings.py); nothing here
feeds his context, and nothing here counts or flags what she has not rated.
"""
import os, sys
from fastapi import APIRouter, Body, HTTPException, Request

for _p in (os.path.expanduser("~/.vintos/workspace/scripts"),
           os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "scripts")):
    if os.path.isdir(_p) and _p not in sys.path: sys.path.append(_p)
import landings as _l
from house_auth import configured_secret as _house_secret, matches as _house_matches

router = APIRouter()
_SECRET = _house_secret(log=False)   # "" when unconfigured: every write below refuses


def _owner(request):
    """Her notes flow into GLORIA-MODEL.md: only the house credential may write one."""
    if not _house_matches(request.headers.get("X-Vintos-Secret", ""), _SECRET):
        raise HTTPException(status_code=401, detail="Unauthorized")


@router.get("/api/landings/sent")
async def landings_sent(days: int = 7):
    """What he sent her (delivered videos, messages he started) in the last days."""
    return {"items": _l.sent(days=max(1, min(days, 30)))}


@router.get("/api/landings/context")
async def landing_context(surface: str, ref: str):
    """What will be kept beside her note: what he meant, and the conversation before it."""
    try:
        ctx = _l.context(surface, ref)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if ctx is None:
        raise HTTPException(status_code=404, detail="no %s called %r" % (surface, ref))
    return ctx


@router.get("/api/landings")
async def landings_notes(days: int = 0):
    return {"notes": _l.notes(days=days or None)}


@router.post("/api/landings")
async def landing_record(request: Request, body: dict = Body(...)):
    _owner(request)
    try:
        row = _l.record(body.get("surface"), body.get("ref"), body.get("rating"), body.get("why"),
                        body.get("before", ""))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"ok": True, "id": row["id"]}


# ---- what her notes become (landing_understanding.py, 2026-10-16) ------------------------------
# Her rating is her consent: what her notes say about her goes into GLORIA-MODEL.md with no second yes.

@router.get("/api/landings/understanding")
async def landing_understanding_read():
    import landing_understanding as _u
    return {"understood": _u._load(_u.APPROVED, [])}
