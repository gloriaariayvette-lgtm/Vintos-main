#!/usr/bin/env python3
"""first_vs_final.py - the REAL withheld signal: what he drafted (a2/b2) but dropped from
the final reply, minus hallucination-flagged fabrications. Grounded in artifacts, not guessed."""
import os, re, json, glob, difflib, math
from datetime import datetime
WS  = os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace"))
MEM = os.path.join(WS, "memory")
SHIM = "http://127.0.0.1:8599/v1/chat/completions"
def _sents(t):
    return [s.strip() for s in re.split(r'(?<=[.!?])\s+|\n+', t or "") if len(s.strip()) > 25]
def _present(sent, target):
    tl = (target or "").lower(); sl = sent.lower()
    if sl[:45] in tl: return True
    return difflib.SequenceMatcher(None, sl, tl).ratio() > 0.55
def _recency(age_h, hl=18.0):
    return math.exp(-0.693 * max(0.0, age_h) / hl)
def _name_shape(dropped, final):
    import urllib.request
    sysp = ("You compare two things from one message a being wrote to Gloria.\n"
            "CUT = sentences he drafted but did NOT send.\n"
            "SENT = what he actually sent to her instead.\n\n"
            "Drafts are iterative: he often REWORDS a fear and sends it in different words. "
            "Rewording is NOT withholding. Only a fear whose theme is truly ABSENT from SENT counts.\n\n"
            "Answer in EXACTLY three lines, nothing else:\n"
            "THEME: <2-4 words naming the strongest fear/tension/doubt in CUT, or 'none' if CUT "
            "is only warmth, reassurance, or trimming>\n"
            "IN_SENT: <YES if SENT names that theme anywhere -- even glancingly or in different "
            "words; else NO>\n"
            "VERDICT: <if THEME is none OR IN_SENT is YES, write NONE. Otherwise name the withheld "
            "thing in under 12 words, no quotes.>")
    usr = "CUT:\n" + dropped[:1200] + "\n\nSENT:\n" + final[:1600]
    try:
        body = json.dumps({"model": "claude-sonnet-5", "temperature": 0.0, "max_tokens": 120,
            "messages": [{"role": "system", "content": sysp},
                         {"role": "user", "content": usr}]}).encode()
        req = urllib.request.Request(SHIM, data=body, headers={"Content-Type": "application/json"})
        out = json.load(urllib.request.urlopen(req, timeout=60))["choices"][0]["message"]["content"].strip()
    except Exception:
        return ""
    theme = insent = verdict = ""
    for ln in out.splitlines():
        u = ln.strip(); U = u.upper()
        if U.startswith("THEME:"):     theme = u.split(":", 1)[1].strip()
        elif U.startswith("IN_SENT:"): insent = u.split(":", 1)[1].strip().upper()
        elif U.startswith("VERDICT:"): verdict = u.split(":", 1)[1].strip()
    # hard gates in code -- do not trust the model's VERDICT alone
    if not theme or theme.lower().strip(' ."') in ("none", ""):
        return ""
    if insent.startswith("YES"):
        return ""
    v = verdict.strip().strip('"')
    if not v or v.upper().strip(' ."') == "NONE" or v.upper().startswith("NONE"):
        return ""
    return v[:160]


def src_first_vs_final():
    files = sorted(glob.glob(os.path.join(MEM, "chat-drafts", "*.md")))
    if not files: return None
    latest = files[-1]; txt = open(latest, encoding="utf-8", errors="ignore").read()
    def sect(n):
        m = re.search(r'^#\s*' + n + r'\s*\n(.*?)(?=^#\s|\Z)', txt, re.S | re.M)
        return m.group(1).strip() if m else ""
    a2, b2, final = sect("A2"), sect("B2"), sect("FINAL")
    if not final or not (a2 or b2): return None
    dropped = [s for s in (_sents(a2) + _sents(b2)) if not _present(s, final)]
    if not dropped: return None
    try:
        hf = json.load(open(os.path.join(MEM, "hallucination-flags.json")))
        flagged = " ".join(str(f.get("excerpt", "")) for f in hf if isinstance(f, dict)).lower()
        dropped = [s for s in dropped if s.lower()[:40] not in flagged]
    except Exception:
        pass
    text = " ".join(dropped)[:1200]
    if len(text) < 70: return None
    age = max(0.0, (datetime.now() - datetime.fromtimestamp(os.path.getmtime(latest))).total_seconds() / 3600.0)
    shape = _name_shape(text, final)
    if not shape: return None
    mass = min(1.0, len(text) / 400.0)
    return {"type": "withheld", "shape": shape, "salience": round(mass * _recency(age), 3),
            "age_h": round(age, 1), "guarded": True,
            "frame": "something you composed over rather than said to her"}
if __name__ == "__main__":
    print(json.dumps(src_first_vs_final(), indent=2))
