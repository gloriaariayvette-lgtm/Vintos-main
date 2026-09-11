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


# Values that are not keys. `sk-REPLACE_ME` sat twice under the real key in her file, and
# anything that SOURCES the env file takes the last assignment — so a reader could send the
# placeholder and get 401 Unauthorized, which reads as a revoked key and is not one.
PLACEHOLDERS = ("replace_me", "replace-me", "changeme", "change_me", "your-key-here",
                "your_key_here", "xxx", "todo", "tbd", "none", "null")


def is_placeholder(v):
    """True for a value that is obviously a stand-in rather than a secret."""
    t = str(v or "").strip().strip("<>").lower()
    if not t:
        return True
    if t in PLACEHOLDERS:
        return True
    return any(ph in t for ph in ("replace_me", "replace-me", "changeme", "your-key-here"))


def assignments(name, path=None):
    """Every assignment of `name` in the file, in order. A name assigned more than once is
    always a mistake worth naming: a file parser takes the first, a shell that sources the
    file and systemd's EnvironmentFile take the last, so the same file hands two readers
    two different values and nothing says so."""
    out = []
    try:
        with open(path or DEFAULT_PATH) as f:
            for i, line in enumerate(f, 1):
                s_ = line.strip()
                if not s_ or s_.startswith("#"):
                    continue
                if s_.startswith("export "):
                    s_ = s_[7:].lstrip()
                if s_.startswith(name + "="):
                    out.append((i, _unquote(s_.split("=", 1)[1])))
    except Exception:
        pass
    return out


def value(name, default="", path=None):
    """The environment first — that is how every one of the old readers behaved, and a
    unit or a shell that exports the key must keep winning over the file. Then the file.
    Never raises, and never logs what it found."""
    v = _unquote(os.environ.get(name, ""))
    # A placeholder in the environment is worse than nothing: it is sent, and the provider
    # says 401. Fall through to the file rather than carry it to the wire.
    if v and not is_placeholder(v):
        return v
    real = [(i, val) for i, val in assignments(name, path) if val and not is_placeholder(val)]
    if real:
        return real[-1][1]      # shell semantics: the last real assignment wins
    return default


def describe(name, path=None):
    """What shape the value is in, without ever printing it. For the questions that matter
    when a provider says 401: how many times is this assigned, is any of them a placeholder,
    and which one actually wins?"""
    rows = assignments(name, path)
    env_raw = os.environ.get(name, "")
    chosen = value(name, "", path)
    out = {"name": name,
           "assignments": [{"line": i, "placeholder": is_placeholder(v), "len": len(v),
                            "tail": ("…" + v[-4:]) if len(v) > 6 else v} for i, v in rows],
           "in_environment": bool(env_raw),
           "environment_is_placeholder": bool(env_raw) and is_placeholder(_unquote(env_raw)),
           "found": bool(chosen)}
    if len(rows) > 1:
        out["warning"] = ("%s is assigned %d times on lines %s. A file parser takes the first; "
                          "a shell that sources this file, and systemd's EnvironmentFile, take "
                          "the last. Two readers, two values, and nothing says so."
                          % (name, len(rows), ", ".join(str(i) for i, _ in rows)))
    if rows and all(is_placeholder(v) for _, v in rows) and not chosen:
        out["warning"] = "%s is only ever set to a placeholder; nothing real to send" % name
    if chosen:
        out["chosen_tail"] = "…" + chosen[-4:]
        out["chosen_len"] = len(chosen)
    return out


if __name__ == "__main__":
    import json, sys
    names = sys.argv[1:] or ["OPENAI_API_KEY", "SOL_MODEL", "XAI_API_KEY", "BRAVE_API_KEY"]
    for n in names:
        print(json.dumps(describe(n)))
