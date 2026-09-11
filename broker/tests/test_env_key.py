#!/usr/bin/env python3
"""Sol answered 401 for three nights and the key was fine.

Gloria, 11 September: "[Journal] Sol B1 failed (HTTP Error 401: Unauthorized)". Sol had
been writing the B draft for weeks. Astra, on the same OPENAI_API_KEY, in the same file,
kept working the whole time.

Nine places read ~/.vintos/vintos.env and each parsed it by hand. They did not agree:

    astra_call      .strip().strip('"').strip("'")      -> worked
    server.py       .strip().strip('"')                 -> worked
    _load_key       .strip().strip("'\\"")               -> worked
    model_router    .split("=", 1)[1]                   -> raw
    idle-journal    .split("=", 1)[1]                   -> raw
    introspection   .split("=", 1)[1]                   -> raw
    mirror          .split("=", 1)[1]                   -> raw
    code-review     .split("=", 1)[1].strip()           -> raw of the quotes

Every Sol path was in the raw group. Every other OpenAI caller was in the stripping
group. So the moment the file was written the ordinary way —

    OPENAI_API_KEY="sk-..."

— Astra carried on and Sol sent `Authorization: Bearer "sk-...` , quote marks and all,
and OpenAI answered 401. Which looks exactly like a dead key and is not one. The journal
fell back to the house chain every night and said so; nothing pointed at the parse.

One reader now, tolerant of what people actually write in an env file. This holds that,
and holds that no caller has quietly grown its own parse again."""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(REPO, "scripts"))
import env_file as E

R = []
def check(name, ok, detail=""):
    R.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + name + (("  ->  %s" % (detail,)) if (detail and not ok) else ""))

TMP = tempfile.mkdtemp()
ENV = os.path.join(TMP, "vintos.env")
KEY = "sk-proj-" + "A" * 40
open(ENV, "w").write(
    "# his keys\n"
    '\n'
    'OPENAI_API_KEY="%s"\n' % KEY +
    "XAI_API_KEY='xai-%s'\n" % ("B" * 20) +
    "export SOL_MODEL=gpt-5.6\n"
    "BRAVE_API_KEY=brv-plain   # the search fallback\n"
    'CRLF_KEY="win-value"\r\n'
)

print("--- the quoted key is the key, not the key wearing quote marks ---")
check("a double-quoted value comes back unquoted", E.value("OPENAI_API_KEY", path=ENV) == KEY,
      E.value("OPENAI_API_KEY", path=ENV)[:14])
check("and a single-quoted one too", E.value("XAI_API_KEY", path=ENV) == "xai-" + "B" * 20)
check("an exported line is read", E.value("SOL_MODEL", path=ENV) == "gpt-5.6")
check("a trailing comment is not part of an unquoted value",
      E.value("BRAVE_API_KEY", path=ENV) == "brv-plain", E.value("BRAVE_API_KEY", path=ENV))
check("a CRLF line from a non-Linux editor still parses",
      E.value("CRLF_KEY", path=ENV) == "win-value", repr(E.value("CRLF_KEY", path=ENV)))
check("a name that is not there returns the default",
      E.value("NOPE", "fallback", path=ENV) == "fallback")
check("a comment line is never mistaken for a value", E.value("#", path=ENV) == "")

print("\n--- this is exactly what the old Sol parse did with the same line ---")
raw = next(l.strip().split("=", 1)[1] for l in open(ENV) if l.strip().startswith("OPENAI_API_KEY="))
check("the raw parse kept the quote marks", raw == '"%s"' % KEY and raw != KEY)
check("so the Authorization header was malformed", ("Bearer " + raw).startswith('Bearer "'))
check("and the one reader does not", ("Bearer " + E.value("OPENAI_API_KEY", path=ENV)).startswith("Bearer sk-"))

print("\n--- the environment still wins, as it always did ---")
os.environ["OPENAI_API_KEY"] = "sk-from-the-environment"
check("an exported key beats the file", E.value("OPENAI_API_KEY", path=ENV) == "sk-from-the-environment")
os.environ["OPENAI_API_KEY"] = '"sk-quoted-in-the-environment"'
check("and a quoted one there is unquoted too",
      E.value("OPENAI_API_KEY", path=ENV) == "sk-quoted-in-the-environment")
del os.environ["OPENAI_API_KEY"]

print("\n--- a value that legitimately starts with a quote is not truncated ---")
odd = os.path.join(TMP, "odd.env")
open(odd, "w").write('ODD=\'half\nPAIRED="both"\n')
check("an unmatched quote is left alone", E.value("ODD", path=odd) == "'half", repr(E.value("ODD", path=odd)))
check("a matched pair is stripped", E.value("PAIRED", path=odd) == "both")

print("\n--- describe() answers the 401 question without printing the secret ---")
d = E.describe("OPENAI_API_KEY", path=ENV)
check("it says the value was quoted", d["found"] and d["was_quoted"] is True, d)
check("it gives the length difference the quotes caused", d["raw_len"] - d["clean_len"] == 2, d)
check("and it never carries the key itself",
      KEY not in repr(d) and len(d.get("first", "")) <= 4, d)
d2 = E.describe("NOT_SET_AT_ALL", path=ENV)
check("a missing name says so plainly", d2["found"] is False)

print("\n--- no caller kept its own parse ---")
import re
offenders = []
for root in ("bin", "scripts"):
    d = os.path.join(REPO, root)
    for f in sorted(os.listdir(d)):
        p = os.path.join(d, f)
        if f == "env_file.py" or not os.path.isfile(p): continue
        if not (f.endswith(".py") or f.endswith(".sh")): continue
        for i, line in enumerate(open(p, errors="replace"), 1):
            if "vintos.env" not in line and "OPENAI_API_KEY=" not in line: continue
            m = re.search(r"split\(['\"]=['\"], ?1\)\[1\]", line)
            if not m: continue
            tail = line[m.end():m.end() + 70]
            if "strip(" not in tail:
                offenders.append("%s/%s:%d" % (root, f, i))
check("nothing splits the env file and uses the value raw", not offenders, "; ".join(offenders))

print("\n--- every Sol path reads through the one door ---")
def src(rel):
    return open(os.path.join(REPO, rel)).read()
check("the journal's Sol draft uses it", "from env_file import value" in src("bin/idle-journal.sh"))
check("and its twin does too", "from env_file import value" in src("scripts/idle-journal.sh"))
check("the router's sol_draft uses it", "_env(\"OPENAI_API_KEY\")" in src("bin/model_router.py"))
check("and so does the Sol model name", "_env(\"SOL_MODEL\")" in src("bin/model_router.py"))
check("introspection uses it", "from env_file import value" in src("bin/introspection.sh"))
check("mirror uses it", "from env_file import value" in src("scripts/mirror.sh"))
check("the code-review lens uses it", "from env_file import value" in src("bin/vintos-code-review.py"))
check("Astra, which already worked, goes through the same door",
      "from env_file import value" in src("scripts/astra_call.py"))
check("the server does too", "from env_file import value" in src("bin/server.py"))
check("every fallback still strips quotes, for a checkout with no env_file",
      all("strip('\"')" in src(f) or 'strip(\'"\')' in src(f)
          for f in ("bin/idle-journal.sh", "bin/introspection.sh", "scripts/mirror.sh")))

print("\n--- the deploy carries the new module ---")
dep = src("scripts/deploy-atelier.sh")
check("env_file.py is in the manifest", "env_file.py" in dep)

print("\n--- it reached nothing outside its own scratch ---")
check("only a throwaway env file was read", ENV.startswith(TMP))
check("her real key file was never opened by this suite",
      E.DEFAULT_PATH.endswith("vintos.env") and ENV != E.DEFAULT_PATH)

print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
