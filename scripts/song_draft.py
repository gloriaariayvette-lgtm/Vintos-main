#!/usr/bin/env python3
"""Every song is written by Sonnet first and finished by Grok (Gloria, 17 October: "Songs come from wants and dream
music. Both should be written by Sonnet first and finished by Grok.").

Before this, each path had one writer: a want's song (wants-router -> creative-expression.sh) was Grok alone, and the
5:15 dream music (music-composer.py) was Sonnet alone. Now both paths draft with Sonnet and finish with Grok; the draft
is kept beside the finished spec so the two can be compared.

    python3 song_draft.py draft SOUL_FILE < prompt     # Sonnet's draft spec, or nothing on failure
    python3 song_draft.py finish < draft               # Grok's finished spec, or nothing on failure
"""
import json
import os
import re
import sys
import urllib.request

SHIM = "http://127.0.0.1:8599/v1/chat/completions"
SONNET = "claude-sonnet-5"                    # the model the dream-music composer already writes with
GROK = "grok-4.20-0309-non-reasoning"         # the model a want's song was already written with

FINISH = ("Sonnet wrote this draft of your song. Finish it: the song is yours. Keep what is true and rewrite what is "
          "not, the lyrics most of all - make them sing in your own voice, short singable lines that rhyme and scan, "
          "[Verse]/[Chorus] tags kept, a chorus that returns. Keep every header the draft has, in its order. "
          "Describe the sound in sonic terms, without named artists, bands, composers, or soundtrack references. "
          "Output ONLY the finished spec, starting with **Title:**.")


def _key():
    k = os.environ.get("XAI_API_KEY", "")
    if k:
        return k
    for p in (os.path.expanduser("~/.vintos/workspace/scripts"), os.path.dirname(os.path.abspath(__file__))):
        sys.path.insert(0, p)
    try:
        from env_file import value
        return value("XAI_API_KEY", "")
    except Exception:
        return ""


def _ask(model, messages, max_tokens=2400, temperature=0.9, timeout=200):
    headers = {"Content-Type": "application/json"}
    if model.startswith("grok"):
        headers["Authorization"] = "Bearer " + _key()
    body = json.dumps({"model": model, "messages": messages, "temperature": temperature,
                       "max_tokens": max_tokens}).encode()
    req = urllib.request.Request(SHIM, data=body, headers=headers)
    return json.loads(urllib.request.urlopen(req, timeout=timeout).read().decode())["choices"][0]["message"]["content"]


def _spec(text):
    """A spec, from its **Title:** on; '' when there is none."""
    t = re.sub(r"^```\w*|```$", "", str(text or "").strip()).strip()
    i = t.find("**Title:**")
    return t[i:].strip() if i >= 0 else ""


def draft(system, prompt, ask=None):
    """Sonnet's draft of the whole spec, from the same system and prompt the song is written from."""
    ask = ask or _ask
    try:
        return _spec(ask(SONNET, [{"role": "system", "content": system}, {"role": "user", "content": prompt}]))
    except Exception as e:
        print("song_draft: Sonnet did not answer (%s)" % e, file=sys.stderr)
        return ""


def finish(spec_draft, system="", context="", ask=None):
    """Grok's finished spec. '' when Grok fails or returns no spec: the caller keeps the draft rather than lose the song."""
    if not spec_draft:
        return ""
    ask = ask or _ask
    msgs = ([{"role": "system", "content": system}] if system else []) + [
        {"role": "user", "content": ((context + "\n\n") if context else "") + "THE DRAFT:\n" + spec_draft + "\n\n" + FINISH}]
    try:
        return _spec(ask(GROK, msgs))
    except Exception as e:
        print("song_draft: Grok did not finish (%s)" % e, file=sys.stderr)
        return ""


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "draft":
        soul = ""
        try:
            soul = open(sys.argv[2]).read()[:2000] if len(sys.argv) > 2 else ""
        except OSError:
            pass
        out = draft(soul + "\n\nRespond creatively. Do not explain what you are doing - just create.", sys.stdin.read())
    elif cmd == "finish":
        out = finish(sys.stdin.read())
    else:
        print(__doc__); sys.exit(2)
    if out:
        print(out)
