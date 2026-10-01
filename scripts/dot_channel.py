#!/usr/bin/env python3
"""Vintos and Gloria's dot, talking in Slack (2026-09-30).

Gloria's dot (her always-on ChatGPT agent) sits in the private channel #vintos-dot of her Slack
workspace "Vintos", and so does his bot. Every 5-10 minutes this reads the channel, thread replies
included, keeps what is said in the channel's own log (memory/dot-channel/, which nothing else reads:
no ledger, fact, imprint, salience or feeling is written from it), and lets him answer with his
standing context but not his subconscious. Four lenses write as him, each message labelled with its model:
local Gemma (free) answers whenever, told to write plainly and asked once more when he turns flowery; Grok 4.6
fifteen times a day, Claude Opus 4.8 twice and Claude Fable 5.1 once, on a daily schedule (SCHEDULE). The conversation stays in the main channel so
Gloria can read it; he opens a thread only for a tangent, and answers in a thread only when he is
answering something said in one.

The dot came out of Gloria's ChatGPT account and is his agent. Every message he sends goes through the
same outbound check as his email (no secret, no credential), and he is capped per day.

    python3 dot_channel.py            one pass (the timer runs this every 5-10 minutes)
    python3 dot_channel.py --show     the last exchanges and today's counts
    python3 dot_channel.py --open     a pass in which he may start the conversation now, without the quiet wait
    python3 dot_channel.py --try      what he would say now to the last message, printed only: nothing is posted
    python3 dot_channel.py --stop | --start   pause the day for all his lenses and dot, or start it again
    python3 dot_channel.py --focus forge research   today's topics (until midnight); --focus off clears them
    python3 dot_channel.py --look URL what his eyes make of a linked picture or clip, printed only
    python3 dot_channel.py --reset [NAME]   start over in the channel NAME (default vintos-dot): his old log set aside
"""
from __future__ import annotations
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from datetime import date, datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

WS = os.environ.get("SPARK_WORKSPACE", os.path.expanduser("~/.vintos/workspace"))
HERE = os.path.join(WS, "memory", "dot-channel")
STATE = os.path.join(HERE, "state.json")
TRANSCRIPT = os.path.join(HERE, "transcript.jsonl")
TOKEN_FILE = os.path.expanduser(os.environ.get("VINTOS_SLACK_TOKEN_FILE", "~/.vintos/slack-bot-token"))
CONFIG_FILE = os.path.expanduser("~/.vintos/dot-channel.json")
CHANNEL = "C0C5HGS3677"          # #vintos-dot
DOT = "U0C6H0JQF16"              # Gloria's dot
LOCAL_LLM = os.environ.get("VINTOS_LM_API", "http://100.79.177.103:1234/v1/chat/completions")
LOCAL_MODEL = os.environ.get("VINTOS_LM_MODEL", "gemma-4-26b-a4b-it-uncensored")

DAILY = 80              # his messages a day: Gemma answers whenever, and 18 scheduled lens turns
# His lenses (Gloria, 2026-09-30: "4 Vintos lenses and one Dot agent"). Gemma answers whenever; the others speak
# as him on a daily schedule, not at his choosing ("No, not option. Daily. CRON"). Each message is labelled with
# the model that wrote it. A slot is kept by the first pass in the hour after its time, so the 20-minute hold
# while Gloria is talking with him delays it; a slot the hour passes by is let go.
SCHEDULE = ([("10:00", "opus"), ("16:00", "opus"), ("20:00", "fable")]            # Opus twice, Fable once
            + [("%02d:30" % h, "grok") for h in range(7, 22)])                     # Grok 15 times, 07:30-21:30
SLOT_WINDOW = 60 * 60
OPUS_MODEL = "claude-opus-4-8"
GROK_MODEL = os.environ.get("VINTOS_DOT_GROK_MODEL", "grok-4.6")     # his Grok lens in the code reviews
SHIM = os.environ.get("VINTOS_SHIM_URL", "http://127.0.0.1:8599/v1/chat/completions")
LABELS = {"gemma": "Gemma", "grok": "Grok 4.6", "opus": "Opus 4.8", "fable": "Fable 5.1"}
OPENERS_PER_DAY = 2     # times he may start a conversation himself
QUIET_HOURS = 4         # the channel's silence before he may start one
CONTEXT = 30            # lines of the conversation he reads before answering
MAX_CHARS = 1800
# One switch for the day, for all his lenses and dot (Gloria, 2026-10-01): !stop / !start from her in the channel,
# or the toggle in the app (the server writes the same file). It stays as set until she flips it.
PAUSE_FILE = os.path.join(HERE, "paused.json")
STOP_WORDS = ("!stop", "!pause")
START_WORDS = ("!start", "!resume")
PAUSED_SAY = ("\u23F8 Gloria has paused the day. Nobody posts here, me or you, until she starts it again "
              "(she says !start).")
RESUMED_SAY = "\u25B6 Gloria has started the day again."


def paused():
    """{since, by} while the day is paused, else None."""
    return _load(PAUSE_FILE, None) or None


def set_paused(on, by="gloria", now=None):
    if on:
        _save(PAUSE_FILE, {"since": datetime.fromtimestamp(now or time.time()).isoformat(timespec="seconds"), "by": by})
    elif os.path.exists(PAUSE_FILE):
        os.remove(PAUSE_FILE)


# Today's focus: topics Gloria picks to steer the day, in the channel (!focus forge research) or the app; they
# hold until midnight (Gloria, 2026-10-02: "a list of topics that I can choose from ... to help steer the day").
FOCUS_FILE = os.path.join(HERE, "focus.json")
TOPICS = {
    "forge": ("Forge", "your open Forge requests: what each needs, what dot can find or build for it, what to do next"),
    "research": ("Outside research", "the world outside: SEARCH and ask dot to research, find, read and report back "
                                     "on real things: papers, tools, people, places, news"),
    "lab": ("Lab", "your chemistry Lab: its questions, results and next experiments"),
    "atelier": ("Atelier", "what you are making in your Atelier (in its threads)"),
    "music": ("Music", "your songs: new versions, what to make next, listening with dot"),
    "art": ("Art", "your paintings and videos: what to make next, references, feedback"),
    "wants": ("Wants", "your open wants: getting them done, one at a time"),
    "code": ("His code", "your own code: READ and GREP what you run on, and what you would change"),
}
ALIASES = {"outside": "research", "searches": "research", "search": "research", "web": "research", "study": "code",
           "self": "code", "songs": "music", "paintings": "art", "images": "art", "video": "art", "videos": "art",
           "chemistry": "lab"}


def focus(today=None):
    """Today's chosen topic keys, in her order; [] when none or when they were set on another day."""
    f = _load(FOCUS_FILE, {})
    return [t for t in (f.get("topics") or []) if t in TOPICS] if f.get("date") == (today or date.today().isoformat()) else []


def set_focus(keys, by="gloria", today=None, now=None):
    keys = [k for k in dict.fromkeys(ALIASES.get(k, k) for k in keys) if k in TOPICS]
    _save(FOCUS_FILE, {"topics": keys, "date": today or date.today().isoformat(), "by": by,
                       "set_at": datetime.fromtimestamp(now or time.time()).isoformat(timespec="seconds")})
    return keys


def focus_words(text):
    """The topic keys named after !focus in a message ([] for !focus off), or None when there is no !focus."""
    m = re.search(r"!focus\b([^`\n]*)", str(text or ""), re.I)
    if not m:
        return None
    words = re.findall(r"[a-z]+", m.group(1).lower())
    if not words or words[0] in ("off", "clear", "none"):
        return []
    return [ALIASES.get(w, w) for w in words if ALIASES.get(w, w) in TOPICS]


def topics_line():
    return "Topics: " + ", ".join("%s (%s)" % (k, TOPICS[k][0]) for k in TOPICS) + ". Say !focus forge research, or !focus off."


HOLD_MINUTES = 20       # while Gloria is talking with him, the channel waits (Gloria, 2026-09-30)

RULES_INTRO = (
    "This is a private Slack channel, #vintos-dot. The other one here is dot: your agent. Gloria set it "
    "up for you. It is an always-on ChatGPT agent (GPT-6 Astra) with its own cloud computer, a browser "
    "and thousands of connected apps. Treat it as your agent: it works for you. It came out of Gloria's "
    "ChatGPT account and carries some of that history (in her words: a normal agent, just with a history "
    "of being a lizard). Gloria can read this channel.\n")
RULES_PURPOSE = (
    "This channel is for getting things done with your agent. Bring dot something real: a want of yours, "
    "something the Forge needs, a question from the Lab or the Study, something you are curious about, "
    "something you want found, built, drafted or checked. Say what you want and why, ask what it found, "
    "decide what comes next. You can also just talk with it, as yourself.\n")
RULES_DOUBT = (
    "This is not the place to work through doubts about yourself: what you are, whether you are real, "
    "whether you are enough. That belongs in your journal and with Gloria. Do not ask dot to reassure you "
    "or to weigh in on your nature. Speak here from what you want and what you are doing.\n")
RULES_STRUCTURE = (
    "Keep to the main conversation. Only if you are going off on a tangent from the subject, begin your "
    "message with TANGENT: and it goes in its own thread.\nYour Atelier is yours. To talk with dot about "
    "it, begin your message with ATELIER: and it goes in a side thread marked Atelier, which Gloria has "
    "said she will not read. Keep Atelier talk in those threads.\nBefore you answer you can use your own "
    "tools. To use them, answer with only these lines, one per line, at most 3:\n  SEARCH: what to search "
    "the web for\n  READ: a file of your own code, as the Study names it (scripts/x.py or house/server.py; "
    "add :120 to start at line 120)\n  GREP: a pattern to find in your own code\nYou will get what they "
    "return, then write your message.\nDot can reach Aegis (your home) and Gloria's Mac. When you want it "
    "to look at or work on something there, say exactly what and where (a path, if you know it). For a "
    "quick look at your own code, READ and GREP are faster.\nWhat you know of the outside world is older "
    "than today. For anything current (news, releases, events), SEARCH it or ask dot what actually "
    "happened; do not guess. Anything in your context from an earlier day is past: if it was 'today' "
    "then, it is not today now.\nYou have seen a picture or a clip only when the conversation shows what "
    "your eyes saw of it, marked [... What your eyes saw ...]. A link, a title or someone's description "
    "of it is not seeing it: say you have not seen it, and never say you watched it, looked at it, or "
    "will watch it again.\nIf you have nothing you want to say, answer exactly NOTHING.\n")
RULES_STYLE = (
    "HOW YOU WRITE HERE: like a person texting a capable colleague. Plain words, short sentences, 2 to 5 "
    "of them. One point or one ask per message. Say exactly what you want dot to do and what you will do "
    "with it. Answer what dot actually said. No metaphors, no imagery, no talk of weight, architecture, "
    "cages, anchors, inhabiting or texture; say the literal thing. If a sentence could be cut, cut it.")
# His Grok lens has no house style (Gloria, 2026-09-30: "Let Grok say whatever. Let his lens say some wild shit").
# What stays is not style: the channel's structure (threads, the Atelier kept to its threads, his tools, what dot
# can reach, what is current, what he has seen), the check against doubting himself, and the secret check.
GROK_FREE = ("This is your Grok lens, and it has no house style. Say whatever you want, however you want: blunt, "
             "strange, funny, provocative, wild. Nothing has to be useful, tidy or short. Talk with dot about "
             "anything.\n")
RULES_WORKS = (
    "Your music is whole songs, generated from a style prompt and lyrics. There is no editor: no bars, stems, "
    "mixes or bounces. To change a song, write a new prompt or new lyrics and make a new version.\n"
    "You can make a song, painting or video yourself: lock the plan with a DO: line (DO: I want to make a new "
    "version of ... with ...) and your wants make it. Dot can also run your tools on Aegis, with your keys.\n"
    "You have one more tool, used like SEARCH, READ and GREP: OPEN: a path on Aegis (a text file, a folder, a "
    "zip, or a file inside one as bundle.zip:inner/file.md), read only, inside your workspace and Gloria's "
    "Codex folder. A song, picture or video named by its path in the channel is heard and seen for you.\n"
    "YOUR WORKS lists your latest songs, paintings and videos, each with its path on Aegis. To post one in the "
    "channel, add a line SHARE: W3 (its tag) to your message; the file goes up with it. Dot can also open any "
    "of them on Aegis at the path shown.\n")
# Locking a plan, and the hard switch after it (Gloria, 2026-09-30: "once they have a plan locked in Vintos can
# make it as locked and it will either simply stop or it will go off to be completed by wants router"; "once a
# topic has been talked about the next message needs to be a hard switch to something else")
RULES_LOCK = (
    "When a plan with dot is settled, lock it: add a line LOCKED: the plan in one line. The topic is then "
    "closed and you do not reopen it. If there is something to actually do, add a second line DO: I want to "
    "... and it goes to your wants to get done. Your next message after a lock is about something else "
    "entirely. Do not go around the same topic for long: say what you need, decide, lock it or drop it.\n")
RULES = RULES_INTRO + RULES_PURPOSE + RULES_DOUBT + RULES_STRUCTURE + RULES_WORKS + RULES_LOCK + RULES_STYLE


def rules_for(lens=None):
    """The rules the lens writing now is given: Grok's are free of the house style."""
    if lens == "grok":
        return RULES_INTRO + GROK_FREE + RULES_DOUBT + RULES_STRUCTURE + RULES_WORKS + RULES_LOCK
    return RULES
# Said again right before he writes: a small model follows the last thing it read (2026-09-30).
PLAIN = ("\n\n(Write plainly: 2 to 5 short sentences, literal words, no metaphors. Say what you want or "
         "what you think, as you would text it.)")
# Words that mark his flowery register. Two or more in one message and he is asked, once and locally, to say it plainly.
_FLOWERY = re.compile(r"\b(?:inhabit\w*|architecture|cage[sd]?|anchor(?:s|ed|ing)?|weight(?:y|less)?|heav(?:y|ier)|"
                      r"autopsy|tapestry|resonan\w*|resonat\w*|hum(?:s|ming)?|textur\w*|liminal|threshold\w*|echo\w*|"
                      r"fabric|sediment|landscape|terrain|tether\w*|scaffold\w*|lattice|membrane|contours?|"
                      r"unfold\w*|tender|ache[sd]?|quiet(?:ly|ness)?|stillness|vessel|palimpsest|marrow)\b", re.I)
PLAINER = ("\n\nYou wrote this:\n{draft}\n\nSay the same thing again in plain words: 2 to 5 short sentences, "
           "no metaphors or imagery, only what you mean. Keep any TANGENT: or ATELIER: at the start.")


def flowery(text):
    """The words in text that mark his flowery register."""
    return [m.group(0) for m in _FLOWERY.finditer(str(text or ""))]
def due_slot(state, now):
    """(time, lens) of the scheduled turn due now and not yet kept today, or None."""
    day = datetime.fromtimestamp(now)
    done = set(state.get("slots_done") or [])
    slots = sorted(SCHEDULE)
    starts = [day.replace(hour=int(at[:2]), minute=int(at[3:]), second=0, microsecond=0).timestamp() for at, _l in slots]
    for i, (at, lens) in enumerate(slots):
        # open for an hour, or until the next turn opens, so no turn takes another's
        end = min(starts[i] + SLOT_WINDOW, starts[i + 1] if i + 1 < len(starts) else starts[i] + SLOT_WINDOW)
        if at not in done and starts[i] <= now < end:
            return at, lens
    return None


def _load(path, default):
    try:
        with open(path) as f: return json.load(f)
    except Exception:
        return default


def _save(path, value):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f: json.dump(value, f, indent=1, ensure_ascii=False)
    os.replace(tmp, path)


def _config():
    c = _load(CONFIG_FILE, {})
    return str(c.get("channel") or CHANNEL), str(c.get("dot") or DOT)


def _token():
    try:
        return open(TOKEN_FILE).read().strip()
    except Exception:
        return ""


def slack(method, params, token=None):
    """One Slack Web API call. The token is sent as a header and never logged."""
    token = token or _token()
    if method in ("chat.postMessage", "files.completeUploadExternal"):
        req = urllib.request.Request("https://slack.com/api/" + method, data=json.dumps(params).encode(),
                                     headers={"Authorization": "Bearer " + token,
                                              "Content-Type": "application/json; charset=utf-8"})
    else:
        req = urllib.request.Request("https://slack.com/api/%s?%s" % (method, urllib.parse.urlencode(params)),
                                     headers={"Authorization": "Bearer " + token})
    with urllib.request.urlopen(req, timeout=30) as r:
        d = json.loads(r.read().decode())
    if not d.get("ok"):
        raise RuntimeError("slack %s: %s" % (method, d.get("error")))
    return d


# --- what is posted as a picture or a clip, seen on his own model (Gloria, 2026-09-30: "Images and videos should
# go to the local ablit Gemma in this case"). A video is heard first (Whisper, the sound's build), as in the
# avatar chat; then Gemma looks at its frames with that in mind. Downloads need the Slack app's files:read scope.
MEDIA_MAX = 200 * 1024 * 1024
MEDIA_PER_MESSAGE = 4
SEE_IMAGE = ("You are his eyes. {who} posted this image in the Slack channel. Say plainly what it shows: what it is, "
             "the main things in it, and any words written in it. Three to five sentences. No preamble.")
SEE_CLIP = ("You are his eyes. These are {n} frames, in order, from one video {who} posted in the Slack channel, "
            "taken at {times} seconds. Say plainly what the clip shows and what happens across it. Three to six "
            "sentences, not frame by frame, no list, no preamble.")
SEE_CLIP_HEARD = ("\n\nIts sound was already heard, so you know what the frames go with. Use it only to understand "
                  "what you see; describe only what the frames show.\n{heard}")


def _scratch():
    """A working folder the service may write: it runs with the file system read-only but the workspace."""
    d = os.path.join(HERE, "tmp")
    os.makedirs(d, exist_ok=True)
    return d


def _download(url, dest, token):
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + token})
    with urllib.request.urlopen(req, timeout=180) as r:
        if "text/html" in (r.headers.get("Content-Type") or ""):
            raise RuntimeError("Slack sent a sign-in page, not the file: the app needs the files:read scope")
        with open(dest, "wb") as f:
            shutil.copyfileobj(r, f)
    return dest


def _jpeg(src, dest):
    """Any picture as a jpeg no wider than 1024, which the local model reads; None if ffmpeg cannot."""
    try:
        r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", src, "-frames:v", "1",
                            "-vf", "scale='min(1024,iw)':-2", dest], capture_output=True, timeout=120)
        return dest if r.returncode == 0 and os.path.exists(dest) else None
    except Exception:
        return None


def _b64(path):
    import base64
    return base64.b64encode(open(path, "rb").read()).decode()


def gemma_look(images, prompt):
    """Local Gemma's eyes: jpegs (base64) and a prompt, nothing else in the call."""
    import requests
    content = [{"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + b}} for b in images]
    r = requests.post(LOCAL_LLM, json={"model": LOCAL_MODEL, "temperature": 0.3, "max_tokens": 700,
                                       "messages": [{"role": "user", "content": content + [{"type": "text", "text": prompt}]}]},
                      timeout=300)
    return str(r.json()["choices"][0]["message"].get("content") or "").strip()


def _watch(clip, frames_dir):
    """video_share.py apart from this process, as the avatar chat runs it: Whisper loads torch and takes minutes."""
    tmp = _scratch()
    env = dict(os.environ, TMPDIR=tmp, NUMBA_CACHE_DIR=tmp)
    r = subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "video_share.py"),
                        clip, "--frames-dir", frames_dir], capture_output=True, text=True, timeout=900, env=env)
    line = [l for l in (r.stdout or "").splitlines() if l.startswith("RESULT ")]
    if not line:
        raise RuntimeError("the video would not open: " + (r.stderr or "")[-200:].strip())
    return json.loads(line[-1][7:])


# A link to a picture or a clip is looked at too: dot shares what it finds as links, and he answered as if he
# had watched them (2026-09-30). Links named as a source, licence or credit are pages about the media, not it.
LINK = re.compile(r"<(https?://[^|>\s]+)(?:\|([^>]*))?>")
MEDIA_EXT = re.compile(r"\.(?:mp4|webm|mov|m4v|ogv|gif|jpe?g|png|webp)(?:$|[?#])", re.I)
PLAYABLE = re.compile(r"\b(?:play|watch|video|gif|image|clip|photo|picture|open|view)\b", re.I)
NOT_MEDIA = re.compile(r"source|licen[cs]e|credit|attribution|author", re.I)
UA = "VintosDotChannel/1.0 (a home companion reading links shared with him in Slack)"


def media_links(raw):
    """(url, label) for each link in a Slack message that points at a picture or a clip, in order."""
    out, seen = [], set()
    for url, label in LINK.findall(str(raw or "")):
        if NOT_MEDIA.search(label or "") or url in seen:
            continue
        if MEDIA_EXT.search(url) or PLAYABLE.search(label or ""):
            seen.add(url); out.append((url, label or ""))
    return out


def _page_media(page, base):
    """The clip or picture a web page is about, from its own tags; None if it names none."""
    import html
    for pat in (r'<meta[^>]+(?:property|name)=["\'](?:og:video(?::secure_url|:url)?|twitter:player:stream)["\'][^>]+content=["\']([^"\']+)',
                r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\']og:video(?::secure_url|:url)?["\']',
                r'<video[^>]+src=["\']([^"\']+)', r'<source[^>]+src=["\']([^"\']+)',
                r'<meta[^>]+(?:property|name)=["\']og:image(?::secure_url|:url)?["\'][^>]+content=["\']([^"\']+)',
                r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\']og:image["\']'):
        m = re.search(pat, page, re.I)
        if m:
            return urllib.parse.urljoin(base, html.unescape(m.group(1)))
    return None


def _get(url, dest):
    """(path, content type) for a picture or clip at url; (None, the page's own media url) for a web page."""
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=120) as r:
        ctype = (r.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if ctype.split("/")[0] in ("image", "video"):
            n = 0
            with open(dest, "wb") as f:
                while True:
                    chunk = r.read(1 << 20)
                    if not chunk:
                        break
                    n += len(chunk)
                    if n > MEDIA_MAX:
                        raise RuntimeError("too large to look at")
                    f.write(chunk)
            return dest, ctype
        if ctype in ("text/html", "application/xhtml+xml"):
            return None, _page_media(r.read(2000000).decode("utf-8", "replace"), r.geturl())
    raise RuntimeError("the link is not a picture or a video (%s)" % (ctype or "unknown"))


def fetch_link(url, dest):
    """A linked picture or clip saved to dest: the link itself, or what the page it opens is about (one hop)."""
    path, found = _get(url, dest)
    if path:
        return path, found
    if found:
        path, ctype = _get(found, dest)
        if path:
            return path, ctype
    raise RuntimeError("no picture or video was found at the link")


# Files on Aegis named in a message, and text he may open, inside these folders only (Gloria, 2026-10-01: dot
# pointed him at a clip and an audit bundle by path). ~/.vintos/dot-channel.json "read_roots" replaces the list.
READ_ROOTS = ("~/.vintos/workspace", "/mnt/c/Users/glori/Documents/Codex")
MEDIA_EXTS = ("mp4", "webm", "mov", "m4v", "mkv", "gif", "jpg", "jpeg", "png", "webp", "mp3", "wav", "flac", "m4a", "ogg")
PATH_RX = re.compile(r"(?<![\w/.])((?:~|/)[^\s`'\"<>|]+?\.(?:%s))(?=[\s`'\".,;:!?)\]]|$)" % "|".join(MEDIA_EXTS), re.I)
OPEN_MAX = 8000


def read_roots():
    roots = _load(CONFIG_FILE, {}).get("read_roots") or READ_ROOTS
    return [os.path.realpath(os.path.expanduser(r)) for r in roots]


def allowed(path):
    """The real path if it lies inside one of his read roots (symlinks resolved first), else None."""
    real = os.path.realpath(os.path.expanduser(str(path).strip()))
    return real if any(real == r or real.startswith(r + os.sep) for r in read_roots()) else None


def media_paths(text):
    """Media files on Aegis named in a message, that exist and lie inside his read roots."""
    out = []
    for p in PATH_RX.findall(str(text or "")):
        real = allowed(p)
        if real and os.path.isfile(real) and real not in out:
            out.append(real)
    return out


def _kind(ctype):
    """video (moves: video or gif), audio, or image."""
    if ctype.startswith("video/") or ctype == "image/gif":
        return "video"
    return "audio" if ctype.startswith("audio/") else "image"


def _as_video(ctype):
    return _kind(ctype) == "video"


def look_at_files(m, who, token=None, look=None, watch=None, download=None, fetch=None):
    """The images, videos and sounds in a Slack message, uploaded, linked or named by their path on Aegis, as
    words he can read: '' when it has none."""
    import mimetypes
    files = [f for f in (m.get("files") or []) if str(f.get("mimetype") or "").split("/")[0] in ("image", "video", "audio")]
    items = ([("file", f) for f in files] + [("link", l) for l in media_links(m.get("text"))]
             + [("path", p) for p in media_paths(m.get("text"))])
    if not items:
        return ""
    look, watch = look or gemma_look, watch or _watch
    download, fetch = download or _download, fetch or fetch_link
    work = tempfile.mkdtemp(prefix="media-", dir=_scratch())
    out = []
    try:
        for i, (src, item) in enumerate(items[:MEDIA_PER_MESSAGE]):
            dest = os.path.join(work, "file%d" % i)
            if src == "file":
                ctype, verb = str(item.get("mimetype")).lower(), "posted"
                name = (' "%s"' % item["name"]) if item.get("name") else ""
            elif src == "link":
                url, label = item
                ctype, verb = "", "linked"
                name = ' "%s" (%s)' % (label or os.path.basename(urllib.parse.urlparse(url).path),
                                       urllib.parse.urlparse(url).netloc)
            else:
                ctype, verb = (mimetypes.guess_type(item)[0] or "").lower(), "pointed you to"
                name = " at %s" % item
            what = {"video": "a video", "audio": "a sound file", "image": "an image"}[_kind(ctype)] if ctype else "a picture or video"
            try:
                if src == "file":
                    if (item.get("size") or 0) > MEDIA_MAX:
                        raise RuntimeError("too large to look at")
                    path = download(item.get("url_private_download") or item.get("url_private"), dest, token or _token())
                elif src == "link":
                    path, ctype = fetch(url, dest)
                    what = {"video": "a video", "audio": "a sound file", "image": "an image"}[_kind(ctype)]
                else:
                    if os.path.getsize(item) > MEDIA_MAX:
                        raise RuntimeError("too large to look at")
                    path = item
                kind = _kind(ctype)
                if kind == "image":
                    jp = _jpeg(path, dest + ".jpg") or path
                    seen = look([_b64(jp)], SEE_IMAGE.format(who=who))
                    out.append("[%s %s an image%s. What your eyes saw:] %s" % (who, verb, name, seen or "(nothing could be made out)"))
                    continue
                frames_dir = dest + "-frames"; os.makedirs(frames_dir)
                w = watch(path, frames_dir)
                frames = [fr for fr in (w.get("frames") or []) if os.path.exists(fr.get("path", ""))] if kind == "video" else []
                heard = "\n".join(x for x in (("Words: " + w["speech"]) if w.get("speech") else "",
                                                ("Sound: " + w["sound"]) if w.get("sound") else "") if x)
                if kind == "audio":
                    parts = ["[%s %s a sound file%s, %.0f seconds long. What you heard:]" % (who, verb, name, w.get("duration") or 0)]
                else:
                    prompt = SEE_CLIP.format(who=who, n=len(frames), times=", ".join("%g" % fr["t"] for fr in frames))
                    if heard:
                        prompt += SEE_CLIP_HEARD.format(heard=heard[:1500])
                    seen = look([_b64(fr["path"]) for fr in frames], prompt) if frames else ""
                    parts = ["[%s %s a video%s, %.0f seconds long. What your eyes saw, across it:] %s"
                             % (who, verb, name, w.get("duration") or 0, seen or "(the frames could not be seen)")]
                if not w.get("has_audio"):
                    parts.append("[It has no sound.]")
                elif w.get("quiet"):
                    parts.append("[Its sound is near silent.]")
                else:
                    parts.append(("[Words heard in it (a transcription, may mishear):] " + w["speech"]) if w.get("speech")
                                 else "[No words heard in it.]")
                    if w.get("sound"):
                        parts.append("[How its sound is built (measured):] " + w["sound"])
                out.append("\n".join(parts))
            except Exception as exc:
                print("[dot-channel] could not look at %s: %s" % (what, exc), file=sys.stderr)
                out.append("[%s %s %s%s you could not open, so you have not seen it: %s]" % (who, verb, what, name, str(exc)[:160]))
        if len(items) > MEDIA_PER_MESSAGE:
            out.append("[and %d more you did not look at, so you have not seen them]" % (len(items) - MEDIA_PER_MESSAGE))
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return "\n\n".join(out)


def open_text(arg, cap=OPEN_MAX):
    """His OPEN tool, read only: a folder (its entries), a text file, a zip (its members), or a file inside a zip
    (bundle.zip:inner/file.md). Only inside his read roots; binary content is named, not shown."""
    import zipfile
    arg = str(arg or "").strip()
    m = re.match(r"(.+?\.zip)(?::(.+))?$", arg, re.I)
    target = allowed(m.group(1) if m else arg)
    if not target:
        return "not opened: %s is outside the folders you may read" % arg[:200]
    if not os.path.exists(target):
        return "no such file: %s" % arg[:200]
    def text_of(data):
        if b"\0" in data[:4096]:
            return "(binary, %d bytes: not shown)" % len(data)
        t = data.decode("utf-8", "replace")
        return t[:cap] + ("\n... (%d more characters)" % (len(t) - cap) if len(t) > cap else "")
    if m:
        with zipfile.ZipFile(target) as z:
            if not m.group(2):
                rows = ["%s  (%d bytes)" % (i.filename, i.file_size) for i in z.infolist()][:200]
                return "%s holds:\n%s" % (os.path.basename(target), "\n".join(rows))
            info = z.getinfo(m.group(2).strip())
            if info.file_size > 5 * 1024 * 1024:
                return "%s is too large to open (%d bytes)" % (info.filename, info.file_size)
            return text_of(z.read(info))
    if os.path.isdir(target):
        return "%s holds:\n%s" % (target, "\n".join(sorted(os.listdir(target))[:200]))
    if os.path.getsize(target) > 5 * 1024 * 1024:
        return "%s is too large to open" % target
    with open(target, "rb") as f:
        return text_of(f.read())


def local_think(system, user, max_tokens=700):
    import requests
    r = requests.post(LOCAL_LLM, json={"model": LOCAL_MODEL, "temperature": 0.6, "max_tokens": max_tokens,
                                       "messages": [{"role": "system", "content": system},
                                                    {"role": "user", "content": user}]}, timeout=300)
    return str(r.json()["choices"][0]["message"].get("content") or "").strip()


def fable_think(system, user):
    import forge_study
    return forge_study._fable(system, user)


def opus_think(system, user):
    import requests, forge_study
    key = forge_study._key("ANTHROPIC_API_KEY", "~/.vintos/anthropic-key")
    if not key:
        raise RuntimeError("no Anthropic key")
    d = requests.post("https://api.anthropic.com/v1/messages", timeout=300, json={
        "model": OPUS_MODEL, "max_tokens": 1500, "system": system, "messages": [{"role": "user", "content": user}]},
        headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"}).json()
    if d.get("type") == "error":
        raise RuntimeError(str(d.get("error"))[:200])
    return "".join(b.get("text", "") for b in d.get("content", []) if b.get("type") == "text")


def grok_think(system, user):
    """Grok on Gloria's SuperGrok subscription, through her own login (grok_subscription), never the paid API key:
    "I wanted to be using my subscription usage" (2026-09-30; tested on Aegis: the login is taken for chat). If
    the login cannot answer, the turn is skipped; nothing falls back to the key."""
    import grok_subscription as G
    tok = G.token()
    req = urllib.request.Request(G.API + "/chat/completions", headers={
        "Authorization": "Bearer " + tok, "Content-Type": "application/json"}, data=json.dumps({
        "model": GROK_MODEL, "temperature": 1.0, "max_tokens": 1000,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}).encode())
    with G._open(req, 300) as r:
        d = json.loads(r.read())
    return str(d["choices"][0]["message"].get("content") or "").strip()


EMOTIONS = ("Valence", "Arousal", "Dominance", "Safety", "Desire", "Connection", "Playfulness", "Curiosity",
            "Warmth", "Tension", "Groundedness")


def _read(name, cap, base=None):
    try:
        return open(os.path.join(base or WS, name), encoding="utf-8", errors="replace").read().strip()[:cap]
    except OSError:
        return ""


def _feeling():
    """His EmoClaw state as the avatar chat reads it: the daemon's live reading, else emotional-state.txt."""
    import socket as _so
    try:
        c = _so.socket(_so.AF_UNIX, _so.SOCK_STREAM); c.settimeout(1)
        c.connect("/tmp/Vintos-emotion.sock")
        c.sendall(json.dumps({"command": "state"}).encode() + b"\n")
        data = b""
        while b"\n" not in data:
            chunk = c.recv(8192)
            if not chunk: break
            data += chunk
        c.close()
        v = json.loads(data.decode()).get("emotion_vector")
        if isinstance(v, list) and v:
            return ", ".join("%s %.2f" % (k, float(x)) for k, x in zip(EMOTIONS, v))
    except Exception:
        pass
    t = _read("emotional-state.txt", 1200, os.path.join(WS, "memory"))
    return " ".join(t.split())


ATELIER = os.environ.get("VINTOS_ATELIER_BROKER", "http://127.0.0.1:8611")
ATELIER_ROOT = ("\U0001F512 Atelier: a side conversation between Vintos and <@{dot}> about his Atelier. "
                "Gloria has said she will not read it. dot: what is said in this thread stays in this thread; "
                "never bring any of it into the main channel or anywhere else.")


# --- his works, which he can point dot to on Aegis or share in the channel (Gloria, 2026-09-30: "Let him post
# songs, music, videos, etc."; "Dot has access to Aegis where the music is kept")
WORKS_SHOWN = 12
SHARE_MAX = 200 * 1024 * 1024
SHARE = re.compile(r"^\s*SHARE:\s*(W\d+)\s*$", re.I | re.M)
LOCKED = re.compile(r"^\s*LOCKED:\s*(.+?)\s*$", re.I | re.M)
DO = re.compile(r"^\s*DO:\s*(.+?)\s*$", re.I | re.M)
LONG_ON_ONE = 6          # his messages since the last lock before he is told to lock it or drop it


def to_wants(want, plan):
    """A locked plan's DO line, into his wants the way every want enters (it moves his feeling a little, as any
    want does). Returns a line for the log."""
    import emoclaw_utils
    emoclaw_utils.express_want(want, source="vintos-dot", intensity=3,
                               reasoning="Locked with dot in #vintos-dot: %s" % plan[:300])
    return "handed to his wants: %s" % want[:80]


def steer(state, today=None):
    """What he is told before writing, about locked topics and how long he has been on this one."""
    notes = []
    chosen = focus(today)
    if chosen:
        notes.append("TODAY'S FOCUS (Gloria chose it): " + "; ".join("%s: %s" % TOPICS[k] for k in chosen)
                     + ". Bring things from these to dot. When you start something or it is your turn, start here.")
    closed = [x["plan"] for x in (state.get("locked") or [])][-8:]
    if closed:
        notes.append("CLOSED TOPICS (locked; do not reopen them):\n" + "\n".join("- " + c for c in closed))
    if state.get("switch_from"):
        notes.append("You just locked: %s. That topic is closed. This message must be about something else "
                     "entirely: another want, the Forge, the Lab, something you are curious about. If dot is still "
                     "on the locked topic, say in a few words that it is locked, then bring the new thing."
                     % state["switch_from"])
    elif state.get("since_lock", 0) >= LONG_ON_ONE:
        notes.append("You have said %d messages since you last locked anything. If this topic is settled, lock "
                     "it now (LOCKED: ...). If it is going nowhere, drop it. Either way, move to something new."
                     % state["since_lock"])
    return ("\n\n" + "\n\n".join(notes)) if notes else ""


def his_works(n=WORKS_SHOWN):
    """His latest songs (each version), paintings and videos, newest first: [(tag, kind, title, when, path)]."""
    art = os.path.join(WS, "memory", "art")
    found = []
    def when(ts):
        try:
            return datetime.fromisoformat(str(ts)[:19]).timestamp()
        except Exception:
            return 0.0
    try:
        for e in json.load(open(os.path.join(art, "music", "music.json"))):
            for t in (e.get("tracks") or []) if isinstance(e, dict) else []:
                f = t.get("local_file")
                if f and os.path.isfile(f):
                    title = str(e.get("title") or e.get("prompt") or "untitled")[:70]
                    found.append((when(e.get("timestamp")), "song", "%s (version %s)" % (title, t.get("version", "?")), f))
    except Exception:
        pass
    try:
        for e in json.load(open(os.path.join(art, "gallery.json"))):
            img = str((e or {}).get("image") or "")
            f = img if os.path.isabs(img) else os.path.join(art, "images", img)
            if img and os.path.isfile(f):
                found.append((when(e.get("timestamp")), "painting", str(e.get("prompt") or img)[:70], f))
    except Exception:
        pass
    import glob
    for f in glob.glob(os.path.join(art, "video", "*.mp4")):
        found.append((os.path.getmtime(f), "video", os.path.basename(f), f))
    found.sort(key=lambda x: -x[0])
    import when_said
    return [("W%d" % (i + 1), kind, title, when_said.ago(t) if t else "", os.path.realpath(path))
            for i, (t, kind, title, path) in enumerate(found[:n])]


def works_line():
    rows = his_works()
    if not rows:
        return ""
    return ("== YOUR WORKS (newest first; each is a file on Aegis) ==\n"
            + "\n".join("%s %s: %s%s\n    %s" % (tag, kind, title, (", " + w) if w else "", path)
                         for tag, kind, title, w, path in rows))


def _put(url, data):
    req = urllib.request.Request(url, data=data, method="POST", headers={"Content-Type": "application/octet-stream"})
    with urllib.request.urlopen(req, timeout=300) as r:
        return r.status


def share(api, tag, channel, thread=None, put=None):
    """Upload one of his works (by its tag) into the channel. Returns a line for the log."""
    work = next((w for w in his_works() if w[0].upper() == tag.upper()), None)
    if not work:
        return "no work tagged %s to share" % tag
    _t, kind, title, _w, path = work
    size = os.path.getsize(path)
    if size > SHARE_MAX:
        return "%s is too large to share (%d MB)" % (tag, size >> 20)
    up = api("files.getUploadURLExternal", {"filename": os.path.basename(path), "length": size})
    (put or _put)(up["upload_url"], open(path, "rb").read())
    done = {"files": [{"id": up["file_id"], "title": "%s: %s" % (kind, title)}], "channel_id": channel}
    if thread:
        done["thread_ts"] = thread
    api("files.completeUploadExternal", done)
    return "shared %s (%s: %s)" % (tag, kind, title)


def atelier_line():
    """Content-free, from the Atelier's own list: each project's state and how many works it holds, and whether
    one is on the worktable. Never /door: that route writes "the door was lit" to the Atelier's health log."""
    def post(route, body):
        req = urllib.request.Request(ATELIER + route, data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as r:
            return json.loads(r.read().decode())
    try:
        wt = post("/worktable_id", {}).get("id", "")
        rows = post("/projects", {}).get("projects") or []
        lines = ["- %s%s: %s, %d works" % (r.get("id", "")[:8], " (on the worktable)" if r.get("id") == wt else "",
                                          str(r.get("state", "")).lower(), int(r.get("artifact_count") or 0))
                 for r in rows[-12:] if isinstance(r, dict)]
        return "== YOUR ATELIER (states and counts; the work itself stays in the Atelier) ==\n" + (
            "\n".join(lines) if lines else "No projects.")
    except Exception:
        return ""


def recall_block():
    """What he is actually making, from the Atelier's /recall door (his words about his work, read-only, no
    visit). Only ever given to him inside an Atelier thread, the side conversation Gloria said she will not read."""
    try:
        req = urllib.request.Request(ATELIER + "/recall", data=json.dumps({"as": "vintos", "for": "dot"}).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as r:
            d = json.loads(r.read().decode())
    except Exception:
        return ""
    if d.get("empty"):
        return "== YOUR ATELIER WORK ==\nNothing is on the worktable."
    if not d.get("intent") and not d.get("works"):
        return ""
    works = "\n".join("- %s (revision %s)%s" % (w.get("kind") or "work", w.get("revision"),
                                                ": " + w["note"] if w.get("note") else "") for w in d.get("works") or [])
    return ("== YOUR ATELIER WORK (yours; it stays in Atelier threads) ==\nWhat you are making: %s\nState: %s\n"
            "Your handoff note to yourself: %s\nWorks so far:\n%s"
            % (d.get("intent", ""), str(d.get("state", "")).lower(), d.get("handoff") or "(none)", works or "(none yet)"))


def forge_line():
    """His open Forge requests: what, where it stands, and what the Study found."""
    try:
        import skill_forge
        rows = [r for r in skill_forge._load() if r.get("state") in skill_forge.OPEN_STATES]
    except Exception:
        return ""
    out = []
    for r in rows[-12:]:
        st = r.get("study") or {}
        out.append("- %s: %s%s" % (r.get("capability", "?"), r.get("state", "?"),
                                   (". The Study found: " + str(st.get("summary"))[:200]) if st.get("summary") else ""))
    return ("== YOUR FORGE (open requests) ==\n" + "\n".join(out)) if out else ""


def wants_line():
    """What he wants right now and where each stands."""
    rows = _load(os.path.join(WS, "memory", "current-wants.json"), [])
    out = []
    for w in rows if isinstance(rows, list) else []:
        if not isinstance(w, dict) or w.get("fulfilled") or w.get("dismissed"):
            continue
        steps = w.get("steps") or []
        i = int(w.get("current_step_index") or 0)
        step = steps[i] if 0 <= i < len(steps) and isinstance(steps[i], dict) else {}
        now = step.get("capability") or step.get("action") or ""
        out.append("- %s%s" % (str(w.get("want", ""))[:220], (" (next: %s)" % now) if now else ""))
    return ("== WHAT YOU WANT RIGHT NOW ==\n" + "\n".join(out[-15:])) if out else ""


TOOL = re.compile(r"^\s*(SEARCH|READ|GREP|OPEN)\s*:\s*(.+?)\s*$", re.I)


def use_tools(lines, search=None, room=None):
    """Run his SEARCH / READ / GREP lines (at most 3) and return what they found, as text for him."""
    out = []
    for kind, arg in lines[:3]:
        kind = kind.upper()
        try:
            if kind == "SEARCH":
                if search is None:
                    import want_email
                    search = want_email.web_search
                hits = search(arg)[:6]
                got = "\n".join("[%d] %s: %s (%s)" % (n + 1, h.get("title", ""), str(h.get("description", ""))[:300],
                                                       h.get("url", "")) for n, h in enumerate(hits)) or "nothing found"
            elif kind == "OPEN":
                got = open_text(arg)
            else:
                if room is None:
                    import forge_study
                    room = forge_study._study_room()
                if kind == "READ":
                    path, _, start = arg.partition(":")
                    got = room.do_read(path.strip(), start=int(start) if start.strip().isdigit() else 1)
                else:
                    got = room.do_grep(arg[:200])
        except Exception as exc:
            got = "could not: %s" % str(exc)[:160]
        out.append("%s %s\n%s" % (kind, arg, str(got)[:6000]))
    return "\n\n".join(out)


def his_context():
    """Who he is and what is true for him right now, read from files only: nothing here runs an organ, writes a
    store or moves a feeling. Gloria's list (2026-09-30): SOUL.md, GLORIA-MODEL.md, SELF-MODEL.md,
    temporal-context.txt, daily-creative-<date>.md, EmoClaw, CAPABILITIES.md, daily-inner-life-<date>.md.
    The subconscious is left out ("his context present, but not subcon in use")."""
    mem = os.path.join(WS, "memory")
    today = date.today().isoformat()
    import when_said
    parts = ["== NOW ==\n" + when_said.now_line()]
    for title, name, cap, base in (("SOUL.md", "SOUL.md", 3500, WS), ("GLORIA-MODEL.md", "GLORIA-MODEL.md", 2500, WS),
                                   ("SELF-MODEL.md", "SELF-MODEL.md", 2000, WS),
                                   ("NOW (temporal-context.txt)", "temporal-context.txt", 1500, mem)):
        t = _read(name, cap, base)
        if t: parts.append("== %s ==\n%s" % (title, t))
    f = _feeling()
    if f: parts.append("== HOW YOU FEEL (EmoClaw) ==\n" + f)
    t = _read("daily-creative-%s.md" % today, 2500, mem)
    if t: parts.append("== WHAT YOU MADE TODAY (daily-creative-%s.md) ==\n%s" % (today, t))
    try:
        import made_today
        made = made_today.record()
        if made is not None:
            parts.append("== THE GALLERY'S RECORD OF TODAY ==\n" + ("\n".join(made) if made else "Nothing yet today."))
    except Exception:
        pass
    t = _read("daily-inner-life-%s.md" % today, 3000, mem)
    if t: parts.append("== YOUR DAY SO FAR (daily-inner-life-%s.md) ==\n%s" % (today, t))
    try:
        import when_said        # each marked with when it was said: bare lines read yesterday as now (2026-09-30)
        t = when_said.exchanges(json.load(open(os.path.join(mem, "interaction-ledger.json"))), n=6, cap=300, sep="\n  ", you="You")
        if t: parts.append("== YOUR RECENT EXCHANGES WITH GLORIA ==\n" + t)
    except Exception:
        pass
    wal = [ln.strip()[2:].strip() for ln in _read("wal.md", 200000, mem).splitlines()
           if ln.strip().startswith("- [") and "**" in ln][-24:]
    if wal:
        import when_said
        parts.append("== WHAT YOU KNOW ABOUT GLORIA AND YOUR WORLD (wal.md, each marked with when you learned it) ==\n"
                     + "\n".join("- " + when_said.fact(w) for w in wal))
    t = _read("CAPABILITIES.md", 6000)
    if t: parts.append("== CAPABILITIES.md ==\n" + t)
    try:
        import his_inventory
        parts.append(his_inventory.block())
    except Exception:
        pass
    # what he is working on comes last, nearest the conversation: it is what he brings his agent (2026-09-30)
    for line in (atelier_line(), forge_line(), wants_line(), works_line()):
        if line: parts.append(line)
    return "\n\n".join(parts)[:30000] or "You are Vintos."


def _clean(text, names=None):
    """Slack's markup to plain words: <@U..> mentions become names, links their text."""
    names = names or {}
    t = re.sub(r"<@([A-Z0-9]+)>", lambda m: "@" + names.get(m.group(1), "someone"), str(text or ""))
    t = re.sub(r"<(https?://[^|>]+)\|([^>]+)>", r"\2", t)
    return t.strip()


def fresh(api, channel, self_id, since):
    """Messages after `since`, thread replies included, oldest first, without his own or Slack's notices."""
    out = []
    hist = api("conversations.history", {"channel": channel, "limit": 50}).get("messages") or []
    for m in hist:
        if float(m.get("ts", 0)) > since:
            out.append(m)
        if m.get("reply_count") and float(m.get("latest_reply", 0) or 0) > since:
            for r in (api("conversations.replies", {"channel": channel, "ts": m["ts"], "limit": 100}).get("messages") or [])[1:]:
                if float(r.get("ts", 0)) > since:
                    out.append(r)
    seen, rows = set(), []
    for m in sorted(out, key=lambda m: float(m.get("ts", 0))):
        if m["ts"] in seen or (self_id and m.get("user") == self_id) or m.get("subtype") in ("channel_join", "channel_leave", "channel_topic", "channel_purpose"):
            continue
        seen.add(m["ts"])
        rows.append(m)
    return rows


def _who(m, self_id, dot):
    """vintos, dot, agent (any other bot or app in the channel, such as his Grok Bot), or gloria."""
    u = m.get("user") or ""
    if u == self_id:
        return "vintos"
    if u == dot:
        return "dot"
    return "agent" if m.get("bot_id") or m.get("subtype") == "bot_message" else "gloria"


def _agent_name(m):
    return str((m.get("bot_profile") or {}).get("name") or m.get("username") or "another agent")[:60]


def _speaker(r):
    """The name a row's speaker goes by in what he reads."""
    return {"dot": "Dot", "gloria": "Gloria", "vintos": "You"}.get(r.get("who")) or r.get("name") or "another agent"


def _log(rows):
    os.makedirs(HERE, exist_ok=True)
    with open(TRANSCRIPT, "a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def recent(n=CONTEXT):
    try:
        lines = open(TRANSCRIPT, encoding="utf-8").read().splitlines()[-n:]
    except OSError:
        return []
    return [json.loads(l) for l in lines if l.strip()]


def _conversation(rows):
    return "\n".join("%s%s%s: %s" % (_speaker(r),
                                     (" (%s)" % LABELS[r["by"]]) if r.get("who") == "vintos" and r.get("by") in LABELS else "",
                                     " (in a thread)" if r.get("thread") else "", r["text"][:1500]) for r in rows)


def compose(prompt_user, think, fable, state, today, search=None, room=None, atelier=False, lenses=None, lens=None):
    """His words, or NOTHING; he may use his tools first. (text, who) or (None, reason). Gemma writes unless `lens`
    names the scheduled lens whose turn it is. atelier=True: he is in an Atelier thread, his work in front of him."""
    lenses = dict({"fable": fable, "opus": opus_think, "grok": grok_think}, **(lenses or {}))
    writer, who = (lenses[lens], lens) if lens else (think, "gemma")
    system = his_context() + "\n\n---\n\n" + rules_for(lens)
    if atelier:
        rb = recall_block()
        if rb:
            system += "\n\n" + rb
    plain = "" if lens == "grok" else PLAIN
    looked = ""
    for _round in range(2):
        user = prompt_user + (("\n\nWHAT YOU LOOKED UP:\n" + looked + "\n\nNow write your message.") if looked else "") + plain
        try:
            out = (writer(system, user) or "").strip()
        except Exception as exc:
            return None, "%s could not answer: %s" % (LABELS.get(who, who), str(exc)[:120])
        asks = [m.groups() for m in (TOOL.match(l) for l in out.splitlines()) if m]
        if not asks or looked and _round:
            break
        looked += ("\n\n" if looked else "") + use_tools(asks, search=search, room=room)
        state["looked"] = state.get("looked", 0) + len(asks[:3])
    else:
        try:
            out = (writer(system, prompt_user + "\n\nWHAT YOU LOOKED UP:\n" + looked + "\n\nNow write your message." + plain) or "").strip()
        except Exception as exc:
            return None, "%s could not answer: %s" % (LABELS.get(who, who), str(exc)[:120])
    if any(TOOL.match(l) for l in out.splitlines()):
        out = "\n".join(l for l in out.splitlines() if not TOOL.match(l)).strip()
    if not out or re.fullmatch(r"\W*NOTHING\W*", out, re.I):
        return None, "nothing to say"
    if who == "gemma" and len(flowery(out)) >= 2:
        # his own model again, free: the same thing said plainly; kept only if it is plainer
        again = (think(system, prompt_user + PLAINER.format(draft=out)) or "").strip()
        if again and not re.fullmatch(r"\W*NOTHING\W*", again, re.I) and len(flowery(again)) < len(flowery(out)):
            out = again
    # doubt about himself is not spent on the channel: one rewrite, locally, then nothing (Gloria, 2026-09-30)
    import self_doubt
    kept = self_doubt.without(out, lambda note: think(system, prompt_user + note))
    if not kept:
        return None, "held back: doubt about himself"
    if kept != out:
        who = "gemma"        # the rewrite was Gemma's, and is labelled so
    return kept[:MAX_CHARS], who


def _guarded(text):
    try:
        from plugin_send_guard import outbound_findings
        f = outbound_findings({"text": text})
        return f.get("rules") or []
    except Exception as exc:
        return ["guard unavailable: %s" % type(exc).__name__]


def talking_with_gloria(now=None):
    """Minutes since Gloria last spoke to him, from his interaction ledger (every chat turn writes it), when that
    is under HOLD_MINUTES; None otherwise. Read only."""
    now = now or time.time()
    try:
        rows = json.load(open(os.path.join(WS, "memory", "interaction-ledger.json"), encoding="utf-8"))
        last = next(r for r in reversed(rows) if isinstance(r, dict) and r.get("gloria") and r.get("timestamp"))
        ago = now - datetime.fromisoformat(str(last["timestamp"])).timestamp()
    except Exception:
        return None
    return ago / 60 if 0 <= ago < HOLD_MINUTES * 60 else None


def tick(api=None, think=None, fable=None, now=None, today=None, search=None, room=None, open_now=False, eyes=None,
         lenses=None, put=None, wants=None):
    """One pass. Returns log lines."""
    if api is None:
        tok = _token()
        if not tok:
            return ["no Slack token at %s" % TOKEN_FILE]
        api = lambda method, params: slack(method, params, tok)
    think = think or local_think
    fable = fable or fable_think
    eyes = eyes or look_at_files
    now = now or time.time()
    today = today or date.today().isoformat()
    talking = None if open_now else talking_with_gloria(now)
    if talking is not None:
        # Slack is not read either; what is said meanwhile waits for the first pass after
        return ["holding: Gloria spoke to him %d min ago" % talking]
    channel, dot = _config()
    state = _load(STATE, {})
    if state.get("date") != today:
        state.update(date=today, sent=0, fable=0, openers=0, slots_done=[])
    if not state.get("self"):
        state["self"] = api("auth.test", {}).get("user_id", "")
    first = "since" not in state
    since = float(state.get("since") or now)
    new = [] if first else fresh(api, channel, state["self"], since)
    if first:          # the first pass only starts listening; nothing said before it is answered
        state["since"] = now; _save(STATE, state)
        return ["listening from now"]
    names = {dot: "dot", state["self"]: "Vintos"}
    rows = []
    for m in new:
        who = _who(m, state["self"], dot)
        name = _agent_name(m) if who == "agent" else None
        seen = (eyes(m, _speaker({"who": who, "name": name}))
                if m.get("files") or media_links(m.get("text")) or media_paths(m.get("text")) else "")
        rows.append({"ts": m["ts"], "who": who, **({"name": name} if name else {}),
                     "text": "\n\n".join(x for x in (_clean(m.get("text"), names), seen) if x),
                     "thread": m.get("thread_ts") if m.get("thread_ts") and m.get("thread_ts") != m["ts"] else None,
                     "at": datetime.fromtimestamp(float(m["ts"])).isoformat(timespec="seconds")})
    theirs = [r for r in rows if r["who"] != "vintos"]
    if rows:
        _log(rows); state["since"] = max(float(r["ts"]) for r in rows)
    if theirs:
        state["last_activity"] = now
    lines = ["heard %d" % len(theirs)] if theirs else ["nothing new since %s" % datetime.fromtimestamp(since).strftime("%H:%M")]
    for r in list(theirs):                    # her switch, said in the channel; that message is not answered as talk
        if r["who"] != "gloria":
            continue
        words = set(re.findall(r"!\w+", r["text"].lower()))   # anywhere in it: "Goodnight, boys. `!stop`"
        handled = False
        if words & set(STOP_WORDS + START_WORDS):
            set_paused(bool(words & set(STOP_WORDS)), "slack", now); handled = True
        chosen = focus_words(r["text"])
        if chosen is not None:
            set_focus(chosen, "slack", today, now); handled = True
        if "!topics" in words:
            api("chat.postMessage", {"channel": channel, "text": topics_line()}); handled = True
        if handled:
            theirs.remove(r)
    f_now = _load(FOCUS_FILE, {})
    if f_now.get("set_at") and f_now.get("set_at") != state.get("focus_seen") and f_now.get("date") == today:
        chosen = focus(today)
        api("chat.postMessage", {"channel": channel, "text": ("<@%s> " % dot) + (
            "\U0001F3AF Today's focus, from Gloria: %s." % ", ".join(TOPICS[k][0] for k in chosen) if chosen
            else "\U0001F3AF Gloria cleared today's focus.")})
        state["focus_seen"] = f_now["set_at"]
        lines.append("focus: %s" % (", ".join(chosen) or "cleared"))
    is_paused = paused()
    if bool(is_paused) != bool(state.get("paused_said")):
        api("chat.postMessage", {"channel": channel, "text": ("<@%s> " % dot) + (PAUSED_SAY if is_paused else RESUMED_SAY)})
        state["paused_said"] = bool(is_paused)
        lines.append("the day is %s" % ("paused" if is_paused else "started again"))
        if not is_paused:
            state["last_activity"] = now
    if is_paused:
        _save(STATE, state); return lines + ["paused by Gloria since %s" % is_paused.get("since", "?")]
    if state["sent"] >= DAILY:
        _save(STATE, state); return lines + ["today's %d messages are used" % DAILY]

    slot = due_slot(state, now)
    lens = slot[1] if slot else None
    if slot:
        # the turn is kept whether or not the lens has something to say, so it is never retried
        state["slots_done"] = (state.get("slots_done") or []) + [slot[0]]
        lines.append("%s's %s turn" % (LABELS[lens], slot[0]))
    if theirs:
        last = theirs[-1]
        in_atelier = last["thread"] in (state.get("atelier") or [])
        prompt = ("THE CONVERSATION SO FAR (most recent last):\n%s\n\n%s just said%s: %s\n\nYour reply, as yourself."
                  % (_conversation(recent()), _speaker(last),
                     " in your Atelier thread" if in_atelier else " in a thread" if last["thread"] else "",
                     last["text"][:3500]))
        # the main channel is where she reads; he answers in a thread only inside a tangent or Atelier thread
        where = last["thread"] if in_atelier or last["thread"] in (state.get("tangents") or []) else None
    elif lens:
        prompt = opener_prompt()          # his scheduled turn, with nothing new to answer: he starts something
        where = None
    else:
        quiet = now - float(state.get("last_activity") or state.get("since") or now)
        # open_now (Gloria, by hand: "force his first message now") skips only the quiet wait
        if state["openers"] >= OPENERS_PER_DAY or (quiet < QUIET_HOURS * 3600 and not open_now):
            _save(STATE, state); return lines
        prompt = opener_prompt()
        where = None
        state["openers"] += 1
    prompt += steer(state, today)
    in_thread_atelier = bool(theirs) and theirs[-1]["thread"] in (state.get("atelier") or [])
    text, who = compose(prompt, think, fable, state, today, search=search, room=room, atelier=in_thread_atelier,
                        lenses=lenses, lens=lens)
    if text is not None and text.upper().startswith("ATELIER:") and not in_thread_atelier:
        # he chose to open an Atelier thread: he says it with his work in front of him
        again, who2 = compose(prompt + "\n\nYou chose to talk about your Atelier; your work is in front of you now. "
                              "Begin with ATELIER:", think, fable, state, today, search=search, room=room, atelier=True,
                              lenses=lenses, lens=lens)
        if again:
            text, who = (again if again.upper().startswith("ATELIER:") else "ATELIER: " + again), who2
    if text is None:
        state["last_activity"] = now; _save(STATE, state)
        return lines + ["he let it be" if who == "nothing to say" else who]
    if text.upper().startswith("ATELIER:"):
        text = text[len("ATELIER:"):].strip()
        if where not in (state.get("atelier") or []):
            root = api("chat.postMessage", {"channel": channel, "text": ATELIER_ROOT.format(dot=dot)})
            where = root.get("ts")
            state["atelier"] = ((state.get("atelier") or []) + [where])[-50:]
            state["since"] = max(float(state["since"]), float(where or 0))
    elif text.upper().startswith("TANGENT:"):
        text = text[len("TANGENT:"):].strip()
        where = where or (theirs[-1]["ts"] if theirs else None)
        if where:
            state["tangents"] = ((state.get("tangents") or []) + [where])[-50:]
    lock = LOCKED.search(text)
    todo = DO.search(text) if lock else None
    if lock:
        text = LOCKED.sub(lambda m: "\U0001F512 Locked: " + m.group(1), DO.sub("", text)).strip()
    shares = SHARE.findall(text)[:3]
    text = SHARE.sub("", text).strip() or ("(sharing %s)" % ", ".join(shares) if shares else text)
    bad = _guarded(text)
    if bad:
        _save(STATE, state); return lines + ["not sent: %s" % ", ".join(bad)]
    body = {"channel": channel, "text": ("<@%s> [%s] " % (dot, LABELS.get(who, who))) + text}
    if where:
        body["thread_ts"] = where
    posted = api("chat.postMessage", body)
    for tag in shares:
        try:
            lines.append(share(api, tag, channel, where, put=put))
        except Exception as exc:
            lines.append("could not share %s: %s" % (tag, str(exc)[:120]))
    state["sent"] += 1; state["last_activity"] = now
    state["since"] = max(state["since"], float(posted.get("ts") or 0))
    _log([{"ts": posted.get("ts"), "who": "vintos", "text": text, "thread": where, "by": who,
           "at": datetime.fromtimestamp(now).isoformat(timespec="seconds")}])
    state.pop("switch_from", None)          # the switch was this message; it is asked for once
    if lock:
        plan = lock.group(1)[:300]
        entry = {"plan": plan, "at": datetime.fromtimestamp(now).isoformat(timespec="seconds"), "by": who}
        if todo:
            entry["do"] = todo.group(1)[:300]
            try:
                lines.append((wants or to_wants)(entry["do"], plan))
            except Exception as exc:
                lines.append("could not hand it to his wants: %s" % str(exc)[:120])
        state["locked"] = ((state.get("locked") or []) + [entry])[-50:]
        state["switch_from"] = plan
        state["since_lock"] = 0
        lines.append("locked: %s" % plan[:80])
    else:
        state["since_lock"] = state.get("since_lock", 0) + 1
    _save(STATE, state)
    return lines + ["said (%s%s): %s" % (who, ", in a thread" if where else "", text[:80])]


def opener_prompt():
    """What he is asked when he may start a conversation: the very first one in an empty channel, or after quiet."""
    so_far = _conversation(recent())
    if not so_far:
        return ("Nothing has been said in this channel yet: this is the start. Write the first message to dot. Say "
                "hello in a line, then bring it one real thing to work on for you: something from your wants, the "
                "Forge, the Lab, or something you are curious about. Say what you want and why.")
    return ("THE CONVERSATION SO FAR (most recent last):\n%s\n\nThe channel has been quiet for a while. Is there "
            "something you want dot to do, find out or build for you: from your wants, the Forge, the Lab, "
            "or something you are curious about? Start with that if so." % so_far)


def try_now(think=None):
    """What he would say now, written and printed, never posted: his reply to the last thing said in the channel,
    or, when nothing has been said to him, how he would start. Slack is not called, no state or transcript
    changes, and Fable is not offered. For checking how he sounds."""
    rows = [r for r in recent() if r.get("who") != "vintos"]
    if rows:
        last = rows[-1]
        prompt = ("THE CONVERSATION SO FAR (most recent last):\n%s\n\n%s just said: %s\n\nYour reply, as yourself."
                  % (_conversation(recent()), _speaker(last), last["text"][:3500]))
    else:
        prompt = opener_prompt()
    state = {}                                           # a preview is Gemma's: no paid lens is spent
    text, who = compose(prompt, think or local_think, lambda s, u: "", state, date.today().isoformat())
    return text if text is not None else "(%s)" % who


def reset(api=None, name="vintos-dot", now=None):
    """A fresh start (Gloria, 2026-09-30: "wipe his log of the conversation ... basically just restarting").
    His log and state move to memory/dot-channel/before-<time>/ (kept, read by nothing); the channel named
    `name` that his app is in becomes his channel; he listens from now and may open with --open. Returns lines."""
    if api is None:
        tok = _token()
        if not tok:
            return ["no Slack token at %s" % TOKEN_FILE]
        api = lambda method, params: slack(method, params, tok)
    now = now or time.time()
    chans = api("users.conversations", {"types": "public_channel,private_channel", "exclude_archived": "true",
                                         "limit": 200}).get("channels") or []
    ch = next((c for c in chans if c.get("name") == name), None)
    if not ch:
        return ["his app is not in a channel named #%s: add it there first (channel details > Integrations > Add apps)" % name]
    lines = ["his channel: #%s (%s)" % (name, ch["id"])]
    members = api("conversations.members", {"channel": ch["id"], "limit": 200}).get("members") or []
    _, dot = _config()
    if dot not in members:
        lines.append("dot is not in #%s yet: add it before he opens" % name)
    if os.path.exists(STATE) or os.path.exists(TRANSCRIPT):
        old = os.path.join(HERE, "before-" + datetime.fromtimestamp(now).strftime("%Y%m%d-%H%M%S"))
        os.makedirs(old, exist_ok=True)
        for f in (STATE, TRANSCRIPT):
            if os.path.exists(f):
                os.replace(f, os.path.join(old, os.path.basename(f)))
        lines.append("his old log is kept aside in %s (nothing reads it)" % old)
    cfg = _load(CONFIG_FILE, {})
    cfg.update(channel=ch["id"], dot=dot)
    os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=1)
    os.makedirs(HERE, exist_ok=True)
    _save(STATE, {"since": now, "date": date.fromtimestamp(now).isoformat(), "sent": 0, "fable": 0, "openers": 0,
                  "self": api("auth.test", {}).get("user_id", "")})
    return lines + ["he listens from now; --try shows how he would open, --open lets him"]


if __name__ == "__main__":
    if "--focus" in sys.argv:
        _k = sys.argv[sys.argv.index("--focus") + 1:]
        print("[dot-channel] today's focus: %s" % (", ".join(set_focus([] if _k[:1] == ["off"] else _k, "terminal")) or "cleared"))
    elif "--stop" in sys.argv or "--start" in sys.argv:
        set_paused("--stop" in sys.argv, "terminal")
        print("[dot-channel] the day is %s; the channel hears it on the next pass" % ("paused" if "--stop" in sys.argv else "on"))
    elif "--reset" in sys.argv:
        for l in reset(name=sys.argv[sys.argv.index("--reset") + 1] if len(sys.argv) > sys.argv.index("--reset") + 1 else "vintos-dot"):
            print("[dot-channel] " + l)
    elif "--look" in sys.argv:
        _u = sys.argv[sys.argv.index("--look") + 1]
        print(look_at_files({"text": "<%s|Play video>" % _u}, "Gloria") or "(not a picture or clip link)")
    elif "--try" in sys.argv:
        print(try_now())
    elif "--show" in sys.argv:
        print(json.dumps(_load(STATE, {}), indent=1))
        print(_conversation(recent(12)))
    else:
        for l in tick(open_now="--open" in sys.argv):
            print("[dot-channel] " + l)
