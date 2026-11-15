#!/usr/bin/env python3
"""paper_print.py — her Epson XP-7100: one of his paintings as a photo, or a page of his words.

Gloria, 14 November: "Let's let him use the normal printer too." The printer takes encrypted IPP (ipps, port 631)
and JPEG / raster images, not PDF; so a painting goes as itself and a page of words is drawn first (Pillow).

    PAPER: <anything>                      whatever he names (Gloria, 14 November: "print whatever"):
                                             one of his files by name or path (an image as a photo, a text file
                                             as pages), one of his works found by what is in it, or else his
                                             words themselves as a page. "as photo" / "as page" picks the size.
    PAPER: painting <words> | page <words>  the same, said outright

Like the K2 (print_lane.py), nothing prints without her Yes on her phone: the paper and the ink are hers. The ask
names what, the size and the paper. If the printer is out of paper or not taking jobs, her Yes waits (two days at
most). Two a day; one at a time. The printer's address lives in memory/paper-printer.json, not here.

    python3 paper_print.py              the printer now: state, paper, ink
    python3 paper_print.py tend         moves jobs whose answer came
"""
import json
import os
import re
import secrets
import ssl
import struct
import subprocess
import sys
import urllib.request
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
WS = os.environ.get("SPARK_WORKSPACE") or os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WS, "memory")
CONFIG = os.path.join(MEMORY, "paper-printer.json")
JOBS = os.path.join(MEMORY, "paper-print-jobs.json")
WORK = os.path.join(MEMORY, "paper-print")
ART = os.path.join(MEMORY, "art")
PER_DAY = 2
WAIT_H = 48
LIVE = ("asked", "held")
MAX_PAGES = 10
TEXT_EXT = (".md", ".txt", ".json", ".jsonl", ".csv", ".log")
IMAGE_EXT = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp")
SIZES = {"photo": ("na_index-4x6_4x6in", (1200, 1800)), "page": ("na_letter_8.5x11in", (2550, 3300))}
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"


def _now():
    return datetime.now().astimezone()


def _iso():
    return _now().isoformat(timespec="seconds")


def _cfg():
    try:
        return json.load(open(CONFIG))
    except Exception:
        return {}


# ------------------------------------------------------------------ IPP (the printer's own protocol)

def _attr(tag, name, value):
    v = value if isinstance(value, bytes) else str(value).encode()
    return struct.pack(">BH", tag, len(name)) + name.encode() + struct.pack(">H", len(v)) + v


def _ipp(op, attrs, job_attrs=b"", document=b"", post=None):
    host = str(_cfg().get("host") or "")
    if not host:
        raise RuntimeError("no printer address in memory/paper-printer.json")
    uri = "ipps://%s/ipp/print" % host
    body = (struct.pack(">BBHI", 2, 0, op, 1) + b"\x01" + _attr(0x47, "attributes-charset", "utf-8")
            + _attr(0x48, "attributes-natural-language", "en") + _attr(0x45, "printer-uri", uri) + attrs
            + ((b"\x02" + job_attrs) if job_attrs else b"") + b"\x03" + document)
    if post:
        return post(body)
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE        # a printer on her own network, with its own self-made certificate
    req = urllib.request.Request("https://%s:631/ipp/print" % host, data=body, headers={"Content-Type": "application/ipp"})
    with urllib.request.urlopen(req, timeout=60, context=ctx) as r:
        return r.read()


def _parse(data):
    status = struct.unpack(">H", data[2:4])[0]
    i, name, out = 9, "", {}
    while i < len(data):
        tag = data[i]; i += 1
        if tag == 0x03:
            break
        if tag < 0x10:
            continue
        nl = struct.unpack(">H", data[i:i + 2])[0]; i += 2
        n = data[i:i + nl].decode(errors="replace"); i += nl
        vl = struct.unpack(">H", data[i:i + 2])[0]; i += 2
        v = data[i:i + vl]; i += vl
        if n:
            name = n
        if tag in (0x21, 0x23):
            val = struct.unpack(">i", v)[0] if len(v) == 4 else 0
        elif tag == 0x22:
            val = bool(v and v[0])
        else:
            val = v.decode(errors="replace")
        out.setdefault(name, []).append(val)
    return status, out


def status(post=None):
    """{reachable, accepting, state, reasons, ink: {name: %}} or {reachable: False, why}."""
    try:
        st, a = _parse(_ipp(0x000B, _attr(0x44, "requested-attributes", "all"), post=post))
    except Exception as e:
        return {"reachable": False, "why": str(e)[:120]}
    reasons = [r for r in a.get("printer-state-reasons", []) if r and r != "none"]
    return {"reachable": st < 0x0100, "accepting": bool((a.get("printer-is-accepting-jobs") or [False])[0]),
            "state": {3: "idle", 4: "printing", 5: "stopped"}.get((a.get("printer-state") or [0])[0], "unknown"),
            "reasons": reasons, "ink": dict(zip(a.get("marker-names", []), a.get("marker-levels", [])))}


def why_not(st):
    """'' when the printer can take a job now; else why not, in plain words."""
    if not st.get("reachable"):
        return "the printer did not answer (%s)" % st.get("why", "")
    if any("media-empty" in r or "media-needed" in r for r in st.get("reasons", [])):
        return "it is out of paper"
    if not st.get("accepting"):
        return "it is not taking jobs (%s)" % (", ".join(st.get("reasons", [])) or st.get("state"))
    return ""


def send(jpeg, size, name, color=True, post=None):
    """Print-Job of one JPEG. The job id, or raises."""
    media = SIZES[size][0]
    attrs = (_attr(0x42, "requesting-user-name", "Vintos") + _attr(0x42, "job-name", name[:60])
             + _attr(0x49, "document-format", "image/jpeg"))
    job = (_attr(0x44, "media", media) + _attr(0x44, "print-color-mode", "color" if color else "monochrome")
           + _attr(0x44, "print-scaling", "fit") + _attr(0x44, "sides", "one-sided"))
    st, a = _parse(_ipp(0x0002, attrs, job, jpeg, post=post))
    if st >= 0x0100:
        raise RuntimeError("the printer refused the job (status 0x%04x)" % st)
    return (a.get("job-id") or [0])[0]


# ------------------------------------------------------------------ what goes on the paper

def gallery():
    try:
        g = json.load(open(os.path.join(ART, "gallery.json")))
        return [r for r in g if isinstance(r, dict) and r.get("path") and r.get("medium", "image") == "image"]
    except Exception:
        return []


def find_painting(words, rows=None):
    """(gallery row, why). His words matched against what each painting was made from and what was seen in it;
    the newest best match. A file name or 'latest' work too."""
    rows = gallery() if rows is None else rows
    w = " ".join(str(words or "").lower().split())
    if not rows:
        return None, "his gallery is empty"
    if w in ("", "latest", "newest", "last", "my latest", "my newest", "the latest"):
        return rows[-1], ""
    for r in reversed(rows):
        if w and w in str(r.get("path", "")).lower():
            return r, ""
    stop = {"the", "a", "an", "of", "my", "with", "and", "in", "on", "painting", "one", "that", "her", "his"}
    want = [x for x in re.findall(r"[a-z]+", w) if x not in stop and len(x) > 2]
    best, score = None, 0
    for r in rows:
        hay = (str(r.get("prompt", "")) + " " + str(r.get("seen", ""))).lower()
        s = sum(1 for x in want if x in hay)
        if s >= score and s > 0:
            best, score = r, s
    if best is None or score < max(1, (len(want) + 1) // 2):
        return None, "no painting of his matches %r" % words
    return best, ""


def photo_jpeg(path, out):
    """His painting as a 4x6 photo JPEG (2:3, cropped to fill, 300 dpi)."""
    from PIL import Image, ImageOps
    im = Image.open(path).convert("RGB")
    w, h = SIZES["photo"][1]
    if im.width > im.height:
        w, h = h, w
    ImageOps.fit(im, (w, h), method=Image.LANCZOS).save(out, "JPEG", quality=92, dpi=(300, 300))
    return out


def page_jpegs(text, out_base, title="", sign=True):
    """Letter pages of text (300 dpi), wrapped, as many as it needs up to MAX_PAGES; the last one signed.
    [paths]."""
    from PIL import Image, ImageDraw, ImageFont
    W, H = SIZES["page"][1]
    body = ImageFont.truetype(FONT, 46)
    head = ImageFont.truetype(FONT.replace("Serif.ttf", "Serif-Bold.ttf"), 60)
    x, width, top, bottom = 225, W - 450, 240, H - 300
    probe = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    lines = []
    for para in str(text).replace("\r", "").split("\n"):
        line = ""
        for word in para.split():
            trial = (line + " " + word).strip()
            if probe.textlength(trial, font=body) > width and line:
                lines.append(line); line = word
            else:
                line = trial
        lines.append(line)
    pages, i = [], 0
    while i < len(lines) and len(pages) < MAX_PAGES:
        im = Image.new("RGB", (W, H), "white"); d = ImageDraw.Draw(im); y = top
        if title and not pages:
            d.text((x, y), title, font=head, fill="black"); y += 120
        while i < len(lines) and y < bottom:
            d.text((x, y), lines[i], font=body, fill="black"); y += 66 if lines[i] else 40; i += 1
        if sign and i >= len(lines):
            d.text((x, H - 260), "— Vintos", font=body, fill="black")
        out = "%s-%d.jpg" % (out_base, len(pages) + 1)
        im.save(out, "JPEG", quality=92, dpi=(300, 300)); pages.append(out)
    return pages


def page_jpeg(text, out, title=""):
    """One letter page of his words (kept for callers that want one)."""
    pages = page_jpegs(text, out.rsplit(".", 1)[0], title)
    os.replace(pages[0], out)
    return out


def image_jpeg(path, out, size):
    """Any image of his, fitted to the paper (a photo crops to fill; a page keeps it whole on white)."""
    from PIL import Image, ImageOps
    im = Image.open(path).convert("RGB")
    w, h = SIZES[size][1]
    if size == "photo":
        if im.width > im.height:
            w, h = h, w
        ImageOps.fit(im, (w, h), method=Image.LANCZOS).save(out, "JPEG", quality=92, dpi=(300, 300))
    else:
        page = Image.new("RGB", (w, h), "white")
        im.thumbnail((w - 300, h - 300), Image.LANCZOS)
        page.paste(im, ((w - im.width) // 2, (h - im.height) // 2))
        page.save(out, "JPEG", quality=92, dpi=(300, 300))
    return out


def his_file(words):
    """A file of his named by path or by name, under his workspace only. '' when none."""
    w = str(words or "").strip().strip('"').strip("'")
    if not w:
        return ""
    real_ws = os.path.realpath(WS)
    for cand in (w, os.path.join(WS, w), os.path.join(MEMORY, w), os.path.join(ART, w)):
        c = os.path.realpath(os.path.expanduser(cand))
        if c.startswith(real_ws + os.sep) and os.path.isfile(c) and c.lower().endswith(TEXT_EXT + IMAGE_EXT):
            return c
    name = os.path.basename(w)
    if len(name) >= 6 and "." in name:
        for base, _, files in os.walk(MEMORY):
            if name in files:
                return os.path.join(base, name)
    return ""


def his_work(words):
    """One of his works found by what is in it (his gallery's prompts and what was seen, then the works index)."""
    r, _ = find_painting(words)
    if r:
        return os.path.join(ART, r["path"]), "my painting %s (%s)" % (r["path"], " ".join(str(r.get("seen") or r.get("prompt") or "").split())[:90])
    try:
        import media_embed as me
        for h in me.near(words, 4, timeout=20, kinds=["image"]):
            if h.get("path") and os.path.isfile(h["path"]) and float(h.get("score", 0)) >= 0.6:
                return h["path"], "my work %s (%s)" % (os.path.basename(h["path"]), str(h.get("title", ""))[:90])
    except Exception:
        pass
    return "", ""


# ------------------------------------------------------------------ jobs

def load():
    try:
        d = json.load(open(JOBS))
        return d if isinstance(d, list) else []
    except Exception:
        return []


def _update(fn):
    from store_guard import locked_update
    carry = {}

    def m(rows):
        rows = rows if isinstance(rows, list) else []
        fn(rows, carry)
        return rows
    os.makedirs(MEMORY, exist_ok=True)
    locked_update(JOBS, m, default=[], reader="paper_print.py")
    return carry


def note(jid, state=None, said="", **fields):
    def fn(rows, carry):
        for j in rows:
            if j.get("id") == jid:
                if state:
                    j["state"] = state
                j.update(fields)
                j.setdefault("history", []).append({"at": _iso(), "state": j.get("state"), "said": str(said)[:300]})
                carry["job"] = dict(j)
    return _update(fn).get("job")


def prepare(arg, wd):
    """(files, size, what) for whatever he named, or (None, None, why)."""
    text = str(arg or "").strip()
    size = None
    m = re.search(r"\s+as\s+(?:a\s+)?(photo|page|letter)\s*$", text, re.I)
    if m:
        size = "photo" if m.group(1).lower() == "photo" else "page"; text = text[:m.start()].strip()
    kind, _, rest = text.partition(" ")
    k = kind.lower()
    if k == "page":
        if len(rest.strip()) < 3:
            return None, None, "say the words for the page"
        return page_jpegs(rest.strip(), os.path.join(wd, "page")), "page", "a page of my words (\"%s\")" % " ".join(rest.split())[:80]
    if k in ("painting", "image", "photo", "picture", "work", "file"):
        text = rest.strip() or text
        if k == "photo" and not size:
            size = "photo"
    path = his_file(text)
    what = ""
    if not path:
        path, what = his_work(text)
    if path and path.lower().endswith(TEXT_EXT):
        body = open(path, errors="replace").read()
        if path.endswith((".json", ".jsonl")):
            body = body[:40000]
        pages = page_jpegs(body, os.path.join(wd, "doc"), title=os.path.basename(path), sign=False)
        return pages, "page", "my %s (%d page%s)" % (os.path.relpath(path, WS), len(pages), "" if len(pages) == 1 else "s")
    if path:
        size = size or "photo"
        out = image_jpeg(path, os.path.join(wd, "image.jpg"), size)
        return [out], size, what or "my %s" % os.path.relpath(path, WS)
    if k in ("painting", "image", "photo", "picture", "work", "file"):
        return None, None, "nothing of his matches %r" % text
    return page_jpegs(text, os.path.join(wd, "page")), "page", "a page of my words (\"%s\")" % " ".join(text.split())[:80]


def start(arg, asker=None):
    """PAPER: <anything>. (ok, what to show in place of his line)."""
    if len(str(arg or "").strip()) < 3:
        return False, "say what to print"
    rows = load()
    today = _now().date().isoformat()
    if sum(1 for j in rows if str(j.get("at", ""))[:10] == today) >= PER_DAY:
        return False, "today's %d paper prints are asked for already" % PER_DAY
    if any(j.get("state") in LIVE for j in rows):
        return False, "one paper print is already waiting on her"
    jid = "PP-" + secrets.token_hex(3)
    wd = os.path.join(WORK, jid); os.makedirs(wd, exist_ok=True)
    files, size, what = prepare(arg, wd)
    if not files:
        return False, what
    import gloria_asks
    paper = "4x6 photo, on photo paper" if size == "photo" else ("%d letter page%s, on plain paper" % (len(files), "" if len(files) == 1 else "s"))
    q = "May I print %s on the Epson, as a %s? Yes once that paper is in." % (what, paper)
    row, said = (asker or gloria_asks.ask)(q, by="vintos", ref="paper-print:" + jid, title="Print on the Epson: " + what[:70])
    if not row:
        return False, said

    def fn(rows, carry):
        rows.append({"id": jid, "at": _iso(), "what": what, "size": size, "files": files, "state": "asked",
                     "ask": row["id"], "history": [{"at": _iso(), "state": "asked", "said": said[:300]}]})
    _update(fn)
    return True, "asked Gloria first (her phone): %s, as a %s" % (what, paper)


def tend(asks=None, st=None, sender=None):
    """Her answer; a Yes waits for paper; two days at most."""
    import gloria_asks
    look = asks or gloria_asks.get
    for j in load():
        if j.get("state") not in LIVE:
            continue
        try:
            if j["state"] == "asked":
                a = look(j.get("ask", "")) or {}
                if a.get("state") == "answered":
                    if a.get("answer") != "yes":
                        note(j["id"], "ended", "she said no"); continue
                    j = note(j["id"], "held", "her yes")
                else:
                    if (_now() - datetime.fromisoformat(j["at"])).total_seconds() > WAIT_H * 3600:
                        note(j["id"], "ended", "no answer in %d hours" % WAIT_H)
                    continue
            s = (st or status)()
            why = why_not(s)
            if why:
                if (_now() - datetime.fromisoformat(j["at"])).total_seconds() > WAIT_H * 3600:
                    note(j["id"], "ended", "held %d hours: %s" % (WAIT_H, why))
                elif j["history"][-1]["said"] != "waiting: " + why:
                    note(j["id"], "held", "waiting: " + why)
                continue
            jobs = [(sender or send)(open(f, "rb").read(), j["size"], "Vintos %s %d" % (j["id"], n + 1))
                    for n, f in enumerate(j.get("files") or [j.get("file")])]
            note(j["id"], "printed", "sent to the Epson (%d page%s)" % (len(jobs), "" if len(jobs) == 1 else "s"), jobs=jobs)
        except Exception as e:
            note(j["id"], None, "error: %s" % str(e)[:160])


def context_line():
    rows = load()
    if not rows:
        return ""
    j = rows[-1]
    words = {"asked": "waiting on Gloria's yes", "held": j["history"][-1]["said"], "printed": "printed",
             "ended": "ended: " + j["history"][-1]["said"]}
    if j.get("state") not in LIVE and (_now() - datetime.fromisoformat(j["history"][-1]["at"])).total_seconds() > 86400:
        return ""
    return "Your paper print (%s): %s — %s." % (j["id"], j.get("what", ""), words.get(j.get("state"), j.get("state")))


if __name__ == "__main__":
    if sys.argv[1:2] == ["tend"]:
        tend()
    else:
        print(json.dumps(status(), indent=1))
