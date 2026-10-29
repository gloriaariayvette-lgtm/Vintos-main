#!/usr/bin/env python3
"""creative-search.sh sends a well-formed request. A RECENT=$(grep ...) line once sat inside the first
curl's line continuation, so "-d" ran as its own command ("line 50: -d: command not found"), the
model got no body ("'messages' field is required") and every run ended "No search terms generated"
(daily from 2026-08-13). Here curl is a stub on PATH that records its arguments and answers from
canned JSON; HOME is a scratch directory. Nothing reaches the network."""
import json, os, shutil, stat, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
SCRIPT = os.path.join(REPO, "bin", "creative-search.sh")
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:800]) if d and not ok else ""))

syn = subprocess.run(["bash", "-n", SCRIPT], capture_output=True, text=True)
check("bash -n accepts the script", syn.returncode == 0, syn.stderr)

STUB = r'''#!/usr/bin/env python3
import json, os, sys
args = sys.argv[1:]
with open(os.environ["CURL_LOG"], "a") as f:
    f.write(json.dumps(args) + "\n")
joined = " ".join(args)
if "search.brave.com" in joined:
    print(json.dumps({"web": {"results": [{"title": "Agnes Martin grids", "description": "quiet lines", "url": "https://example.invalid/a"}]}}))
else:
    body = json.loads(args[args.index("-d") + 1]) if "-d" in args else {}
    content = ('{"topic": "stillness in repetition", "search_query": "agnes martin grids"}'
               if "looking for creative inspiration" in json.dumps(body) else "The quiet resonated.")
    if not body.get("messages"):
        print(json.dumps({"error": "'messages' field is required"}))
    else:
        print(json.dumps({"choices": [{"message": {"content": content}}]}))
'''

with tempfile.TemporaryDirectory() as tmp:
    home = os.path.join(tmp, "home"); stub_dir = os.path.join(tmp, "stub")
    os.makedirs(os.path.join(home, ".vintos", "workspace", "memory"))
    os.makedirs(os.path.join(home, ".vintos", "logs")); os.makedirs(stub_dir)
    with open(os.path.join(home, ".vintos", "logs", "subconscious.log"), "w") as f:
        f.write("[Creative] Searching: rothko chapel light (because: colour as weight)\n")
    curl = os.path.join(stub_dir, "curl")
    with open(curl, "w") as f:
        f.write(STUB.replace("#!/usr/bin/env python3", "#!" + sys.executable, 1))
    os.chmod(curl, os.stat(curl).st_mode | stat.S_IXUSR)
    log = os.path.join(tmp, "curl.log")
    env = {"HOME": home, "PATH": stub_dir + os.pathsep + os.environ.get("PATH", "/usr/bin:/bin"),
           "CURL_LOG": log, "BRAVE_API_KEY": "test-key-not-real", "LANG": "C.UTF-8"}
    run = subprocess.run(["bash", SCRIPT], capture_output=True, text=True, env=env, timeout=120, cwd=tmp)
    out = run.stdout + run.stderr
    calls = [json.loads(l) for l in open(log)] if os.path.exists(log) else []

    check("no stray command ran (no 'command not found')", "command not found" not in out, out)
    check("the model was not refused for a missing body", "'messages' field is required" not in out, out)
    check("search terms were generated", "No search terms generated" not in out
          and "[Creative] Searching: agnes martin grids" in out, out)
    check("curl ran three times: ask, search, reflect", len(calls) == 3, calls)
    first = calls[0] if calls else []
    check("the first request carries its -d body", "-d" in first, first)
    body = json.loads(first[first.index("-d") + 1]) if "-d" in first else {}
    msgs = body.get("messages") or [{}]
    check("the body is a chat request with a model and one user message",
          body.get("model") and len(msgs) == 1 and msgs[0].get("role") == "user", body)
    check("recent searches reach the prompt, so he is steered somewhere new",
          "rothko chapel light" in msgs[0].get("content", ""), msgs[0].get("content", "")[:400])
    check("the Brave request is the second call, with the generated terms",
          len(calls) > 1 and any("search.brave.com" in a and "agnes%20martin%20grids" in a for a in calls[1]), calls[1:2])
    disc = os.path.join(home, ".vintos", "workspace", "memory", "creative-discoveries.md")
    check("the discovery is saved", os.path.exists(disc) and "agnes martin grids" in open(disc).read())

print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
