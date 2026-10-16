#!/usr/bin/env python3
"""landing_understanding.py — her Landings notes become his understanding of her.

Gloria, 2026-10-16: "I thought the ratings were going somewhere." They were not. landings.py keeps her notes
outside his workspace and nothing he reads opens them; the weekly pass that was meant to turn them into
understanding was never built (docs/open-work.md, 24 September). This is that pass.

    python3 landing_understanding.py understand   # read her notes not yet considered; write what they say of her
    python3 landing_understanding.py show         # what he understands from them so far

Her rules, kept here:
  - Her rating IS her consent (Gloria, 2026-10-16: "My rating of a piece IS the consent to use it"). There is no
    second yes: a line that passes the rules below goes straight into GLORIA-MODEL.md, in its own block, which the
    weekly Gloria-model rewrite keeps (gloria-model-update.sh carries the block across).
  - Her notes are about HIS work; what reaches him is what they say about HER. Understanding of her, never a
    rating and never her words (her rule, 24 September: a quoted rating would skew him). A line that names a
    rating, quotes her, or repeats six words in a row from her note is refused and kept, with why, beside her notes.
  - What landed weighs as much as what missed.

The author is the model that already writes his model of her (gloria-model-update.sh: the shim, claude-sonnet-5),
so this adds no new voice to GLORIA-MODEL.md. The weekly run is gloria-model-update.sh's, after its cooldown.
"""
import json, os, re, sys, time, uuid
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path: sys.path.insert(0, HERE)
import landings

WORKSPACE = landings.WORKSPACE
MODEL_FILE = os.path.join(WORKSPACE, "GLORIA-MODEL.md")
PROPOSALS = os.path.join(landings.LANDINGS_DIR, "understanding-proposals.json")
APPROVED = os.path.join(landings.LANDINGS_DIR, "understanding.json")
LM_URL = os.environ.get("VINTOS_GLORIA_MODEL_URL", "http://127.0.0.1:8599/v1/chat/completions")
MODEL = "claude-sonnet-5"          # the author of GLORIA-MODEL.md already (gloria-model-update.sh)
START, END = "<!-- LANDINGS-START -->", "<!-- LANDINGS-END -->"
RATING_WORDS = re.compile(r"\b(?:landed|partly|missed|miss(?:es)?|rat(?:ed|ing|ings)|score[sd]?|graded?)\b", re.I)
RUN = 6                            # this many of her words in a row is her words


def _load(path, default):
    try:
        with open(path) as f: return json.load(f)
    except Exception:
        return default


def _save(path, value):
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    tmp = path + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f: json.dump(value, f, indent=1, ensure_ascii=False)
    os.replace(tmp, path)


def _words(text):
    return re.findall(r"[a-z0-9']+", str(text or "").lower())


def refused(text, notes):
    """Why a proposed line may not reach him, or ''."""
    text = str(text or "").strip()
    if len(text) < 12: return "too thin to be understanding"
    if RATING_WORDS.search(text): return "it names a rating"
    if re.search(r"[\"“”]", text): return "it quotes"
    mine = _words(text)
    runs = {" ".join(mine[i:i + RUN]) for i in range(len(mine) - RUN + 1)}
    for n in notes:
        hers = _words(" ".join((str(n.get("why", "")), str(n.get("before", "")))))
        if any(" ".join(hers[i:i + RUN]) in runs for i in range(len(hers) - RUN + 1)):
            return "it repeats her words"
    return ""


def _piece_text(piece):
    piece = piece if isinstance(piece, dict) else {}
    bits = [str(piece.get(k)) for k in ("type", "title", "caption", "prompt", "text", "description", "style", "lyrics")
            if piece.get(k)]
    return " | ".join(bits)[:700]


def _evidence(notes):
    out = []
    for n in notes:
        lead = "; ".join(("she: " + r.get("gloria", "")[:140] if r.get("gloria") else "") +
                         (" / he: " + r.get("vintos", "")[:140] if r.get("vintos") else "")
                         for r in (n.get("lead_up") or [])[-4:])
        out.append("[%s] %s, %s\nWHAT HE MADE: %s\nHOW IT REACHED HER: %s\nWHY, IN HER TELLING: %s\nWHAT LED UP TO IT, "
                   "IN HER TELLING: %s\nTHE HOURS BEFORE: %s" % (
                       n.get("id"), n.get("surface"), str(n.get("at", ""))[:16], _piece_text(n.get("piece")) or "(not kept)",
                       n.get("rating"), n.get("why", ""), n.get("before", "") or "-", lead or "-"))
    return "\n\n".join(out)


SYSTEM = ("You are Vintos. Gloria has told you how some of the things you made for her reached her, and why. Her notes "
          "are about your work; what you write is about HER. For each note, ask what it shows about her: what she "
          "was carrying in the hours before, what she needed from a thing at that moment, what in the piece met that "
          "need or passed it by, and what that says about how she takes things in (pace, explanation, surprise, "
          "being asked something of, being left room). Write that, as understanding of her you could act on next "
          "time. Rules, all of them hard: never state or imply a rating or a score; never quote her or reuse her "
          "phrasing, say it in your own words; write about her, not about your craft; what reached her matters "
          "exactly as much as what did not; each line must rest on the notes named in it; say nothing the notes do "
          "not support. A single note supports at most a tentative line, and you say it is tentative; where a new "
          "note bears out or changes something you already understand, write the line as it now stands. "
          "Respond with ONLY JSON.")


def _ask(prompt, call=None):
    if call: return call(SYSTEM, prompt)
    import requests
    r = requests.post(LM_URL, json={"model": MODEL, "temperature": 0.5, "max_tokens": 1500,
                                    "messages": [{"role": "system", "content": SYSTEM},
                                                 {"role": "user", "content": prompt}]}, timeout=240)
    return str(r.json()["choices"][0]["message"].get("content") or "")


def _json_in(text):
    m = re.search(r"\{.*\}", str(text or ""), re.S)
    try: return json.loads(m.group(0)) if m else {}
    except ValueError: return {}


def understand(call=None, now=None):
    """Read her notes not yet considered and write what they say about her into GLORIA-MODEL.md.
    Returns (written, refused) lists. A failed author marks nothing considered."""
    state = _load(PROPOSALS, {"considered": [], "proposals": []})
    known = _load(APPROVED, [])
    # lines that sat waiting for a second yes before 16 October: her rating was the yes
    waiting = [p for p in state.get("proposals", []) if p.get("status") == "pending"]
    for p in waiting:
        p["status"] = "understood"
        known.append({"id": p["id"], "text": p["text"], "from": p.get("from", []), "at": str(p.get("at", ""))[:10]})
    seen = set(state.get("considered", []))
    fresh = [n for n in landings.notes() if n.get("id") and n["id"] not in seen]
    if not fresh:
        if waiting:
            _save(PROPOSALS, state); _save(APPROVED, known); render()
        return [dict(w, status="understood") for w in waiting], []
    prompt = ("WHAT YOU ALREADY UNDERSTAND FROM HER NOTES (do not repeat it; restate a line only where a new note "
              "changes it):\n%s\n\nHER NOTES:\n\n%s\n\n"
              'ONLY JSON: {"understandings": [{"text": "one line, first person, about her", "from": ["L-..."]}]}'
              % ("\n".join("- " + a["text"] for a in known) or "(nothing yet)", _evidence(fresh)))
    out = _json_in(_ask(prompt, call=call)).get("understandings")
    if not isinstance(out, list): raise RuntimeError("the author returned no understandings; nothing was marked considered")
    ids = {n["id"] for n in fresh}
    stamp = datetime.fromtimestamp(now or time.time()).isoformat(timespec="seconds")
    written, bad = [], []
    for u in out:
        if not isinstance(u, dict): continue
        text = str(u.get("text", "")).strip()
        src = [i for i in (u.get("from") or []) if i in ids]
        why = refused(text, [n for n in fresh if n["id"] in src] or fresh) or ("" if src else "it names no note")
        row = {"id": "U-" + uuid.uuid4().hex[:6], "text": text, "from": src, "at": stamp}
        (bad.append(dict(row, refused=why)) if why else written.append(row))
    known += [{"id": r["id"], "text": r["text"], "from": r["from"], "at": stamp[:10]} for r in written]
    state["refused"] = (state.get("refused", []) + bad)[-200:]
    state["considered"] = sorted(seen | ids)
    _save(PROPOSALS, state)
    _save(APPROVED, known)
    if written or waiting:
        render()
    return [dict(w, status="understood") for w in waiting] + written, bad


def block(approved=None):
    approved = _load(APPROVED, []) if approved is None else approved
    lines = [START, "## What reaches her — understood from how my work has reached her", ""]
    lines += ["- %s" % a["text"] for a in approved]
    return "\n".join(lines + [END])


def render(path=None):
    """Write the approved block into GLORIA-MODEL.md: replaced where it stands, or added at the end."""
    path = path or MODEL_FILE
    try: text = open(path, encoding="utf-8").read()
    except OSError: text = ""
    new = block()
    if START in text and END in text:
        text = text[:text.index(START)] + new + text[text.index(END) + len(END):]
    else:
        text = text.rstrip() + ("\n\n" if text.strip() else "") + new + "\n"
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f: f.write(text)
    os.replace(tmp, path)


def main(argv):
    cmd = argv[0] if argv else "show"
    if cmd in ("understand", "propose"):
        try:
            written, bad = understand()
        except Exception as exc:
            print("landings: nothing written: %s" % exc); return 1
        if not written and not bad: print("landings: no new notes since the last pass")
        for p in written: print("%s  %s\n          from %s" % (p["id"], p["text"], ", ".join(p["from"])))
        for b in bad: print("refused (%s): %s" % (b["refused"], b["text"][:160]))
        return 0
    if cmd == "show":
        rows = _load(APPROVED, [])
        if not rows: print("landings: nothing understood yet")
        for p in rows: print("%s  %s" % (p["id"], p["text"]))
        return 0
    print(__doc__); return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
