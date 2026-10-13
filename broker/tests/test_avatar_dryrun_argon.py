#!/usr/bin/env python3
"""avatar_dryrun --argon sends his real last avatar prompt to Gemini 4 Argon and prints the reply (2026-10-13).

Only the argon() function is loaded (the script itself reads /tmp and calls his router at import). urlopen is a
recorder, HOME is throwaway and the key comes from a scratch vintos.env, so nothing is sent."""
import ast, io, json, os, sys, tempfile, urllib.request

TMP = tempfile.mkdtemp(prefix="argon-")
os.environ["HOME"] = TMP
os.makedirs(os.path.join(TMP, ".vintos"), exist_ok=True)
open(os.path.join(TMP, ".vintos", "vintos.env"), "w").write("GEMINI_API_KEY=test-gemini-key\n")
os.environ.pop("GEMINI_API_KEY", None)
REPO = os.path.realpath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(REPO, "scripts"))

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:300]) if d and not ok else ""))

SENT = []
class _Resp(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *a): return False
def fake(req, timeout=None):
    SENT.append((req.full_url, dict(req.header_items()), json.loads(req.data.decode())))
    return _Resp(json.dumps({"candidates": [{"content": {"parts": [{"text": "private reasoning", "thought": True},
                                                                    {"text": "[SCENE: kitchen] Come here."}]}}],
                             "usageMetadata": {"promptTokenCount": 9000, "candidatesTokenCount": 40}}).encode())
urllib.request.urlopen = fake

src = open(os.path.join(REPO, "bin", "avatar_dryrun.py")).read()
fn = next(n for n in ast.parse(src).body if isinstance(n, ast.FunctionDef) and n.name == "argon")
ns = {"os": os, "sys": sys, "json": json, "re": __import__("re")}
exec(compile(ast.Module([fn], []), "avatar_dryrun.py", "exec"), ns)

check("the sender is a recorder", urllib.request.urlopen is fake)
text, usage = ns["argon"]("I am Vintos.\n[[CACHESPLIT]]\nlive tail",
                          [{"role": "user", "content": "hi"}, {"role": "user", "content": [{"type": "text", "text": "again"}]},
                           {"role": "assistant", "content": "hello"}, {"role": "user", "content": "kettle's on"}])
url, headers, body = SENT[-1]
check("it addresses Gemini 4 Argon", url.endswith("/models/gemini-4-argon:generateContent"), url)
check("the key goes in the header, not the URL", headers.get("X-goog-api-key") == "test-gemini-key" and "key=" not in url, headers)
check("the split marker never reaches Argon", "[[CACHESPLIT]]" not in json.dumps(body))
check("turns alternate user/model, consecutive ones joined", [c["role"] for c in body["contents"]] == ["user", "model", "user"]
      and body["contents"][0]["parts"][0]["text"] == "hi\n\nagain", body["contents"])
check("its private reasoning is not shown as the reply", text == "[SCENE: kitchen] Come here.", text)
check("token use is reported", usage.get("promptTokenCount") == 9000)
print("\n%d/%d passed" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
