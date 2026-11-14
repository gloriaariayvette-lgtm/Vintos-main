#!/usr/bin/env python3
"""warm-gratitude-call.py - the model call behind warm-idle-gratitude.sh.

The shell writes the system and user prompts to /tmp/wg_sys.txt and /tmp/wg_usr.txt (paths can be
overridden with WG_SYS / WG_USR) and prints whatever this prints. The helper only ever existed in the
old ~/.openclaw tree, so on this house every warm-idle run failed on a missing file (611 failures by
2026-11-14). This is that helper, routed like its siblings (gloria-model-call.py): the subconscious
flag's URL and model, AEON by default. On any failure it prints nothing and exits 1, so the shell's
"empty means no entry" rule holds.
"""
import json
import os
import sys
import urllib.request


def _subcon_route(url, model):
    """The subconscious flag (subcon_target.py), as in gloria-model-call.py."""
    try:
        for d in (os.path.dirname(os.path.abspath(__file__)), os.path.expanduser("~/.vintos/workspace/scripts")):
            if d not in sys.path:
                sys.path.append(d)
        import subcon_target
        return subcon_target.generative_route(url, model)
    except Exception:
        return url, model


URL = "http://100.79.177.103:1234/v1/chat/completions"
MODEL = "aeon-gemma-4-12b"


def call(sys_msg, usr_msg, url=None, model=None, timeout=600):
    u, m = _subcon_route(os.environ.get("SUBCON_URL") or URL, os.environ.get("SUBCON_MODEL") or MODEL)
    body = json.dumps({"model": model or m,
                       "messages": [{"role": "system", "content": sys_msg}, {"role": "user", "content": usr_msg}],
                       "temperature": 0.9, "max_tokens": 500}).encode()
    req = urllib.request.Request(url or u, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())["choices"][0]["message"]["content"].strip()


def main():
    try:
        sys_msg = open(os.environ.get("WG_SYS", "/tmp/wg_sys.txt")).read()
        usr_msg = open(os.environ.get("WG_USR", "/tmp/wg_usr.txt")).read()
        out = call(sys_msg, usr_msg)
    except Exception as e:
        print("[warm-gratitude-call] no entry: %s" % e, file=sys.stderr)
        return 1
    if not out:
        return 1
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
