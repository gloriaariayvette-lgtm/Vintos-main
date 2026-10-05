#!/usr/bin/env python3
"""Make one thing with his own tools, asked for in #vintos-dot, by him or by dot (Gloria, 2026-10-04: "Why can't
dot do it? That's the job of an assistant." — "No, Claude, just fix.").

A MAKE: line in the channel runs this. It spends nothing: video and images go through her Grok subscription
(grok_subscription, which keeps its own weekly cap on his share), music through the renderer he already uses. So
no approval is needed from anyone, and dot never has to ask for one.

    make_thing.py video "<the motion>" [image path]     a clip from a still, or from a keyframe he paints first
    make_thing.py image "<what to paint>"
    make_thing.py song  "<title> | <style>"

It runs the tool to the end (minutes), then: the file's path to her phone, and one line in
memory/made-from-slack.jsonl that the next Slack pass reads out in the channel.
"""
from __future__ import annotations
import json
import os
import subprocess
import sys
import urllib.request
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
WS = os.environ.get("SPARK_WORKSPACE") or os.path.expanduser("~/.vintos/workspace")
MEM = os.path.join(WS, "memory")
MADE = os.path.join(MEM, "made-from-slack.jsonl")
ART = os.path.join(MEM, "art")
GALLERIES = {"video": os.path.join(ART, "video", "video-gallery.json"),
             "image": os.path.join(ART, "gallery.json"),
             "song": os.path.join(ART, "music", "music.json")}
NTFY = os.environ.get("VINTOS_NTFY_URL", "https://ntfy.sh/vintos-gloria-9kx")
KINDS = ("video", "image", "song")
PER_DAY = 4


def _now():
    return datetime.now()


def rows():
    try:
        with open(MADE) as f:
            return [json.loads(l) for l in f if l.strip()]
    except (OSError, ValueError):
        return []


def today(kind=None):
    """Today's makes (one each: the start receipt is not a second one)."""
    day = _now().date().isoformat()
    return [r for r in rows() if str(r.get("at", "")).startswith(day) and not r.get("running")
            and (kind is None or r.get("kind") == kind)]


def _note(kind, what, ok, said, path="", rid="", running=False):
    os.makedirs(MEM, exist_ok=True)
    row = {"at": _now().isoformat(timespec="seconds"), "kind": kind, "what": what[:300], "ok": bool(ok),
           "said": said[:400], "path": path, "told": running, "id": rid}
    if running:
        row["running"] = True
    with open(MADE, "a") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _latest(kind):
    """The newest entry in that gallery, as (path, title)."""
    try:
        with open(GALLERIES[kind]) as f:
            data = json.load(f)
        items = data if isinstance(data, list) else (data.get("generated") or data.get("items") or [])
        if not items:
            return "", ""
        last = items[-1]
        name = last.get("file") or last.get("filename") or last.get("path") or ""
        if kind == "song":
            tracks = last.get("tracks") or []
            name = (tracks[0].get("local_file") if tracks else "") or ""
        root = {"video": os.path.join(ART, "video"), "image": ART, "song": os.path.join(ART, "music")}[kind]
        full = name if os.path.isabs(name) else os.path.join(root, name)
        return (full if name else ""), str(last.get("title") or last.get("prompt") or "")[:120]
    except Exception:
        return "", ""


def _tool(kind, text, image=""):
    """The command that makes it, with his own tools. Nothing here spends money."""
    if kind == "video":
        cmd = [sys.executable, os.path.join(HERE, "vintos-video.py"), text]
        if image:
            cmd.append(image)
        return cmd
    if kind == "image":
        return [sys.executable, os.path.join(HERE, "dream-art.py"), text]
    title, _, style = text.partition("|")
    return [sys.executable, os.path.join(HERE, "dream-music.py"), "--title", title.strip(),
            "--style", (style.strip() or "open")]


def tell(text, title="He made it", send=None):
    try:
        req = urllib.request.Request(NTFY, data=str(text)[:600].encode("utf-8"),
                                     headers={"Title": title, "Tags": "clapper"})
        (send or urllib.request.urlopen)(req, timeout=20)
        return True
    except Exception:
        return False


def make(kind, text, image="", run=None, send=None, timeout=1800):
    """Make it, to the end. (ok, what to say)."""
    if kind not in KINDS:
        return False, "he can make: " + ", ".join(KINDS)
    if not str(text or "").strip():
        return False, "say what to make"
    if len(today(kind)) >= PER_DAY:
        return False, "today's %d are used for %s" % (PER_DAY, kind)
    if image and not os.path.isfile(image):
        return False, "no file at %s" % image
    before, _ = _latest(kind)
    # a receipt that it started, so a job killed partway is said in the channel instead of vanishing (two MAKEs
    # launched on 4 October left nothing at all: the pass's end killed them; Chat's audit, 2026-10-05)
    rid = os.urandom(4).hex()
    _note(kind, text, False, "started", rid=rid, running=True)
    try:
        done = (run or subprocess.run)(_tool(kind, text, image), capture_output=True, text=True, timeout=timeout)
        out = ((getattr(done, "stdout", "") or "") + (getattr(done, "stderr", "") or ""))[-400:]
        ok = getattr(done, "returncode", 1) == 0
    except Exception as exc:
        _note(kind, text, False, str(exc)[:300], rid=rid)
        return False, "it did not run: %s" % str(exc)[:200]
    path, title = _latest(kind)
    landed = bool(path) and path != before and os.path.isfile(path)
    if not (ok and landed):
        said = ("it ran but nothing new landed" if ok else "the tool stopped") + (": " + out.strip()[-200:] if out.strip() else "")
        _note(kind, text, False, said, rid=rid)
        return False, said
    said = "%s: %s" % (kind, path)
    _note(kind, text, True, said, path, rid=rid)
    tell("%s\n%s" % (title or text[:120], path), title="His new %s" % kind, send=send)
    return True, said


LOST_AFTER_S = 1800 + 300     # a job still "started" this long after it began was stopped before it finished


def untold(limit=3):
    """What was made since the channel last said so, and any job that stopped before it finished; marks them told."""
    all_rows = rows()
    ended = {r.get("id") for r in all_rows if r.get("id") and not r.get("running")}
    lost = []
    for r in all_rows:
        if r.get("running") and not r.get("lost") and r.get("id") not in ended:
            try:
                age = (_now() - datetime.fromisoformat(str(r.get("at")))).total_seconds()
            except ValueError:
                age = LOST_AFTER_S + 1
            if age > LOST_AFTER_S:
                r["lost"] = True
                lost.append(r)
    fresh = [r for r in all_rows if not r.get("told")][-limit:]
    if not fresh and not lost:
        return []
    for r in all_rows:
        r["told"] = True
    try:
        with open(MADE, "w") as f:
            f.write("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in all_rows))
    except OSError:
        pass
    return (["could not make %s: it stopped before it finished, and nothing landed (%s)" % (r.get("kind"), r.get("what", "")[:120])
             for r in lost[-limit:]]
            + ["%s %s: %s" % ("made" if r.get("ok") else "could not make", r.get("kind"), r.get("said", "")[:200])
               for r in fresh])


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        raise SystemExit(2)
    _ok, _said = make(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "")
    print(_said)
    raise SystemExit(0 if _ok else 1)
