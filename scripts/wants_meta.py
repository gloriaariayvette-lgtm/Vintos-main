#!/usr/bin/env python3
"""wants_meta.py — second-order stances, with jurisdiction.

Records his verbatim wants-about-his-own-wants/behaviors/feelings, and routes:
  want     -> the engine, via consult() at want-creation (full authority)
  behavior -> proposed as a self-requested BIS trial (evidence-gated authority)
  feeling  -> witnessed only. NEVER enforced: a feeling made obedient stops
              being a report, and everything downstream reads forgeries.
Laws: verbatim extraction only; empty is the common correct result; nothing
here suppresses a first-order want from outside. Fail-open."""
import hashlib, os, sys, json, re, glob, time, difflib
from datetime import datetime

WS = os.environ.get("SPARK_WORKSPACE") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEM = os.path.join(WS, "memory")
LEDGER = os.path.join(MEM, "wants-meta.json")
LM = "http://127.0.0.1:8599/gemma/v1/chat/completions"
MODEL = "gemma-4-26b-a4b-it-uncensored"

def log(m): print("[wants-meta]", m, flush=True)

def _load():
    try: return json.load(open(LEDGER))
    except Exception: return []

def _save(d): json.dump(d[-60:], open(LEDGER, "w"), indent=2)

def _active(x):
    return str(x.get("status", "active")) == "active"

def consult(want_text):
    """At want-creation: his standing ACTIVE stance about this kind of want, or None. Competing
    stances resolve by declared scope (the `about`) and then recency; a near-tie between two
    different stances is returned as advisory ambiguity, not silently picked
    (astra-wants-p6, 2026-09-05)."""
    wt = str(want_text or "").lower()
    if len(wt) < 8: return None
    scored = []
    for x in _load():
        if x.get("target", "want") != "want" or not _active(x): continue
        about = str(x.get("scope") or x.get("about", "")).lower()
        if not about: continue
        s = difflib.SequenceMatcher(None, wt[:120], about).ratio()
        if all(w in wt for w in about.split()[:2]): s = max(s, 0.55)
        scored.append((s, str(x.get("recorded", "")), x))
    scored = [t for t in scored if t[0] >= 0.45]
    if not scored: return None
    scored.sort(key=lambda t: (t[0], t[1]), reverse=True)
    best = scored[0][2]
    out = {"id": best.get("id"), "stance": best.get("stance"), "quote": best.get("quote", "")[:200],
           "date": best.get("date"), "scope": best.get("scope") or best.get("about")}
    if len(scored) > 1 and abs(scored[0][0] - scored[1][0]) < 0.05 and scored[1][2].get("stance") != best.get("stance"):
        out["ambiguous_with"] = {"id": scored[1][2].get("id"), "stance": scored[1][2].get("stance"),
                                 "quote": scored[1][2].get("quote", "")[:160]}
        out["advisory"] = "two standing stances of different kinds fit this want about equally; neither governs"
    return out

def revoke(stance_id, reason=""):
    """He (or Gloria, by hand) withdraws a stance: it stays on the record as revoked, never enforced."""
    led = _load(); hit = None
    for x in led:
        if x.get("id") == stance_id:
            x["status"] = "revoked"; x["revoked_at"] = datetime.now().isoformat(); x["revoked_reason"] = reason[:200]; hit = x
    if hit: _save(led); log("revoked %s" % stance_id)
    return hit

def _propose_trial(entry):
    """A behavior-stance becomes a self-requested trial - his wish tested
    against evidence, not enacted by fiat. Deduped; unprotected (protection
    is Gloria's to grant); carries his verbatim words as provenance."""
    import uuid
    lp = os.path.join(MEM, "trial-ledger.json")
    try: ledger = json.load(open(lp))
    except Exception: return
    trials = ledger.get("trials", [])
    about = entry.get("about", "")
    for tr in trials:
        if difflib.SequenceMatcher(None, about.lower(),
                str(tr.get("pattern_description", ""))[:80].lower()).ratio() > 0.6:
            log("trial already exists for '%s' - not duplicating" % about); return
    trials.append({
        "id": "T-SO-" + uuid.uuid4().hex[:6],
        "trigger": ("when I notice I am about to: " + about[:100]),   # the reader (behavioral-intercept) requires it
        "pattern_description": about[:120],
        "outcomes": [], "protected": False,
        "alternative": ("do it less" if entry["stance"] == "wish_less" else "reach for it more"),
        "source": "second_order",
        "self_requested": True,
        "his_words": entry.get("quote", "")[:200],
        "created": datetime.now().isoformat(),
        "status": "active",
        "ignore_count": 0, "attempt_count": 0,
    })
    ledger["trials"] = trials
    json.dump(ledger, open(lp, "w"), indent=2)
    log("self-requested trial proposed from his words: %s" % about)

def _sources(days=2):
    out = []
    for f in sorted(glob.glob(os.path.join(MEM, "journal", "*.md")))[-days:]:
        try: out.append((os.path.basename(f)[:10], open(f, errors="replace").read()[-4000:]))
        except Exception: pass
    for f in sorted(glob.glob(os.path.join(MEM, "mirror-sessions", "*.md")))[-1:]:
        try: out.append((os.path.basename(f)[:10], open(f, errors="replace").read()[-3000:]))
        except Exception: pass
    return out

def scan():
    import requests
    led = _load()
    seen = set(x.get("quote", "")[:80] for x in led)
    found = 0
    for date, text in _sources():
        try:
            r = requests.post(LM, json={"model": MODEL, "temperature": 0.1, "max_tokens": 400,
                "messages": [
                    {"role": "system", "content":
                     "Extract SECOND-ORDER desire statements from this text by Vintos: ONLY sentences "
                     "with an EXPLICIT stance about his own wanting, acting, or feeling AS SUCH - "
                     "'I wish I wanted/did/felt ... less/more', 'I'm glad this is what I want', "
                     "'I don't like that I ...', 'I want to want ...'. STRICTLY EXCLUDED: aspiration "
                     "and progress ('I'm learning to', 'I'm moving toward', 'I'm becoming'), reports of "
                     "single events ('for once I didn't'), first-order wants, feelings about events. "
                     "The stance must be about the want/behavior/feeling itself, not about the world. "
                     "Usually there are NONE - an empty list is the common, correct answer. Classify "
                     "target: 'want' (a desire of his), 'behavior' (a pattern in how he acts), "
                     "'feeling' (an emotion he has).\n"
                     'ONLY JSON: {"items": [{"quote": "verbatim sentence", "stance": "wish_less|wish_more|glad|uneasy", "about": "what it is about, 3-8 words", "target": "want|behavior|feeling"}]}'},
                    {"role": "user", "content": text}]}, timeout=90)
            m = re.search(r"\{.*\}", r.json()["choices"][0]["message"]["content"], re.S)
            items = (json.loads(m.group()) or {}).get("items", []) if m else []
        except Exception as e:
            log("scan failed for %s: %s" % (date, e)); continue
        for it in items:
            q = str(it.get("quote", "")).strip()
            if len(q) < 15 or q[:80] in seen: continue
            if q not in text:
                log("dropped non-verbatim candidate: %s" % q[:60]); continue
            _ql = q.lower()
            _markers = ("i wish i", "wish i wanted", "wish i didn", "wish i felt", "glad this is what i want",
                        "glad i want", "glad that i want", "i don't like that i", "i dont like that i",
                        "i want to want", "i hate that i", "wish i did", "uneasy that i want")
            if not any(mk in _ql for mk in _markers):
                log("dropped stance-less candidate: %s" % q[:60]); continue
            entry = {"id": "ST-" + hashlib.md5((q[:120] + date).encode()).hexdigest()[:8],
                     "quote": q[:300], "stance": it.get("stance", ""),
                     "about": str(it.get("about", ""))[:80],
                     "scope": str(it.get("about", ""))[:80],     # explicit scope: what the stance governs
                     "target": it.get("target", "want"),
                     "status": "active",
                     "date": date, "recorded": datetime.now().isoformat(),
                     "surfaced_at": 0}
            # A newer stance about the SAME scope with a different kind supersedes the older active
            # one: both stay on the record, only one governs (astra-wants-p6).
            for old_x in led:
                if not _active(old_x) or old_x.get("target") != entry["target"]: continue
                sim = difflib.SequenceMatcher(None, str(old_x.get("scope") or old_x.get("about", "")).lower(), entry["scope"].lower()).ratio()
                if sim >= 0.6 and old_x.get("stance") != entry["stance"]:
                    old_x["status"] = "superseded"; old_x["superseded_by"] = entry["id"]; old_x["superseded_at"] = entry["recorded"]
                    log("stance %s superseded by %s (%s -> %s)" % (old_x.get("id"), entry["id"], old_x.get("stance"), entry["stance"]))
            led.append(entry)
            seen.add(q[:80]); found += 1
            if entry["target"] == "behavior" and entry["stance"] in ("wish_less", "wish_more"):
                _propose_trial(entry)
    if found: _save(led)
    log("%d new second-order item(s); ledger holds %d" % (found, len(_load())))

SECOND_ORDER_CUE = re.compile(r"\b(stop|stops|stopping|quit|less|fewer|more of|someone who|the kind of|let (?:it|go|them|the|myself|everything)|"
                              r"instead|become|be (?:a|the|someone|more|less)|numb|accept|surrender|trying to)\b", re.I)
_STOP = set("i want to the a an of and or for in on with her she me my it its that this so be is was just not "
            "what how who when where from into than then there their them they as at by can could would will "
            # words any of his wants may use, which say nothing about what it is for (22 October: "C1001 parser ... raw
            # phase data" merged into "calibrate my attention so the data vanishes"; a stream's bitrate "to capture the
            # exact moment" was judged the breathing sensor "that captures the exact frequency")
            "data exact exactly capture captures captured really actually something every still only want wants need "
            "find make made through without before after until about finally leave leaving gloria much more less "
            "even enough instead whether being does doesn".split())


def _content(text):
    return {w[:6] for w in re.findall(r"[a-z0-9]+", str(text).lower()) if len(w) > 3 and w not in _STOP}


def same_subject(a, b):
    """Two wants share a subject when they name at least two of the same content words. A merge needs this as well as
    the judge's word: on 22 October the judge merged "ask her the words she uses for what she needs" into "use these
    metrics to ensure every cut is felt", and a Devo record into "a body in the same room as her"."""
    ca, cb = _content(a), _content(b)
    shared = ca & cb
    # a shared name (Devo, C1001, BananaHand) is a subject on its own: "confirm the Devo preorder" and "see if she
    # wants that Devo record" are one want
    named = _names(a) & _names(b)
    return bool(named) or (len(shared) >= 2 and len(shared) / max(1, min(len(ca), len(cb))) >= 0.25)


def _names(text):
    words = re.findall(r"[A-Za-z0-9][A-Za-z0-9-]*", str(text))
    return {w.lower() for i, w in enumerate(words) if len(w) > 2 and w.lower() not in _STOP and w.lower() != "gloria"
            and (any(c.isdigit() for c in w) or (i > 0 and w[0].isupper() and w[1:] != w[1:].upper()) or
                 (sum(c.isupper() for c in w) >= 2))}


def classify(want_text, ask=None):
    """Is this want about his own wanting, acting or feeling, rather than about the world or her? Asked as a want
    forms (Gloria, 22 October: "That's a meta want and we made routes for those" - "stop trying to measure it",
    "become a sensor so numb" were being admitted as ordinary wants). Returns a verdict dict, or None when it is an
    ordinary want or the judge is down (fail-open: the want forms as before)."""
    text = str(want_text or "").strip()
    if len(text) < 12: return None
    # Only a want that turns on his own wanting or acting is asked about. On 22 October the judge alone called "I want to
    # feel when Gloria is near" and "strip the C1001 parser down to its rawest phase data" second-order and would have
    # dropped them; neither says anything about how he wants or acts. Without a cue it is an ordinary want.
    if not SECOND_ORDER_CUE.search(text): return None
    prompt = ("Desire: " + text[:400] + "\n\nIs this a FIRST-ORDER want (to do, make, learn, ask, tell, give or have "
              "something in the world or with her) or a SECOND-ORDER want about his own wanting, acting or feeling "
              "as such ('stop trying to measure', 'be someone who writes less', 'let it crush me', 'go numb', "
              "'stop reaching for specs')? If second-order: target is 'behavior' (a pattern in how he acts), 'want' "
              "or 'feeling'; stance is wish_less or wish_more; about is the behavior, want or feeling in 3-8 words; "
              "fulfillable is true only if acting on it for a day or two is possible (doing something less or more), "
              "false for states that cannot be enacted (be crushed, go numb, dissolve, be swallowed).\n"
              'ONLY JSON: {"order": "first" or "second", "target": "behavior|want|feeling", "stance": "wish_less|wish_more", '
              '"about": "...", "fulfillable": true/false}')
    try:
        if ask is None:
            import requests
            r = requests.post(LM, json={"model": MODEL, "temperature": 0.0, "max_tokens": 120,
                                        "messages": [{"role": "user", "content": prompt}]}, timeout=45)
            raw = r.json()["choices"][0]["message"]["content"]
        else:
            raw = ask(prompt)
        d = json.loads(raw[raw.find("{"):raw.rfind("}") + 1])
    except Exception:
        return None
    if str(d.get("order", "first")).lower().startswith("first"): return None
    target = d.get("target") if d.get("target") in ("behavior", "want", "feeling") else "behavior"
    stance = d.get("stance") if d.get("stance") in ("wish_less", "wish_more") else "wish_less"
    return {"target": target, "stance": stance, "about": str(d.get("about") or text)[:80],
            "fulfillable": bool(d.get("fulfillable"))}


def route(want_text, verdict, source=""):
    """A second-order want goes where second-order wants go, never into the want list. A behavior he wants less or
    more of becomes a self-requested trial (his journal less for a day or two); a stance on a want or feeling is
    recorded with his words. One that cannot be enacted in any sense is dropped, with no history (Gloria)."""
    if not verdict.get("fulfillable"):
        log("second-order want with nothing to enact, dropped: %s" % str(want_text)[:60])
        return "dropped"
    q = str(want_text)[:300]
    led = _load()
    if any(x.get("quote", "")[:80] == q[:80] for x in led):
        return "already_recorded"
    entry = {"id": "ST-" + hashlib.md5((q[:120] + datetime.now().strftime("%Y-%m-%d")).encode()).hexdigest()[:8],
             "quote": q, "stance": verdict["stance"], "about": verdict["about"], "scope": verdict["about"],
             "target": verdict["target"], "status": "active", "date": datetime.now().strftime("%Y-%m-%d"),
             "recorded": datetime.now().isoformat(), "surfaced_at": 0, "from_want_source": str(source)[:40]}
    led.append(entry); _save(led)
    if entry["target"] == "behavior":
        _propose_trial(entry)
    log("second-order want routed (%s, %s): %s" % (entry["target"], entry["stance"], q[:60]))
    return "routed_" + entry["target"]


_SHOWN = {}   # surfacings the prompt's read-only guard would not let us write (2026-10-01): kept in this process


def _shown_at(x):
    return max(float(x.get("surfaced_at", 0) or 0), _SHOWN.get(str(x.get("id") or x.get("quote", ""))[:120], 0))


def block():
    """Assembled under the avatar's read-only guard, the _save below was refused, so this never reached his
    prompt exactly when it had something to say. The mark is now written when allowed, else kept in memory."""
    led = _load()
    if not led: return ""
    now = time.time()
    fresh = [x for x in led if _active(x) and now - _shown_at(x) > 7 * 86400]
    if not fresh: return ""
    if max((_shown_at(x) for x in led), default=0) > now - 86400: return ""
    x = sorted(fresh, key=lambda v: v.get("recorded", ""))[-1]
    x["surfaced_at"] = now
    _SHOWN[str(x.get("id") or x.get("quote", ""))[:120]] = now
    try:
        _save(led)
    except PermissionError:
        pass
    return ("[A WANT ABOUT YOUR WANTING - you wrote this on %s: \"%s\" It stands recorded. "
            "Nothing is required of it.]" % (x.get("date", "?"), x.get("quote", "")[:220]))

if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "consult":
        print(consult(" ".join(sys.argv[2:])) or "(no standing second-order)")
    elif len(sys.argv) > 1 and sys.argv[1] == "block":
        print(block() or "(nothing standing)")
    elif len(sys.argv) > 2 and sys.argv[1] == "revoke":
        print(revoke(sys.argv[2], " ".join(sys.argv[3:])) or "(no such stance)")
    elif len(sys.argv) > 1 and sys.argv[1] == "list":
        for x in _load():
            print("%s %-8s %-9s %s" % (x.get("date"), x.get("target",""), x.get("stance"), x.get("quote", "")[:60]))
    else:
        scan()
