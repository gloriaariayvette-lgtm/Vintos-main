#!/usr/bin/env python3
"""env_file.py — one reader for ~/.vintos/vintos.env.

Nine places read this file and each of them parsed it by hand. They did not agree,
and the disagreement was invisible until it cost him a model:

    astra_call      .strip().strip('"').strip("'")      → worked
    server.py       .strip().strip('"')                 → worked
    _load_key       .strip().strip("'\\"")               → worked
    model_router    .split("=", 1)[1]                   → raw
    idle-journal    .split("=", 1)[1]                   → raw

Every Sol path was in the raw group and every other OpenAI caller was in the
stripping group. So the moment the file was written the ordinary way —

    OPENAI_API_KEY="sk-..."

— Astra kept working and Sol sent `Authorization: Bearer "sk-...` , quote marks and
all, and OpenAI answered 401 Unauthorized. Which reads exactly like a dead key, and
is not one. The journal fell back to the house chain every night and said so, and
nothing pointed at the parse.

So: one reader, and it is tolerant of the things a person actually writes in an env
file — `export KEY=`, single or double quotes, trailing whitespace, a trailing
comment, blank lines, CRLF from an editor that was not on Linux. The environment
still wins over the file, as it always did.

    value("OPENAI_API_KEY")            -> the key, or ""
    value("SOL_MODEL", "gpt-5.6")      -> the value, or the default
    describe("OPENAI_API_KEY")         -> a shape report that never prints the secret
"""
import os

DEFAULT_PATH = os.path.expanduser("~/.vintos/vintos.env")


def _unquote(raw):
    """The value as the shell would have seen it, minus the noise a hand-edited file
    carries. A quote is only stripped as a matched pair, so a value that legitimately
    begins with one is not silently truncated."""
    v = str(raw or "").strip().rstrip("\r")
    # a trailing comment, but only when it is clearly not part of a quoted value
    if not (v[:1] in ("'", '"')):
        cut = v.find(" #")
        if cut >= 0:
            v = v[:cut].rstrip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in ("'", '"'):
        v = v[1:-1]
    return v.strip()


def value(name, default="", path=None):
    """The environment first — that is how every one of the old readers behaved, and a
    unit or a shell that exports the key must keep winning over the file. Then the file.
    Never raises, and never logs what it found."""
    v = os.environ.get(name, "")
    if v:
        return _unquote(v)
    try:
        with open(path or DEFAULT_PATH) as f:
            for line in f:
                s = line.strip()
                if not s or s.startswith("#"):
                    continue
                if s.startswith("export "):
                    s = s[7:].lstrip()
                if s.startswith(name + "="):
                    got = _unquote(s.split("=", 1)[1])
                    if got:
                        return got
    except Exception:
        pass
    return default


def describe(name, path=None):
    """What shape the value is in, without ever printing it. For the one question that
    matters when a provider says 401: is this a key, or a key wearing quote marks?"""
    src, raw = "environment", os.environ.get(name, "")
    if not raw:
        src = "file"
        try:
            with open(path or DEFAULT_PATH) as f:
                for line in f:
                    s = line.strip()
                    if s.startswith("export "):
                        s = s[7:].lstrip()
                    if s.startswith(name + "="):
                        raw = s.split("=", 1)[1]
                        break
        except Exception:
            return {"name": name, "found": False, "why": "no %s" % (path or DEFAULT_PATH)}
    if not raw:
        return {"name": name, "found": False, "why": "not set in the environment or the file"}
    clean = _unquote(raw)
    return {"name": name, "found": True, "source": src,
            "raw_len": len(raw), "clean_len": len(clean),
            "was_quoted": len(raw.strip()) != len(clean),
            "first": clean[:3] + "…" if clean else "",
            "last": "…" + clean[-2:] if len(clean) > 5 else ""}


if __name__ == "__main__":
    import json, sys
    names = sys.argv[1:] or ["OPENAI_API_KEY", "SOL_MODEL", "XAI_API_KEY", "BRAVE_API_KEY"]
    for n in names:
        print(json.dumps(describe(n)))
