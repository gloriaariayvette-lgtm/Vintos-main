#!/usr/bin/env python3
"""Curiosity ntfy receipts open the exact phone answer form. Scratch HOME; no network."""
import importlib.util
import os
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
HOME = tempfile.mkdtemp(prefix="vintos-curiosity-link-")
os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")
os.environ["VINTOS_PUBLIC_BASE"] = "http://aegis.test:8500/"
os.makedirs(os.path.join(os.environ["SPARK_WORKSPACE"], "memory"), exist_ok=True)

spec = importlib.util.spec_from_file_location(
    "architecture_answers", os.path.join(REPO, "scripts", "architecture_answers.py"))
answers = importlib.util.module_from_spec(spec); spec.loader.exec_module(answers)

checks = []
def check(name, condition):
    checks.append(bool(condition)); print(("PASS " if condition else "FAIL ") + name)

url = answers.answer_url("question / one")
headers = answers.ntfy_headers("question / one")
check("the answer URL names one encoded question", url == "http://aegis.test:8500/aq?qid=question%20%2F%20one")
check("tapping the notification opens the answer form", headers.get("Click") == url)
check("the notification also has an explicit Answer action", headers.get("Actions") == "view, Answer, " + url)

server = open(os.path.join(REPO, "bin", "server.py"), encoding="utf-8").read()
web = open(os.path.join(REPO, "bin", "vintos-websearch.py"), encoding="utf-8").read()
twin = open(os.path.join(REPO, "scripts", "vintos-websearch.py"), encoding="utf-8").read()
check("the answer page filters an opaque question id", 'async def _aq_page(qid: str = "")' in server and 'str(x.get("id")) == str(qid)' in server)
check("the one-question form puts the cursor in the answer box", "rows='5' autofocus" in server)
check("the curiosity sender uses the shared actionable headers", "_answer_headers(_qid)" in web)
check("installed web-search twins stay identical", web == twin)
check("the test never touches the live workspace", answers.STORE.startswith(HOME))

print("\n%d/%d" % (sum(checks), len(checks)))
raise SystemExit(0 if all(checks) else 1)
