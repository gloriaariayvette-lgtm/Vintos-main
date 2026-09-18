#!/usr/bin/env python3
"""Jev's browser chooser is offline-tested: scratch state, stubbed providers, no sender, no host writes."""
import io, json, os, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
TMP = tempfile.mkdtemp(); os.environ["VINTOS_DESKTOP_STATE_DIR"] = TMP
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import browser_agent as BA, browser_jev as BJ, desktop_agent as DA

R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + ("" if ok else " -- " + str(detail)))

check("isolated scratch state", str(DA.STATE_DIR).startswith(TMP), DA.STATE_DIR)

def page(url="https://restaurant.example/menu"):
    state = {"url": url, "title": "Dinner", "scrollY": 0, "height": 2200, "inner": 800, "media": None}
    elements = [{"kind": "field", "text": "Search menu", "value": "", "ontop": True},
                {"kind": "button", "text": "Open tacos", "ontop": True},
                {"kind": "button", "text": "Place order", "ontop": True}]
    return state, elements

def answer(keys, pick, confidence=.93):
    return {"choice": pick, "confidence": confidence, "probabilities": {k: float(k == pick) for k in keys}}

class Slow:
    endpoint = "http://local.test/v1/chat/completions"; model = "local-gemma"; timeout = 3
    def __init__(self): self.calls = []
    def __call__(self, task, summary, step, last, recent, notes=""):
        self.calls.append((task, summary, step, last, recent, notes)); return {"action": "scroll", "px": 333, "reason": "slow"}

calls = []
def click_post(body):
    calls.append(body); qs = body["questions"]
    return {"model": "jev-test", "answers": {"operation": answer(qs["operation"]["criteria"], "CLICK"),
            "click_target": answer(qs["click_target"]["criteria"], "1")}}

old_post = BJ._post; BJ._post = click_post
slow = Slow(); planner = BJ.JevPlanner(slow)
st, els = page(); action = planner.choose_page("pick tacos", "summary", 1, "", [], "plan", st, els, "Tacos", [])
check("one Jev call selects one observed compatible target", len(calls) == 1 and action["action"] == "click" and action["n"] == 1, (calls, action))
sent = calls[0]
check("purchase control is absent from Jev's target space", all("Place order" not in json.dumps(v) for v in sent["questions"]["click_target"]["criteria"].values()), sent["questions"])
check("no screenshot or field value is sent", "image" not in json.dumps(sent).lower() and sent["state"]["elements"][0]["filled"] is False, sent["state"])

class Response:
    def __init__(self, obj): self.obj = obj
    def __enter__(self): return self
    def __exit__(self, *_): pass
    def read(self): return json.dumps(self.obj).encode()

def type_post(body):
    calls.append(body); qs = body["questions"]
    return {"model": "jev-test", "answers": {"operation": answer(qs["operation"]["criteria"], "TYPE_TEXT"),
            "type_text_target": answer(qs["type_text_target"]["criteria"], "0")}}

typed_requests = []
def local_http(req, timeout=0):
    typed_requests.append(json.loads(req.data)); return Response({"choices": [{"message": {"content": '{"text":"tacos","enter":true}'}}]})

BJ._post = type_post; old_http = BJ.HTTP; BJ.HTTP = local_http
action = planner.choose_page("search for tacos", "summary", 1, "", [], "plan", st, els, "Menu", [])
check("Jev picks the field and local Gemma supplies text", action["action"] == "type" and action["n"] == 0 and action["text"] == "tacos" and action["enter"], action)
check("field prose used only the local endpoint", len(typed_requests) == 1 and typed_requests[0]["model"] == "local-gemma", typed_requests)

private_calls = len(calls)
action = planner.choose_page("pay", "summary", 1, "", [], "plan", *page("https://restaurant.example/checkout"), "Card number", [])
check("checkout stays on local Gemma without a Jev call", len(calls) == private_calls and action["planner"] == "gemma_fallback", action)

def low_post(body):
    qs = body["questions"]; return {"model": "jev-test", "answers": {"operation": answer(qs["operation"]["criteria"], "CLICK", .2),
                                                                  "click_target": answer(qs["click_target"]["criteria"], "1")}}
BJ._post = low_post
action = planner.choose_page("pick tacos", "summary", 1, "", [], "plan", st, els, "Tacos", [])
check("low confidence falls back locally", action["planner"] == "gemma_fallback" and action["fallback_reason"] == "jev_low_operation_confidence", action)

os.environ.pop("TYPESAFE_API_KEY", None); os.environ["VINTOS_BROWSER_PLANNER"] = "auto"
check("house auto mode remains Gemma when Jev has no key", isinstance(BA.planner_for_house(), BA.GemmaTextPlanner))
os.environ["TYPESAFE_API_KEY"] = "test"; check("house auto mode selects Jev when configured", isinstance(BA.planner_for_house(), BJ.JevPlanner))

class PurchaseBrowser:
    def ensure(self): return {"ok": True}
    def activate(self): return {"ok": True}
    def elements(self): return {"state": {"url": "https://x.test/cart", "title": "Cart", "scrollY": 0, "height": 800, "inner": 800, "media": None},
                                "elements": [{"kind": "button", "text": "Place order", "ontop": True}]}
    def text(self): return {"text": "Place order", "outline": []}
    def click(self, n): raise AssertionError("purchase click escaped")
    def shot(self): return b""
pb = PurchaseBrowser()
script = iter([{"action": "click", "n": 0}, {"action": "fail", "reason": "blocked", "evidence": "Place order"}])
result = BA.run("buy dinner", pb, lambda *a: next(script), max_steps=2, should_stop=lambda: False)
check("executor refuses an irreversible purchase click", result.status == "failed" and result.reason.startswith("blocked"), result)

BJ._post = old_post; BJ.HTTP = old_http
check("no provider or sender escaped the suite", len(calls) >= 2 and all(c.get("model") == "jev-latest" for c in calls), calls)
print("\n%d/%d passed" % (sum(R), len(R))); raise SystemExit(0 if all(R) else 1)
