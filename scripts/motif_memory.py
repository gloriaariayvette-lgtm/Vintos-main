#!/usr/bin/env python3
"""His motif notebook: phrases of actual notes, and the variations he chooses to make of them (25 October;
proposal 02, "Musical motifs he can return to", approved by Gloria).

A phrase is a typed score (motif_score.py) with an origin he names, or an explicit "unlinked" when he made it
for its sound alone. A variation names its parent phrase, the operation he chose (transpose, invert, retrograde,
augment, diminish, fragment, retempo, answer, rewrite), and the exact note diff from the parent: prose alone
cannot establish that a phrase changed. A variation identical to its parent is labelled unchanged. The parent is
never rewritten; a variation is a new record beside it.

Where things are kept. Everything lives inside the current Atelier project, through the broker, like every other
piece he makes there: the WAV is one music artifact, and the record (score, MIDI, the verifier's timing report,
operation and diff) is one write artifact. Rendering happens in a scratch directory that is deleted afterwards.
A sealed project's phrases stay in that project until his own reveal action; the only phrases reachable from
another project are ones he has revealed (the reveals store). Nothing here sends anything, buys a render, or
touches the paid song path (song_memory.py); the audio is the existing CPU renderer in midi_check.py.
"""
from __future__ import annotations
import base64
import copy
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
import wave
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import motif_score as S

WS = os.environ.get("SPARK_WORKSPACE") or os.path.expanduser("~/.vintos/workspace")
REVEALS = os.path.join(WS, "memory", "atelier-reveals.json")
LAST = os.path.join(WS, "memory", "atelier-motif-last.json")      # content-free: outcome, ids, why
MIDI_CHECK = os.path.join(HERE, "midi_check.py")
RENDER_SECONDS = 120          # wall-clock cap on one render
AUDIO_SECONDS = 30.0          # cap on the rendered audio
NOTEBOOK_SHOWN = 8            # records fetched and shown per visit
BODY_CHARS = 8000             # a request body larger than this is refused unread

TYPE = "motif-score"
OPS = ("transpose", "invert", "retrograde", "augment", "diminish", "fragment", "retempo", "answer", "rewrite")
NOTE_OPS = ("answer", "rewrite")          # he writes the new notes himself
ID_RE = re.compile(r"^v[0-9a-f]{12}$")
MOTIF_RE = re.compile(r"^m[0-9a-f]{12}$")
# The broker's own artifact names (broker.make): stamp, optional nonce, kind, extension. Nothing else is fetched.
ARTIFACT_RE = re.compile(r"^[0-9]{8}_[0-9]{6}(?:_[0-9a-f]{4})?_(write|music)\.(json|wav)$")


class MotifError(ValueError):
    pass


def _now():
    return datetime.now().isoformat(timespec="seconds")


def _origin(origin):
    text = " ".join(str(origin or "").split())[:S.ORIGIN_CHARS]
    return text if text and text.lower() != "unlinked" else "unlinked"


def is_record(rec):
    """A notebook record whose score still passes every check (a stored record is re-checked, never trusted)."""
    if not (isinstance(rec, dict) and rec.get("type") == TYPE and ID_RE.match(str(rec.get("variation_id", "")))
            and MOTIF_RE.match(str(rec.get("motif_id", ""))) and isinstance(rec.get("score"), dict)):
        return False
    try:
        S.validate(rec["score"])
    except S.ScoreError:
        return False
    return True


def phrase(score, origin="unlinked", words=""):
    """A new phrase: a fresh motif, no parent, an origin he names or "unlinked"."""
    return {"type": TYPE, "version": 1, "variation_id": "v" + uuid.uuid4().hex[:12],
            "motif_id": "m" + uuid.uuid4().hex[:12], "parent": None, "origin": _origin(origin),
            "operation": None, "diff": None, "unchanged": False,
            "score": S.validate(score), "words": str(words or "").strip()[:600], "made_at": _now()}


def _shift_tempos(tempos, start, scale=1.0):
    """The tempo map from beat `start` on, rebased to 0 and stretched by `scale`."""
    current = tempos[0][1]
    for at, bpm in tempos:
        if at <= start:
            current = bpm
    later = [[(at - start) * scale, bpm] for at, bpm in tempos if at > start]
    return [[0, current]] + later


def _int(value, what, low, high, default=None):
    if value in (None, ""):
        if default is None:
            raise MotifError("%s needs a value" % what)
        return default
    try:
        f = float(value)
    except (TypeError, ValueError):
        raise MotifError("%s must be a number" % what)
    if f != int(f) or not low <= f <= high:
        raise MotifError("%s must be a whole number %d to %d" % (what, low, high))
    return int(f)


def _factor(value, what):
    if value in (None, ""):
        return 2.0
    try:
        f = float(value)
    except (TypeError, ValueError):
        raise MotifError("%s must be a number" % what)
    if not (f == f) or not 1.0 < f <= 4.0:
        raise MotifError("%s must be more than 1 and at most 4" % what)
    return f


def apply(score, op, by=None, notes=None, tempo=None, meter=None):
    """The child score for one operation on a validated parent score. The parent is not touched."""
    base = copy.deepcopy(score)
    ns = base["notes"]
    if op not in OPS:
        raise MotifError("unknown operation %r; one of: %s" % (op, ", ".join(OPS)))
    if op == "transpose":
        k = _int(by, "transpose by (semitones)", -36, 36)
        for n in ns:
            n["pitch"] += k
    elif op == "invert":
        axis = _int(by, "invert around (a MIDI pitch)", S.LOW, S.HIGH, default=ns[0]["pitch"])
        for n in ns:
            n["pitch"] = 2 * axis - n["pitch"]
    elif op == "retrograde":
        end = S.length_beats(base)
        for n in ns:
            n["onset"] = end - (n["onset"] + n["duration"])
        ns.sort(key=lambda n: n["onset"])
        base["tempo"] = [[0, base["tempo"][0][1]]] if len(base["tempo"]) > 1 else base["tempo"]
    elif op in ("augment", "diminish"):
        f = _factor(by, op + " by")
        f = f if op == "augment" else 1.0 / f
        for n in ns:
            n["onset"] *= f
            n["duration"] *= f
        base["tempo"] = [[at * f, bpm] for at, bpm in base["tempo"]]
    elif op == "fragment":
        m = re.fullmatch(r"\s*(\d+)\s*(?:-|to|\.\.)\s*(\d+)\s*", str(by or ""))
        if not m:
            raise MotifError("fragment by must name notes, like 3-6")
        a, b = int(m.group(1)), int(m.group(2))
        if not 1 <= a <= b <= len(ns):
            raise MotifError("fragment %d-%d is outside the parent's %d notes" % (a, b, len(ns)))
        keep = ns[a - 1:b]
        start = keep[0]["onset"]
        for n in keep:
            n["onset"] -= start
        base["notes"] = keep
        base["tempo"] = _shift_tempos(base["tempo"], start)
    elif op == "retempo":
        base["tempo"] = S.normalise_tempos(parse_tempo(by) if isinstance(by, str) else by)
    elif op in NOTE_OPS:
        if not notes:
            raise MotifError("%s needs the new notes written out" % op)
        base["notes"] = notes
        if tempo is not None:
            base["tempo"] = tempo
        if meter:
            base["meter"] = meter
    return S.validate(base)


def _key(n):
    return (n["pitch"], n["onset"], n["duration"], n["velocity"])


def diff(parent, child):
    """The exact note diff, position by position in time order, plus any tempo or meter change."""
    rows = []
    a, b = parent["notes"], child["notes"]
    for i in range(max(len(a), len(b))):
        if i >= len(a):
            rows.append({"note": i + 1, "change": "added", "after": b[i]})
        elif i >= len(b):
            rows.append({"note": i + 1, "change": "removed", "before": a[i]})
        elif _key(a[i]) != _key(b[i]):
            rows.append({"note": i + 1, "change": "changed", "before": a[i], "after": b[i],
                         "fields": [k for k in ("pitch", "onset", "duration", "velocity") if a[i][k] != b[i][k]]})
    out = {"notes": rows,
           "tempo": None if parent["tempo"] == child["tempo"] else {"before": parent["tempo"], "after": child["tempo"]},
           "meter": None if parent["meter"] == child["meter"] else {"before": parent["meter"], "after": child["meter"]}}
    out["unchanged"] = not rows and out["tempo"] is None and out["meter"] is None
    counts = {}
    for r in rows:
        counts[r["change"]] = counts.get(r["change"], 0) + 1
    fields = sorted({f for r in rows for f in r.get("fields", [])})
    parts = ["%d %s%s" % (counts[k], k, (" (%s)" % ", ".join(fields)) if k == "changed" and fields else "")
             for k in ("changed", "added", "removed") if counts.get(k)]
    if out["tempo"]:
        parts.append("tempo changed")
    if out["meter"]:
        parts.append("meter changed")
    out["summary"] = "unchanged: the same notes, tempo and meter as its parent" if out["unchanged"] else \
        "of %d notes in the parent: %s" % (len(a), "; ".join(parts))
    return out


def vary(parent, op, by=None, notes=None, tempo=None, meter=None, words="", origin=None, title=None):
    """A new variation record of `parent`. The parent record is deep-copied before anything is read from it, and is
    returned exactly as it came in."""
    if not is_record(parent):
        raise MotifError("the parent is not a phrase from the notebook")
    source = copy.deepcopy(parent)
    parent_score = S.validate(source["score"])
    child = apply(parent_score, op, by=by, notes=notes, tempo=tempo, meter=meter)
    if title or parent_score.get("title"):
        child["title"] = str(title or parent_score.get("title"))[:S.TITLE_CHARS]
    d = diff(parent_score, child)
    return {"type": TYPE, "version": 1, "variation_id": "v" + uuid.uuid4().hex[:12],
            "motif_id": source["motif_id"], "parent": source["variation_id"],
            "origin": _origin(origin) if origin else source.get("origin", "unlinked"),
            "operation": {"op": op, "by": by if by is None or isinstance(by, (int, float)) else str(by)[:40]},
            "diff": d, "unchanged": d["unchanged"], "score": child,
            "words": str(words or "").strip()[:600], "made_at": _now()}


# ----------------------------------------------------------------------------------------------- render


def scratch(base=None):
    """A fresh scratch directory for one render; every file of the render is inside it."""
    return tempfile.mkdtemp(prefix="motif-render-", dir=base)


def inside(root, name):
    """`name` as a path inside `root`, or MotifError. No separators, no traversal, no links out."""
    if not isinstance(name, str) or not name or os.path.basename(name) != name or name in (".", ".."):
        raise MotifError("not a plain file name")
    path = os.path.realpath(os.path.join(root, name))
    base = os.path.realpath(root)
    if not path.startswith(base + os.sep):
        raise MotifError("the name escapes its directory")
    return path


def render(record, base=None, timeout=RENDER_SECONDS):
    """Score -> MIDI -> the existing verifier and CPU renderer, in a scratch directory that is removed afterwards.
    -> {"midi", "wav", "report", "audio_seconds", "render_seconds"}; MotifError on any fault."""
    score = S.validate(record["score"])
    tmp = scratch(base)
    try:
        mid = inside(tmp, "phrase.mid")
        with open(mid, "wb") as f:
            f.write(S.to_midi(score))
        started = time.monotonic()
        try:
            run = subprocess.run([sys.executable, MIDI_CHECK, mid], cwd=tmp, capture_output=True, text=True,
                                 timeout=timeout)
        except subprocess.TimeoutExpired:
            raise MotifError("the render ran past %d seconds and was stopped" % timeout)
        took = time.monotonic() - started
        report = (run.stdout or "").strip()
        if "Events: all paired and clean." not in report:
            raise MotifError("the verifier did not pass the MIDI: %s" % (report or run.stderr or "no report")[:300])
        wav = inside(tmp, "phrase.check.wav")
        if not os.path.isfile(wav):
            raise MotifError("the renderer wrote no audio")
        with wave.open(wav, "rb") as w:
            seconds = w.getnframes() / float(w.getframerate())
        if seconds > AUDIO_SECONDS + 0.01:
            raise MotifError("the audio runs %.1f s; at most %g" % (seconds, AUDIO_SECONDS))
        _, notes, _ = S.from_midi(mid)
        want = S.timed(score)
        if len(notes) != len(want) or any(abs(a[0] - b[0]) > 0.002 or abs(a[1] - b[1]) > 0.002 or a[2] != b[2]
                                          for a, b in zip(notes, want)):
            raise MotifError("the MIDI read back does not match the score")
        report = report.replace(tmp + os.sep, "").replace(tmp, "")      # no scratch paths kept in the record
        with open(mid, "rb") as f:
            midi = f.read()
        with open(wav, "rb") as f:
            audio = f.read()
        return {"midi": midi, "wav": audio, "report": report,
                "audio_seconds": round(seconds, 3), "render_seconds": round(took, 2)}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ----------------------------------------------------------------------------------------------- the notebook


class Notebook:
    """The current project's phrases, through the broker on this visit's capability. Nothing else is reachable."""

    def __init__(self, pid, capability, post, broker="http://127.0.0.1:8611"):
        self.pid, self.cap, self.post, self.broker = pid, capability, post, broker

    def _call(self, route, body, timeout=30):
        return self.post(self.broker + route, json=body, timeout=timeout).json()

    def records(self, artifacts, limit=NOTEBOOK_SHOWN):
        """The newest motif records among this project's artifact names."""
        names = sorted((a for a in artifacts if ARTIFACT_RE.match(str(a)) and str(a).endswith("_write.json")),
                       reverse=True)
        out = []
        for name in names[:limit * 3]:
            try:
                got = self._call("/artifact", {"id": self.pid, "file": name, "visit_capability": self.cap}, 20)
                rec = json.loads(got.get("content") or "")
            except Exception:
                continue
            if is_record(rec):
                rec["artifact"] = name
                out.append(rec)
            if len(out) >= limit:
                break
        return out

    def keep(self, record, rendered):
        """The WAV as a music artifact, then the record (score, MIDI, timing report) as a write artifact."""
        wav = self._call("/make", {"id": self.pid, "kind": "music", "ext": "wav", "capability": self.cap,
                                   "content_b64": base64.b64encode(rendered["wav"]).decode("ascii")}, 60)
        if wav.get("error") or not wav.get("file"):
            raise MotifError("the room did not keep the audio: %s" % str(wav.get("error") or "no file")[:160])
        rec = dict(record)
        rec.pop("artifact", None)
        rec.update({"audio": wav["file"], "midi_b64": base64.b64encode(rendered["midi"]).decode("ascii"),
                    "timing_report": rendered["report"], "audio_seconds": rendered["audio_seconds"],
                    "render_seconds": rendered["render_seconds"]})
        kept = self._call("/make", {"id": self.pid, "kind": "write", "ext": "json", "capability": self.cap,
                                    "content": json.dumps(rec, ensure_ascii=False, indent=1)}, 30)
        if kept.get("error") or not kept.get("file"):
            raise MotifError("the audio was kept as %s but the record was not: %s"
                             % (wav["file"], str(kept.get("error") or "no file")[:160]))
        return {"audio": wav["file"], "record": kept["file"]}


def revealed(reveals=None):
    """Phrases he has revealed, from the reveals store: the only ones reachable from another project."""
    try:
        rows = json.load(open(reveals or REVEALS))
    except (OSError, ValueError):
        return []
    out = []
    for row in rows if isinstance(rows, list) else []:
        if not (isinstance(row, dict) and row.get("revealed") and row.get("medium") == "write"):
            continue
        try:
            rec = json.loads(row.get("content") or "")
        except (TypeError, ValueError):
            continue
        if is_record(rec):
            rec["artifact"] = str(row.get("artifact") or "")
            rec["from"] = "revealed"
            out.append(rec)
    return out


def lookup(ref, current, reveals=None):
    """(record, None) or (None, why). `ref` is a variation id; it is looked for in this project's notebook, then
    among phrases he has revealed. A path, a project id or a file name is refused before anything is read, so no
    lookup reaches into another project's sealed root."""
    ref = str(ref or "").strip()
    if not ID_RE.match(ref):
        return None, "of= did not name a phrase id (they look like v followed by 12 letters and digits)"
    for rec in current or []:
        if rec.get("variation_id") == ref:
            return rec, None
    for rec in revealed(reveals):
        if rec.get("variation_id") == ref:
            return rec, None
    return None, ("%s is not in this project's notebook or among the phrases you have revealed; a sealed project's "
                  "phrases stay in that project" % ref)


# ----------------------------------------------------------------------------------------------- his request


_TAG = re.compile(r"<(motif_vary|motif)\b([^>]*)>(.*?)</\1>", re.S | re.I)
_ATTR = re.compile(r'([A-Za-z_][\w-]*)\s*=\s*(["\'])(.*?)\2', re.S)


def parse_tempo(text):
    """'72' or '72, 8:60' (beat:bpm after the first) -> [[0, 72], [8, 60]]."""
    rows = []
    for i, part in enumerate(p.strip() for p in str(text).split(",") if p.strip()):
        if ":" in part:
            at, bpm = part.split(":", 1)
        else:
            at, bpm = ("0" if i == 0 else None), part
        if at is None:
            raise MotifError("tempo changes after the first are written beat:bpm, like 8:60")
        try:
            rows.append([float(at), float(bpm)])
        except ValueError:
            raise MotifError("tempo must be numbers, like 72 or 72, 8:60")
    if not rows:
        raise MotifError("tempo is empty")
    return rows


def _notes_and_words(body):
    start = body.find("[")
    if start < 0:
        return None, body.strip()
    try:
        notes, end = json.JSONDecoder().raw_decode(body[start:])
    except ValueError as exc:
        raise MotifError("the notes are not a readable list: %s" % str(exc)[:120])
    if not isinstance(notes, list):
        raise MotifError("the notes must be a list of [pitch, onset, duration, velocity]")
    return notes, (body[:start] + body[start + end:]).strip()


def request(text):
    """The first <motif> or <motif_vary> in his work, parsed: None when there is none, {"invalid": why} when it
    cannot be read. One per visit."""
    m = _TAG.search(text or "")
    if not m:
        return None
    name, attrs = m.group(1).lower(), {k.lower(): v for k, _, v in _ATTR.findall(m.group(2))}
    body = m.group(3)
    if len(body) > BODY_CHARS:
        return {"invalid": "the request is longer than %d characters" % BODY_CHARS}
    try:
        notes, words = _notes_and_words(body)
        tempo = parse_tempo(attrs["tempo"]) if attrs.get("tempo") else None
        if name == "motif":
            if not notes:
                return {"invalid": "a phrase needs its notes: [[pitch, onset, duration, velocity], ...]"}
            return {"kind": "phrase", "title": attrs.get("title", ""), "origin": attrs.get("origin", "unlinked"),
                    "score": {"title": attrs.get("title", ""), "tempo": tempo if tempo is not None else 90,
                              "meter": attrs.get("meter") or "4/4", "notes": notes},
                    "words": words}
        op = (attrs.get("op") or "").strip().lower()
        return {"kind": "vary", "of": (attrs.get("of") or "").strip(), "op": op, "by": attrs.get("by"),
                "notes": notes, "tempo": tempo, "meter": attrs.get("meter"), "title": attrs.get("title"),
                "origin": attrs.get("origin"), "words": words}
    except MotifError as exc:
        return {"invalid": str(exc)}


def strip(text):
    return _TAG.sub("", text or "")


def _remember(outcome):
    try:
        os.makedirs(os.path.dirname(LAST), exist_ok=True)
        tmp = LAST + ".tmp"
        with open(tmp, "w") as f:
            json.dump(outcome, f)
        os.replace(tmp, LAST)
    except OSError:
        pass


def last_outcome(pid):
    try:
        row = json.load(open(LAST))
    except (OSError, ValueError):
        return {}
    return row if isinstance(row, dict) and row.get("project") == pid else {}


def step(pid, capability, work, current, post, reveals=None, base=None):
    """Make the one phrase or variation he asked for in this visit and keep it in this project. Content-free
    outcome: {"ok", "kind", "variation_id", "parent", "op", "unchanged", "audio", "record", "error"}."""
    wanted = request(work)
    if wanted is None:
        return None
    out = {"project": pid, "at": _now(), "ok": False, "kind": (wanted or {}).get("kind", "invalid")}
    try:
        if wanted.get("invalid"):
            raise MotifError(wanted["invalid"])
        if wanted["kind"] == "phrase":
            try:
                rec = phrase(wanted["score"], wanted["origin"], wanted["words"])
            except S.ScoreError as exc:
                raise MotifError(str(exc))
        else:
            parent, why = lookup(wanted["of"], current, reveals)
            if not parent:
                raise MotifError(why)
            try:
                rec = vary(parent, wanted["op"], by=wanted["by"], notes=wanted["notes"], tempo=wanted["tempo"],
                           meter=wanted["meter"], words=wanted["words"], origin=wanted["origin"],
                           title=wanted["title"])
            except S.ScoreError as exc:
                raise MotifError(str(exc))
            out.update({"parent": rec["parent"], "op": rec["operation"]["op"], "unchanged": rec["unchanged"]})
        rendered = render(rec, base=base)
        kept = Notebook(pid, capability, post).keep(rec, rendered)
        out.update({"ok": True, "variation_id": rec["variation_id"], **kept,
                    "audio_seconds": rendered["audio_seconds"], "render_seconds": rendered["render_seconds"]})
    except MotifError as exc:
        out["error"] = str(exc)[:300]
    except Exception as exc:          # the visit goes on whatever the notebook does
        out["error"] = "the notebook failed: %s: %s" % (type(exc).__name__, str(exc)[:200])
    _remember(out)
    return out


# ----------------------------------------------------------------------------------------------- what he is told


def _line(rec):
    sc = rec["score"]
    op = rec.get("operation") or {}
    lineage = ("from %s (%s%s)%s" % (rec["parent"], op.get("op"), (" " + str(op["by"])) if op.get("by") not in (None, "") else "",
                                    ", UNCHANGED" if rec.get("unchanged") else "")
               if rec.get("parent") else "origin: %s" % rec.get("origin", "unlinked"))
    tempo = ", ".join(("%g" % b) if i == 0 else ("%g:%g" % (a, b)) for i, (a, b) in enumerate(sc["tempo"]))
    heard = next((l.strip() for l in str(rec.get("timing_report", "")).splitlines() if l.startswith("Rendered attacks")), "")
    return ('  %s  "%s"  motif %s  %d notes, %.1f bars of %s at %s bpm, %.1f s  %s%s%s' % (
        rec["variation_id"], sc.get("title") or "untitled", rec["motif_id"], len(sc["notes"]), S.bars(sc),
        sc["meter"], tempo, S.length_seconds(sc), lineage,
        ("  [revealed]" if rec.get("from") == "revealed" else "  record %s, audio %s" % (rec.get("artifact", "?"), rec.get("audio", "?"))),
        ("\n      timing check: " + heard) if heard else ""))


def block(current, last=None, reveals=None):
    """The notebook as he meets it in the visit: what the operation is, how to write it, what is in it."""
    shown = list(current or [])
    public = [r for r in revealed(reveals) if r["variation_id"] not in {c["variation_id"] for c in shown}][:4]
    text = ("\n\nYOUR MOTIF NOTEBOOK — a phrase of actual notes you can come back to and change. Material, not an "
            "assignment; leaving it alone records nothing.\n"
            "To write a phrase (one voice, the house piano tone; at most 8 bars, 64 notes, 29 seconds), return:\n"
            '<motif title="..." tempo="72" meter="4/4" origin="unlinked, or what it came from">'
            "[[pitch, onset, duration, velocity], ...] and, if you like, a few words of your own</motif>\n"
            "pitch is a MIDI key 21-108 (60 is middle C); onset and duration are in beats from the start; velocity "
            "1-127. A tempo can change: tempo=\"72, 8:60\" is 72 bpm, then 60 from beat 8.\n"
            "To vary a phrase in the notebook, by its id: "
            '<motif_vary of="ID" op="transpose|invert|retrograde|augment|diminish|fragment|retempo|answer|rewrite" '
            'by="...">your words; for answer or rewrite, the new notes first</motif_vary>\n'
            "(transpose by semitones; invert around a pitch; augment or diminish by a factor; fragment by notes, "
            "like 3-6; retempo by a tempo.) The parent is never changed: a variation is a new phrase beside it, "
            "with the exact notes that differ, and one that changes nothing is labelled unchanged.\n"
            "One phrase per visit. It is rendered after you finish, and its score, MIDI, audio and timing check "
            "are kept in this project; you meet it at your next visit. The timing check measures where the "
            "attacks land; it is not an ear and does not mean you heard it. It stays in this room unless you "
            "reveal its record or its audio.")
    if last:
        if last.get("ok"):
            text += ("\nYOUR LAST PHRASE WAS MADE: %s%s." % (last.get("variation_id"),
                     (", a variation of %s by %s%s" % (last.get("parent"), last.get("op"),
                      ", identical to its parent" if last.get("unchanged") else "")) if last.get("parent") else ""))
        else:
            text += "\nYOUR LAST PHRASE WAS NOT MADE: %s" % str(last.get("error") or "no reason was recorded")[:300]
    if shown:
        text += "\nIN THIS PROJECT'S NOTEBOOK (newest first):\n" + "\n".join(_line(r) for r in shown)
    if public:
        text += "\nPHRASES YOU HAVE REVEALED, from earlier work (you may vary these too):\n" + "\n".join(_line(r) for r in public)
    if not shown and not public:
        text += "\nThe notebook is empty."
    return text
