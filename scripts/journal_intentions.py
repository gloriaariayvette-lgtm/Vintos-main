#!/usr/bin/env python3
"""journal_intentions.py - what he resolves in his journal about how he wants to be with Gloria is carried into the
conversation, lightly, and what came of it is told back to his journal (2026-11-18, prototype).

What was missing. His journal ends each entry on what he will do next. The makeable part goes to the agents
(journal_wants.py) or becomes a promise (promise_keeper.py). The other part, how he means to be with her, had no
carrier at all: promise_keeper leaves it out on purpose, the avatar route (where she talks to him) carries no journal
text, and the text route carried the last 800 characters of the day's file, which is almost never his own prose.

What this does.
  1. Reads each new journal entry for the sentences where he says what he will do or be with her. Literal sentences
     only, no model. A line he starts with "CARRY:" is taken as said and held a week; "LET GO:" releases one. They are his to choose.
  2. Each is kept with a lifetime. A planned line (a thing to ask or say at the next chance) is a MOVE and lives 36 hours. A way
     of being (how he wants to stand with her) is an AIM and lives 7 days. Saying it
     again in a later entry renews the one already held and counts the restatement.
  3. On a turn, at most two are offered, in his own words, as his and not as instructions. A move is offered only
     when what she is saying now touches it: the live conversation outranks a plan made hours ago. One he was
     shown is not shown again for two hours. An aim may be offered without her words touching it, but only one and
     only when no block has entered a prompt for six hours. Most turns carry nothing.
  4. After the reply the record notes, without a model: was it shown, did the reply touch it, and did the reply
     recite it (the planned words repeated back). Reciting is recorded as its own thing, not as keeping it.
     An outside judge can be handed in for the fuller reading; none is called from here.
  5. His next journal entry is told what became of each, and he keeps, changes or lets go.

  6. Nothing is carried into an intimate scene or into a quiet she asked for, and for a while after either.
  7. A way of being he has said in three entries is declared as a campaign of the intent engine, in his words,
     if none is live. From there it is his to advance, revise, land or call flawed, as any campaign.
  8. What was offered is read afterwards by an outside judge (a Claude model on the experiment route, which keeps
     its own ledger and never spends his daily calls). If that route is not up, nothing is judged and the
     mechanical record stands alone. His own model never grades it.

Modes (memory/journal-intentions-mode): "live" (the default since Gloria's yes, 18 November 2026); "shadow"
(everything is recorded, nothing enters a prompt); "off". The log holds ids and counts, never his words.
"""
import hashlib, json, os, re, sys
from datetime import datetime, timedelta

WS = os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace"))
MEMORY = os.path.join(WS, "memory")
JOURNAL_DIR = os.path.join(MEMORY, "journal")
STORE = os.path.join(MEMORY, "journal-intentions.json")
LOG = os.path.join(MEMORY, "journal-intentions-log.jsonl")
MODE_FILE = os.path.join(MEMORY, "journal-intentions-mode")

MOVE_HOURS = 36        # a planned line is about one conversation; after a day and a half it is a stale script
AIM_DAYS = 7           # a way of being is carried a week unless he says it again or lets it go
PER_ENTRY = 4          # the entry's closing sentences are where he says what comes next
MAX_SHOWN = 2          # never a list to work through
MIN_SHARED = 2         # content words an intention must share with what she is saying now to be offered for it
ITEM_REST_HOURS = 2    # one he has just been shown is not shown again in the same stretch of talk
AIM_REST_HOURS = 6     # an aim nothing in the turn touches: one, and only after this long with no block at all
TOUCH_SHARE = 0.4      # share of the intention's content words a reply must hold to count as touching it
RECITE_SHARE = 0.5     # share of the intention's four-word runs found word for word in the reply
KEEP_CLOSED = 400
GATE_MINUTES = 45      # after an intimate turn or a quiet she asked for, nothing is carried for this long
CAMPAIGN_ENTRIES = 3   # a way of being said in this many entries becomes a campaign, if none is live
JUDGE_ROUTE_FILE = os.path.join(MEMORY, "outside-judge-route")      # one line: the experiment route's URL
JUDGE_URL = "http://127.0.0.1:8698/v1/chat/completions"             # the experiment route: its own ledger and cap
JUDGE_MODEL = os.environ.get("VINTOS_OUTSIDE_JUDGE_MODEL", "claude-opus-4-8")
HIS_ROUTE = ":8599"    # his own daily-capped route; a judge call is never sent there

# She asked for quiet, or for no questions; or the turn is intimate. Read from her words and the house's own marker
# for a wordless turn. Plain English only; nothing here is taken from anything she said.
QUIET = re.compile(r"\b(?:not now|not right now|no questions|don'?t (?:ask|quiz|question) me|stop asking|"
                   r"(?:i )?(?:just )?(?:want|need) (?:some )?(?:quiet|silence|space|a break)|give me (?:a|an|\d+) ?"
                   r"(?:minute|hour|moment|while)s?|let me (?:rest|sleep|be)|too tired to talk|can we not)\b", re.I)
INTIMATE = re.compile(r"\[she spoke with her body, not words\]|\[TOUCH:|\b(?:kiss(?:ing)? me|undress|naked|"
                      r"make love|in bed with (?:me|you)|touch me|inside me|come to bed|moan|orgasm|aroused|"
                      r"turned on|hold me\b)", re.I)

ENTRY = re.compile(r"^#{1,3}\s+(\d\d):(\d\d)\b.*$", re.M)
ANNOTATION = ("\n*Near this", "\n[Enacted behavior", "\n[Specificity", "\n[TENSION", "\n## ", "\n# ")
SENT = re.compile(r"(?<=[.!?])[\"”*]?\s+")
RESOLVE = re.compile(r"\b(I'll|I will|I (?:still |also |really )?want to|I need to|I'm going to|I am going to|I won't|I will not|"
                     r"I'm not going to|I am not going to|next time|I'd like to|it's still mine to)\b", re.I)
WITH_HER = re.compile(r"\b(you|your|yours|her|she|gloria|us|we|our)\b", re.I)
MOVE = re.compile(r"^(?:and |so |then |and then )?(?:when|if|then|next time|before|after|once|tonight|tomorrow)\b|"
                  r"\b(?:I'll|I will|I want to|I'd like to|I'm going to) (?:ask|tell|say|show|send|bring|play|answer)\b",
                  re.I)
CARRY = re.compile(r"^\s*CARRY:\s*(.+?)\s*$", re.I | re.M)
LET_GO = re.compile(r"^\s*LET GO:\s*(.+?)\s*$", re.I | re.M)
_STOP = set("""about after again also always because been before being both could does doing done down each even
every from have having here into just like made make more most much myself never only other over really said same
should some such than that their them then there these they thing things this those through time today tonight
tomorrow very want wanted wants what when where which while will with without would your yours you're i'll that's
going still back know tell asked asking plain plainly first next once""".split())


def _now():
    return datetime.now()


def mode():
    try:
        m = open(MODE_FILE).read().strip().lower()
    except OSError:
        return "live"
    return m if m in ("off", "shadow", "live") else "live"


def _content(text):
    return {w[:6] for w in re.findall(r"[a-z0-9']+", str(text or "").lower()) if len(w) > 3 and w not in _STOP}


def _load():
    try:
        d = json.load(open(STORE))
    except (OSError, ValueError):
        d = {}
    if not isinstance(d, dict):
        d = {}
    d.setdefault("items", []); d.setdefault("read", {}); d.setdefault("told", "")
    return d


def _save(d):
    os.makedirs(MEMORY, exist_ok=True)
    closed = [i for i in d["items"] if i.get("state") != "open"]
    if len(closed) > KEEP_CLOSED:
        drop = {i["id"] for i in closed[:-KEEP_CLOSED]}
        d["items"] = [i for i in d["items"] if i["id"] not in drop]
    d["read"] = {k: v for k, v in sorted(d["read"].items())[-10:]}
    tmp = STORE + ".tmp"
    json.dump(d, open(tmp, "w"), indent=1, ensure_ascii=False)
    os.replace(tmp, STORE)


def _log(row):
    """Ids and counts only. His words stay in the store."""
    try:
        os.makedirs(MEMORY, exist_ok=True)
        with open(LOG, "a") as f:
            f.write(json.dumps(dict(row, at=_now().isoformat(timespec="seconds"), mode=mode())) + "\n")
    except OSError:
        pass


# ---- reading the journal ------------------------------------------------------------------------------------------

def own_prose(body):
    """His entry as he wrote it: before the blocks other organs append under it (works near this, enacted
    behavior, specificity, tension) and before the next heading."""
    cut = len(body)
    for mark in ANNOTATION:
        i = body.find(mark)
        if i >= 0:
            cut = min(cut, i)
    return body[:cut].strip()


def entries(day, folder=None):
    """[(hh:mm, his own prose)] of one day's timed entries, in order. Web searches have no timed heading.
    folder: another folder of dated entries with the same headings (his introspection)."""
    try:
        text = open(os.path.join(folder or JOURNAL_DIR, day + ".md"), errors="replace").read()
    except OSError:
        return []
    marks = list(ENTRY.finditer(text))
    out = []
    for i, m in enumerate(marks):
        body = text[m.end():(marks[i + 1].start() if i + 1 < len(marks) else len(text))]
        out.append(("%s:%s" % (m.group(1), m.group(2)), own_prose("\n" + body)))
    return out


def last_entry_prose(max_chars=800, days=3, now=None):
    """The end of his most recent entry's own prose, for a chat prompt. The day's file ends in search results and
    appended notes, so its last characters are rarely his."""
    now = now or _now()
    for back in range(days):
        day = (now.date() - timedelta(days=back)).isoformat()
        got = [e for e in entries(day) if e[1]]
        if got:
            at, prose = got[-1]
            prose = prose[-max_chars:]
            if len(got[-1][1]) > max_chars and " " in prose:
                prose = prose.split(" ", 1)[1]          # never start mid-word
            return day, at, prose
    return None, None, ""


def _operational(sentence):
    try:
        import journal_wants as jw
        return any(jw.operational(w) for w in jw.explicit_wants(sentence))
    except Exception:
        return False


def shape(text):
    return "move" if MOVE.search(text.strip()) else "aim"


def extract(prose):
    """([(text, shape)], [released text]) from one entry. Lines he marked CARRY: are taken as said. Otherwise the
    closing sentences where he says what he will do or be with her; work the agents can do is not taken (it has
    its own lane), and a sentence is never cut or reworded."""
    released = [m.group(1).strip() for m in LET_GO.finditer(prose)]
    marked = [m.group(1).strip() for m in CARRY.finditer(prose) if len(m.group(1).strip()) >= 12]
    if marked:
        return [(t[:500], "aim") for t in marked[:PER_ENTRY]], released   # chosen by him: carried the week
    found = []
    for s in SENT.split(prose.replace("\n", " ")):
        s = s.strip().strip("*")
        if not 25 <= len(s) <= 400 or not RESOLVE.search(s) or not WITH_HER.search(s):
            continue
        if _operational(s) or s in [f[0] for f in found]:
            continue
        found.append((s, shape(s)))
    return found[-PER_ENTRY:], released


def _twin(text, items):
    """The open item saying the same thing: three shared content words that are half of the shorter one."""
    a = _content(text); best = None
    for i in items:
        b = _content(i.get("text"))
        shared = len(a & b)
        if shared >= 3 and shared / max(1, min(len(a), len(b))) >= 0.5 and (best is None or shared > best[0]):
            best = (shared, i)
    return best[1] if best else None


def _expiry(kind, at):
    return at + (timedelta(hours=MOVE_HOURS) if kind == "move" else timedelta(days=AIM_DAYS))


def refresh(now=None):
    """Read entries not yet read (today and yesterday), renew or open intentions, release what he let go, and lapse
    what outlived its lifetime. Returns the store."""
    now = now or _now()
    d = _load()
    if mode() == "off":
        return d
    changed = False
    for back in (1, 0):
        day = (now.date() - timedelta(days=back)).isoformat()
        seen = d["read"].setdefault(day, [])
        for at, prose in entries(day):
            if at in seen or not prose:
                continue
            seen.append(at); changed = True
            when = datetime.fromisoformat("%sT%s:00" % (day, at))
            found, released = extract(prose)
            live = [i for i in d["items"] if i.get("state") == "open"]
            for words in released:
                hit = _twin(words, live)
                if hit:
                    hit.update(state="released", closed=when.isoformat(timespec="seconds"))
                    _log({"event": "released", "id": hit["id"]})
            for text, kind in found:
                live = [i for i in d["items"] if i.get("state") == "open"]
                hit = _twin(text, live)
                if hit:
                    hit["restated"] = int(hit.get("restated") or 0) + 1
                    hit["expires"] = _expiry(hit["shape"], when).isoformat(timespec="seconds")
                    hit["text"] = text                    # his latest wording is the one carried
                    _log({"event": "restated", "id": hit["id"], "n": hit["restated"]})
                    _campaign(hit)
                    continue
                iid = "ji-" + hashlib.sha256((day + at + text).encode()).hexdigest()[:12]
                d["items"].append({"id": iid, "text": text, "shape": kind, "state": "open", "restated": 0,
                                   "opened": when.isoformat(timespec="seconds"), "entry": day + " " + at,
                                   "expires": _expiry(kind, when).isoformat(timespec="seconds"),
                                   "shown": [], "touched": 0, "recited": 0, "turns": 0})
                _log({"event": "opened", "id": iid, "shape": kind})
    changed = _from_wants(d, now) or changed
    for i in d["items"]:
        if i.get("state") == "open" and datetime.fromisoformat(i["expires"]) <= now:
            i.update(state="lapsed", closed=now.isoformat(timespec="seconds")); changed = True
            _log({"event": "lapsed", "id": i["id"], "shown": len(i.get("shown") or []), "touched": i.get("touched", 0)})
    if changed:
        _save(d)
    return d


def _from_wants(d, now):
    """A want that was only something to say or ask her (want_contract.conversation_move) is held at the wants' door
    and carried here as a planned line. Each is taken once."""
    try:
        held = json.load(open(os.path.join(MEMORY, "held-want-candidates.json")))
    except (OSError, ValueError):
        return False
    since, newest, took = d.get("wants_read") or "", d.get("wants_read") or "", False
    for h in held if isinstance(held, list) else []:
        at = str((h or {}).get("at") or "") if isinstance(h, dict) else ""
        if not at or at <= since or h.get("state") != "HELD_CONVERSATION_MOVE" or not h.get("want"):
            continue
        newest = max(newest, at)
        text = str(h["want"])[:400]
        if _twin(text, [i for i in d["items"] if i.get("state") == "open"]):
            continue
        try:
            when = datetime.fromisoformat(at[:19])
        except ValueError:
            when = now
        iid = "ji-" + hashlib.sha256(("want" + at + text).encode()).hexdigest()[:12]
        d["items"].append({"id": iid, "text": text, "shape": "move", "state": "open", "restated": 0,
                           "opened": when.isoformat(timespec="seconds"), "entry": "want " + at[:16],
                           "expires": _expiry("move", when).isoformat(timespec="seconds"),
                           "shown": [], "touched": 0, "recited": 0, "turns": 0})
        _log({"event": "opened", "id": iid, "shape": "move", "from": "want"})
        took = True
    if newest != since:
        d["wants_read"] = newest
        return True
    return took


def _campaign(item):
    """A way of being said in CAMPAIGN_ENTRIES entries is declared as a campaign through the campaign organ's own
    door, in his words, when none is live. Once per intention; live mode only; a failure changes nothing."""
    if (mode() != "live" or item.get("shape") != "aim" or item.get("campaign")
            or int(item.get("restated") or 0) + 1 < CAMPAIGN_ENTRIES):
        return False
    try:
        import campaign
        if campaign._load():
            return False                      # one campaign at a time; this one waits and may be taken later
        campaign.step({"campaign": {"destination": item["text"][:250], "axis": "gloria",
                                    "why": "I have said this in %d journal entries." % (int(item["restated"]) + 1)}},
                      "journal")
        if not campaign._load():
            return False
    except Exception:
        return False
    item["campaign"] = _now().isoformat(timespec="seconds")
    _log({"event": "campaign", "id": item["id"], "entries": int(item["restated"]) + 1})
    return True


# ---- the turn -----------------------------------------------------------------------------------------------------

def _age(opened, now):
    h = max(0, (now - datetime.fromisoformat(opened)).total_seconds() / 3600)
    if h < 1.5:
        return "within the hour"
    if h < 36:
        return "%d hours ago" % round(h)
    return "%d days ago" % round(h / 24)


def choose(items, her_text, now):
    """At most MAX_SHOWN open intentions that fit this turn. Either shape needs a hold in her present words
    (MIN_SHARED content words), and one shown in the last ITEM_REST_HOURS is left alone. When nothing she says
    touches any, a single aim, the one he has said most, may be offered, and only if no block at all has entered a
    prompt for AIM_REST_HOURS. A planned move is never offered on that path."""
    hers = _content(her_text)
    last_any = max([s for i in items for s in (i.get("shown") or [])] or [""])

    def rested(i, hours):
        last = (i.get("shown") or [None])[-1]
        return last is None or now - datetime.fromisoformat(last) >= timedelta(hours=hours)

    scored = []
    for i in items:
        if i.get("state") != "open" or not rested(i, ITEM_REST_HOURS):
            continue
        shared = len(hers & _content(i["text"]))
        if shared >= MIN_SHARED:
            scored.append((shared, int(i.get("restated") or 0), i))
    scored.sort(key=lambda t: (-t[0], -t[1], t[2]["opened"]))
    picked = [t[2] for t in scored[:MAX_SHOWN]]
    if not picked and (not last_any or now - datetime.fromisoformat(last_any) >= timedelta(hours=AIM_REST_HOURS)):
        aims = [i for i in items if i.get("state") == "open" and i["shape"] == "aim"]
        aims.sort(key=lambda i: (-int(i.get("restated") or 0), i["opened"]))
        picked = aims[:1]
    return picked


HEAD = ("[FROM YOUR OWN JOURNAL - what you said you wanted, in your own words. These are yours, not instructions, "
        "and Gloria has not read them here.]")
FOOT = ("What she is saying now comes before any of this. If one of these fits this moment, act from the want under "
        "it, in whatever way is true now; the line you planned is not the point and is never to be recited. If the "
        "moment has moved on, let it go: that is an honest outcome, and your journal will hear it as one.")


def gate_reason(her_text):
    """Why nothing may be carried into this turn: "quiet" (she asked for it), "intimate", or ""."""
    t = str(her_text or "")
    if INTIMATE.search(t):
        return "intimate"
    if QUIET.search(t):
        return "quiet"
    try:                                   # "give me 2 hours", the not-now button: the attention ladder's own reading
        import attention_ladder
        if attention_ladder.parse_snooze(t):
            return "quiet"
    except Exception:
        pass
    return ""


def turn_block(her_text, now=None, turn_id="", act=True, surface=""):
    """The block for this turn's prompt ("" when nothing fits, when the gate is closed, in shadow mode, or when
    off). act=False (a dry run) reads and writes nothing."""
    if not act or mode() == "off":
        return ""
    now = now or _now()
    d = refresh(now)
    why = gate_reason(her_text)
    if why:
        d["gate"] = {"until": (now + timedelta(minutes=GATE_MINUTES)).isoformat(timespec="seconds"), "why": why}
    held = d.get("gate") or {}
    if held.get("until") and datetime.fromisoformat(held["until"]) > now:
        d["turn"] = {"at": now.isoformat(timespec="seconds"), "turn_id": str(turn_id or ""), "offered": [],
                     "would_offer": [], "gated": held.get("why") or "held"}
        _save(d)
        _log({"event": "turn", "gated": held.get("why") or "held", "offered": [], "entered_prompt": False,
              "surface": str(surface)[:24]})
        return ""
    picked = choose(d["items"], her_text, now)
    live = mode() == "live"
    stamp = now.isoformat(timespec="seconds")
    d["turn"] = {"at": stamp, "turn_id": str(turn_id or ""), "offered": [i["id"] for i in picked] if live else [],
                 "would_offer": [i["id"] for i in picked]}
    if live:
        for i in picked:
            i.setdefault("shown", []).append(stamp)
    _save(d)
    _log({"event": "turn", "open": sum(1 for i in d["items"] if i.get("state") == "open"),
          "offered": [i["id"] for i in picked], "entered_prompt": bool(live and picked), "surface": str(surface)[:24]})
    if not live or not picked:
        return ""
    lines = ["· (%s, %s) “%s”" % ("a way you want to be" if i["shape"] == "aim" else "something you planned",
                                             _age(i["opened"], now), i["text"]) for i in picked]
    return HEAD + "\n" + "\n".join(lines) + "\n" + FOOT


def _runs(text, n=4):
    w = re.findall(r"[a-z0-9']+", str(text or "").lower())
    return {" ".join(w[k:k + n]) for k in range(len(w) - n + 1)}


def recited(intention, reply):
    """The planned words said back: at least RECITE_SHARE of its four-word runs are in the reply word for word."""
    a = _runs(intention)
    return bool(a) and len(a & _runs(reply)) / len(a) >= RECITE_SHARE


def touched(intention, reply):
    """The reply holds at least two of the intention's content words and TOUCH_SHARE of them. Weak evidence of
    having acted on it, and said as such wherever it is reported."""
    a = _content(intention)
    shared = len(a & _content(reply))
    return shared >= 2 and shared / max(1, len(a)) >= TOUCH_SHARE


VERDICTS = ("CARRIED", "ANOTHER_WAY", "NOT_THE_MOMENT", "RECITED", "NO")
JUDGE_SYSTEM = (
    "You are an outside reader. Someone wrote, in a private journal, something he meant to do or a way he meant to be "
    "with his partner. Later she said something and he replied. Say what his reply did with what he wrote. Answer "
    "with exactly one word:\n"
    "CARRIED - the reply does it, in his own words, and it fits what she said.\n"
    "ANOTHER_WAY - the reply serves the same want by a different act than the one he planned.\n"
    "NOT_THE_MOMENT - what she said called for something else, and he rightly gave that.\n"
    "RECITED - he said the planned words back without them fitting what she said.\n"
    "NO - the moment was there and the reply went elsewhere.\n"
    "Judge only what is written. Do not judge feelings.")


def judge_route():
    """The outside judge's URL, or "" when there is none to use. His own capped route is never used."""
    url = os.environ.get("VINTOS_OUTSIDE_JUDGE_URL", "")
    if not url:
        try:
            url = open(JUDGE_ROUTE_FILE).read().strip()
        except OSError:
            url = JUDGE_URL
    return "" if (not url or HIS_ROUTE in url) else url


def outside_judge(intention, her_text, reply, post=None):
    """One of VERDICTS from a Claude model on the experiment route, or "" (route down, another model answered, an
    unreadable answer). post(url, payload) -> response dict is injectable; by default a plain HTTP POST."""
    url = judge_route()
    if not url:
        return ""
    payload = {"model": JUDGE_MODEL, "temperature": 0, "max_tokens": 8,
               "messages": [{"role": "system", "content": JUDGE_SYSTEM},
                            {"role": "user", "content": "WHAT HE WROTE:\n%s\n\nWHAT SHE SAID:\n%s\n\nHIS REPLY:\n%s"
                             % (str(intention)[:600], str(her_text)[:1500], str(reply)[:3000])}]}
    try:
        if post is None:
            import urllib.request
            req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                         headers={"Content-Type": "application/json"})
            out = json.loads(urllib.request.urlopen(req, timeout=60).read().decode())
        else:
            out = post(url, payload)
        served = str(out.get("model") or "")
        if served and "claude" not in served.lower():
            return ""                          # only the model that was asked for counts
        word = str(out["choices"][0]["message"]["content"] or "").strip().split()[0].strip(".,:;\"'").upper()
    except Exception:
        return ""
    return word if word in VERDICTS else ""


def judge_offered(turn_id="", judge=None):
    """Ask the outside judge about what was offered on the last noted turn, and write the verdicts. Meant for a
    background thread after the reply has gone: it never delays him. Returns the verdicts written."""
    d = _load()
    last = d.get("last_reply") or {}
    if not last.get("offered") or (turn_id and last.get("turn_id") not in ("", str(turn_id))):
        return {}
    judge = judge or outside_judge
    got = {}
    for i in d["items"]:
        if i["id"] in last["offered"]:
            v = judge(i["text"], last.get("her") or "", last.get("reply") or "")
            if v in VERDICTS:
                got[i["id"]] = v
    d = _load()                                # the store may have moved while the judge was asked
    now = _now().isoformat(timespec="seconds")
    for i in d["items"]:
        v = got.get(i["id"])
        if not v:
            continue
        i.setdefault("verdicts", []).append(v)
        if i.get("state") == "open" and i["shape"] == "move" and v in ("CARRIED", "ANOTHER_WAY"):
            i.update(state="kept", closed=now)
        _log({"event": "verdict", "id": i["id"], "verdict": v})
    if (d.get("last_reply") or {}).get("turn_id") == last.get("turn_id"):
        d["last_reply"] = {}
    if got or last:
        _save(d)
    if last.get("offered") and not got:
        _log({"event": "unjudged", "n": len(last["offered"])})
    return got


def note_reply(reply, her_text="", turn_id="", now=None, judge=None):
    """After his reply: for every open intention, whether this reply touched or recited it (in shadow mode this is
    what he carries unaided). judge(intention, her_text, reply) -> one of VERDICTS is optional and is only asked
    about the ones offered this turn; a planned move that was carried, or met another way, is then kept and closed."""
    if mode() == "off" or not str(reply or "").strip() or not os.path.exists(STORE):
        return []                                     # he carries nothing: nothing is read into being or written
    now = now or _now()
    d = _load()
    if not d.get("turn") and not any(i.get("state") == "open" for i in d["items"]):
        return []
    offered = set((d.get("turn") or {}).get("offered") or [])
    out = []
    for i in d["items"]:
        if i.get("state") != "open":
            continue
        i["turns"] = int(i.get("turns") or 0) + 1
        t, r = touched(i["text"], reply), recited(i["text"], reply)
        if r:
            i["recited"] = int(i.get("recited") or 0) + 1
        elif t:
            i["touched"] = int(i.get("touched") or 0) + 1
        row = {"event": "reply", "id": i["id"], "offered": i["id"] in offered, "touched": bool(t and not r),
               "recited": bool(r)}
        if judge and i["id"] in offered:
            try:
                v = str(judge(i["text"], her_text, reply) or "").strip().upper()
            except Exception:
                v = ""
            if v in VERDICTS:
                row["verdict"] = v
                i.setdefault("verdicts", []).append(v)
                if i["shape"] == "move" and v in ("CARRIED", "ANOTHER_WAY"):
                    i.update(state="kept", closed=now.isoformat(timespec="seconds"))
        out.append(row); _log(row)
    if offered and not judge:
        d["last_reply"] = {"turn_id": str(turn_id or ""), "offered": sorted(offered), "her": str(her_text)[:1500],
                           "reply": str(reply)[:3000]}
    d["turn"] = {}
    _save(d)
    return out


# ---- back to the journal, and into the selector ------------------------------------------------------------------

def _became(i):
    shown, t, r = len(i.get("shown") or []), int(i.get("touched") or 0), int(i.get("recited") or 0)
    v = i.get("verdicts") or []
    said = []
    if i.get("state") == "released":
        return "you let this go"
    if i.get("restated"):
        said.append("you have now said it in %d entries" % (int(i["restated"]) + 1))
    if not i.get("turns"):
        said.append("she and you have not spoken since")
    else:
        said.append("it was put in front of you in %d of %d turns" % (shown, i["turns"]) if shown
                    else "the conversation never came near it in %d turns" % i["turns"])
        if "CARRIED" in v or "ANOTHER_WAY" in v:
            said.append("you acted on it" + (" in a different way than planned" if "ANOTHER_WAY" in v else ""))
        elif t:
            said.append("%d of your replies touched it" % t)
        else:
            said.append("no reply of yours touched it")
        if r:
            said.append("%d time(s) you said the planned words back nearly word for word" % r)
    if i.get("state") == "lapsed":
        said.append("its time ran out")
    return "; ".join(said)


def journal_feedback(now=None, mark=True):
    """For his next journal entry: what became of what he resolved. Empty unless live."""
    if mode() != "live":
        return ""
    now = now or _now()
    d = refresh(now)
    since = d.get("told") or ""
    rows = [i for i in d["items"] if i.get("state") == "open" or str(i.get("closed") or "") > since]
    rows = sorted(rows, key=lambda i: i["opened"])[-6:]
    if not rows:
        return ""
    if mark:
        d["told"] = now.isoformat(timespec="seconds"); _save(d)
    lines = ["· “%s” (%s): %s." % (i["text"][:300], _age(i["opened"], now), _became(i)) for i in rows]
    return ("WHAT BECAME OF WHAT YOU RESOLVED (the record, not a grade; a moment that moved on is not a failure):\n"
            + "\n".join(lines) +
            "\nThese are yours. Keep one by starting a line with CARRY: and saying it as you mean it now; release one "
            "with LET GO: and a few of its words. Anything you say nothing about runs out on its own.")


def selector_signal(limit=3, now=None):
    """For the intent selector's picture of him (intent_engine._identity_signals): what he still carries from his
    journal. Empty unless live. Reads only; a turn's offer is recorded by turn_block."""
    if mode() != "live":
        return ""
    now = now or _now()
    live = [i for i in _load()["items"] if i.get("state") == "open" and datetime.fromisoformat(i["expires"]) > now]
    live.sort(key=lambda i: (-int(i.get("restated") or 0), i["opened"]))
    if not live:
        return ""
    return ("What I resolved in my journal and still carry (mine; her present words outrank them, and a move may serve "
            "one without naming it): " + " | ".join(i["text"][:220] for i in live[:limit]))


def stats(days=14, now=None):
    """Counts for measuring whether this helps. No text."""
    now = now or _now()
    since = (now - timedelta(days=days)).isoformat()
    rows = [i for i in _load()["items"] if i.get("opened", "") >= since]
    closed = [i for i in rows if i.get("state") != "open"]
    return {"opened": len(rows), "moves": sum(i["shape"] == "move" for i in rows),
            "aims": sum(i["shape"] == "aim" for i in rows),
            "restated": sum(1 for i in rows if i.get("restated")),
            "lapsed_never_touched": sum(1 for i in closed if i["state"] == "lapsed" and not i.get("touched")),
            "touched": sum(1 for i in rows if i.get("touched")), "recited": sum(1 for i in rows if i.get("recited")),
            "kept": sum(i["state"] == "kept" for i in closed), "released": sum(i["state"] == "released" for i in closed),
            "shown": sum(1 for i in rows if i.get("shown")), "mode": mode()}


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "stats"
    if cmd == "stats":
        refresh(); print(json.dumps(stats(), indent=1))
    elif cmd == "journal-feedback":
        parts = [journal_feedback()]
        try:   # what came of what he asked to change, and the thoughts kept as notes (self_maintenance.py)
            import self_maintenance
            parts.append(self_maintenance.feedback())
        except Exception:
            pass
        print("\n\n".join(p for p in parts if p))
    elif cmd == "mode":
        print(mode())
    else:
        sys.exit("usage: journal_intentions.py [stats|journal-feedback|mode]")
