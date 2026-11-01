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
deploy = open(os.path.join(REPO, "scripts", "deploy-atelier.sh"), encoding="utf-8").read()
check("the answer page filters an opaque question id", 'async def _aq_page(qid: str = "")' in server and 'str(x.get("id")) == str(qid)' in server)
check("the one-question form puts the cursor in the answer box", "rows='5' autofocus" in server)
check("the curiosity sender uses the shared actionable headers", "_answer_headers(_qid)" in web)
check("installed web-search twins stay identical", web == twin)
check("the answer helper is part of every deployed release", "unsaid_questions.py architecture_answers.py" in deploy)
check("the test never touches the live workspace", answers.STORE.startswith(HOME))

# 1 November: answering a question cleared `delivered`, the web search read that as "never sent", and
# the three questions she had answered on 30 October reached her phone again.
import json
check("the store under test is throwaway", answers.STORE.startswith(HOME))
json.dump([{"id": "q-answered", "question": "Where is the house?", "delivered": True, "delivered_at": 1.0,
            "question_sent_at": 1.0, "answer": None},
           {"id": "q-legacy-answered", "question": "Which bait?", "delivered": True, "answer": None}],
          open(answers.STORE, "w"))
answers.answer("q-answered", "New answer")
answers.answer("q-legacy-answered", "Old record, no send mark")
rows = {x["id"]: x for x in json.load(open(answers.STORE))}
check("answering still leaves the answer waiting for him", rows["q-answered"]["delivered"] is False)
check("an answered question counts as sent, so it is never re-sent", answers.question_sent(rows["q-answered"]))
check("an answered record from before the send mark is not re-sent either", answers.question_sent(rows["q-legacy-answered"]))
check("a record whose send failed is still retried",
      not answers.question_sent({"id": "q", "delivered": False, "answer": None, "answered_at": None}))
check("an old sent record without the new field still counts as sent", answers.question_sent({"id": "q", "delivered": True}))
check("the web search asks question_sent, not the answer's delivered flag",
      "_question_sent(_prior)" in web and '_prior.get("delivered", True)' not in web)
check("a send stamps its own mark", '_rec["question_sent_at"]' in web)
check("an item already handed to her is not picked again", 'not x.get("sent_to_gloria")' in web)

print("\n%d/%d" % (sum(checks), len(checks)))
raise SystemExit(0 if all(checks) else 1)
