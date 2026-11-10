#!/usr/bin/env python3
"""Wants and promises lane, 10 November (Gloria: "Email and journal wants skip the slack !start/!stop limit"; "he
should work on the newest wants and promises. That's supposed to be on a rolling window").

Scratch workspace under a temporary HOME; Slack, the writers and the readers are stubs; every socket is refused."""
import json, os, socket, sys, tempfile, time, unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="wants-window-")
os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")
os.environ["VINTOS_SECRETS"] = os.path.join(HOME, "no-secrets")
NET = []
def _no_net(self, *a, **k):
    if self.family != socket.AF_UNIX: NET.append(a)
    raise OSError("this suite reaches nothing")
socket.socket.connect = _no_net
sys.path.insert(0, os.path.join(REPO, "scripts"))

import dot_channel as D
import email_commitments as EC
import promise_keeper as PK
import room_work
import want_agent as A
from journal_wants import as_his_want, operational, source_receipt

MEM = Path(os.environ["SPARK_WORKSPACE"]) / "memory"
SELF, DOT = "UVINTOS", D.DOT
WORK = "Run the synthetic torn-read test against the old write"


def iso(dt): return dt.isoformat(timespec="seconds")


def ec(n, days_ago, state="open", what=WORK, base=None):
    at = (base or datetime(2026, 11, 10, 12, 0)) - timedelta(days=days_ago)
    return {"id": "EC-%08x" % n, "what": "%s %d" % (what, n), "quote": "I will %s %d." % (what.lower(), n),
            "letter_id": "fixture-letter-%d" % n, "agent": "Fixture Agent", "at": iso(at), "state": state, "evidence": "",
            "rests_on": []}


def bound(wid, days_ago, text="I want to run the synthetic audio analysis %s and export its score.", **over):
    w = dict(id=wid, want=text % wid, source="idle-journal", journal_seeded=True,
             timestamp=iso(datetime(2026, 11, 10, 12, 0) - timedelta(days=days_ago)))
    w.update(source_receipt("journal", "fixture-journal-" + wid, w["want"])); w.update(over)
    return w


class Base(unittest.TestCase):
    def setUp(self):
        for p in (EC.STORE, PK.STORE, D.STATE, D.PAUSE_FILE):
            self.assertTrue(str(p).startswith(HOME), p)
        self.assertTrue(str(A.workspace()).startswith(HOME))
        if MEM.exists():
            import shutil; shutil.rmtree(MEM)
        MEM.mkdir(parents=True)
        self.write("current-wants.json", []); self.write("fulfilled-wants.json", [])
        for k in EC.COUNTS: EC.COUNTS[k] = 0
        self.posts = []; self.now = 2000000000.0
        for target, name, value in ((room_work, "evidence_sync", lambda s: None),
                                    (room_work, "evidence_finish", lambda *a, **k: "untracked")):
            p = patch.object(target, name, value); p.start(); self.addCleanup(p.stop)

    def write(self, name, value): (MEM / name).write_text(json.dumps(value))
    def read(self, name): return json.loads((MEM / name).read_text())
    def post(self, text, agent, identity):
        self.posts.append(text); return {"ok": True, "ts": "%.6f" % (self.now + len(self.posts))}
    def intake(self, state=None):
        return A.intake(state if state is not None else {}, self.post, lambda s: None, self.now)


class WantWindow(Base):
    def test_newest_bound_want_is_handed_over_first(self):
        self.write("current-wants.json", [bound("older", 3), bound("newer", 1), bound("middle", 2)])
        self.intake()
        self.assertEqual(len(self.posts), 1); self.assertIn("[want:newer]", self.posts[0])

    def test_wants_outside_the_window_age_out_counted_and_marked_never_dropped(self):
        working = bound("in-work", 30); working["agent_work"] = {"request_id": "WA-" + "a" * 24, "status": "in_work",
                                                                  "goal_sha256": A.fingerprint(working["want"])}
        self.write("current-wants.json", [bound("stale-a", 20), bound("stale-b", 9), bound("fresh", 6), working, bound("newest", 0)])
        lines = self.intake()
        self.assertIn("want window: 2 aged out (bound, never handed over, older than 7 days before the newest)", lines)
        rows = {w["id"]: w for w in self.read("current-wants.json")}
        self.assertEqual(len(rows), 5)                                                 # nothing removed
        self.assertEqual({k for k, w in rows.items() if w.get("aged_out")}, {"stale-a", "stale-b"})
        self.assertEqual(rows["stale-a"]["aged_out"]["window_days"], A.WINDOW_DAYS)
        self.assertNotIn("aged_out", rows["in-work"])                                  # work in hand keeps going
        self.assertFalse(any(m in "".join(self.posts) for m in ("[want:stale-a]", "[want:stale-b]")))
        self.assertNotIn("want window", " ".join(self.intake()))                       # counted once

    def test_window_does_not_move_while_nothing_new_comes(self):
        self.write("current-wants.json", [bound("only", 400)])
        self.assertNotIn("want window", " ".join(self.intake()))
        self.assertEqual(len(self.posts), 1)


class EmailPromiseWindow(Base):
    def test_owed_rows_are_never_dropped_by_the_cap(self):
        rows = [ec(i, 1, state="open" if i % 2 else "done") for i in range(240)]
        EC._save(rows)
        kept = EC._load()
        self.assertEqual(len(kept), EC.CAP)
        self.assertEqual(sum(1 for r in kept if r["state"] == "open"), 120)            # every owed one
        self.assertEqual(EC.COUNTS["trimmed"], 40)
        lines = EC.sync({}, self.now)
        self.assertIn("email promises: 40 row(s) no longer owed let go at the 200-row cap", lines)
        self.assertFalse([l for l in EC.sync({}, self.now) if "let go" in l])
        EC._save([ec(i, 1) for i in range(230)])                                       # all owed: past the cap, all kept
        self.assertEqual(len(EC._load()), 230)

    def test_the_cap_never_lets_an_aged_out_promise_go(self):
        # review: an aged-out promise is still his and can still be kept (close_lines, close_sources take it), so the
        # cap lets go only rows no longer owed at all, however old the aged-out ones are
        rows = [ec(i, 30, state="aged out") for i in range(30)] + [ec(100 + i, 1, state="done") for i in range(190)]
        EC._save(rows)
        kept = EC._load()
        self.assertEqual(sum(1 for r in kept if r["state"] == "aged out"), 30)
        self.assertEqual((len(kept), EC.COUNTS["trimmed"]), (200, 20))

    def test_a_promise_recorded_while_sync_runs_is_not_lost(self):
        # review: sync now runs on every room pass, paused or not, and the mail reader records promises in another
        # process; each load-change-save holds the store's lock, so neither writes over the other's rows
        import threading
        EC._save([ec(1, 0)])
        inside, release, done = threading.Event(), threading.Event(), []
        def open_items(state):
            inside.set(); release.wait(10); return []
        def recorder():
            done.append(EC.record("fixture-letter-new", "I will build the second synthetic chart.", think=lambda *a, **k: json.dumps(
                [{"what": "Build the second synthetic chart", "quote": "I will build the second synthetic chart.", "evidence": "", "rests_on": []}])))
        with patch.object(room_work, "open_items", open_items):
            syncer = threading.Thread(target=lambda: EC.sync({}, self.now)); syncer.start()
            self.assertTrue(inside.wait(10))
            writer = threading.Thread(target=recorder); writer.start()
            writer.join(0.5); self.assertTrue(writer.is_alive())                     # it waits for the store
            release.set(); syncer.join(10); writer.join(10)
        self.assertEqual(len(done[0]), 1)
        self.assertEqual(sorted(r["id"] for r in EC._load()), sorted(["EC-%08x" % 1, done[0][0]["id"]]))

    def test_newest_first_and_older_ones_age_out_visibly(self):
        rows = [ec(1, 20), ec(2, 10), ec(3, 5), ec(4, 0), ec(5, 30, state="in work")]
        self.write("email-commitments.json", rows)
        with patch("awaiting_evidence.store") as store:
            store.return_value.safe_read.return_value = {}
            owed = EC.open_rows()
            block = EC.block()
        self.assertEqual([r["id"] for r in owed], ["EC-00000004", "EC-00000003", "EC-00000005"])   # in work kept
        states = {r["id"]: r["state"] for r in EC._load()}
        self.assertEqual((states["EC-00000001"], states["EC-00000002"]), ("aged out", "aged out"))
        self.assertIn("newest first, within 7 days of the newest; 2 older ones aged out, kept as aged out", block)
        self.assertLess(block.index("EC-00000004"), block.index("EC-00000003"))
        self.assertEqual(EC.COUNTS["aged_out"], 2)
        text, log = EC.close_lines("PROMISE DROPPED EC-00000001: overtaken by the newer test")
        self.assertEqual(log, ["promise EC-00000001 dropped"])                          # an aged-out one can still be closed

    def test_sync_says_what_aged_out(self):
        self.write("email-commitments.json", [ec(1, 9), ec(2, 0)])
        self.assertIn("email promises aged out of the 7-day window: 1 (kept, marked aged out)", EC.sync({}, self.now))


class Adoption(Base):
    def test_owed_email_promises_become_bound_wants_newest_first_a_few_at_a_time(self):
        self.write("email-commitments.json", [ec(i, i % 5) for i in range(1, 6)]
                   + [ec(9, 0, what="Read the letter again")])                          # not literal work
        made = A.adopt_promises(now=self.now)
        self.assertEqual(len(made), A.ADOPT_OPEN)
        wants = self.read("current-wants.json")
        self.assertTrue(all(A.specific(w) and A.bypass(w) for w in wants))
        self.assertTrue(all({"kind": "commitment", "id": w["adopted_from"]} in w["source_refs"] for w in wants))
        self.assertNotIn("EC-00000009", [w["adopted_from"] for w in wants])
        self.assertEqual(A.adopt_promises(now=self.now), [])                           # three open: no more, none twice
        newest = sorted([r for r in EC.open_rows() if operational(r["what"])], key=lambda r: r["at"], reverse=True)[:3]
        self.assertEqual({w["adopted_from"] for w in wants}, {r["id"] for r in newest})
        # handed over, the request names its promise; finished, the promise is kept
        self.intake()
        w = next(w for w in self.read("current-wants.json") if w.get("agent_work"))
        self.assertEqual(w["agent_work"]["commitment_ids"], [w["adopted_from"]])
        A.close_sources(w, "Synthetic test run, numbers attached.", "https://example.invalid/r", A.workspace())
        self.assertEqual({r["id"]: r["state"] for r in EC._load()}[w["adopted_from"]], "done")
        # one finished frees a place for the next newest
        rows = self.read("current-wants.json")
        for r in rows:
            if r["id"] == w["id"]: r["fulfilled"] = True
        self.write("current-wants.json", rows)
        self.assertEqual(len(A.adopt_promises(now=self.now)), 1)

    def test_journal_promise_that_is_work_goes_to_the_want_lane_not_a_thread(self):
        d = PK.load(); d["items"].append({"id": "PR-abc123", "at": "20:01", "quote": "render the tide chart tonight",
                                          "what": "Render the synthetic tide chart as a PNG", "state": "open",
                                          "opened": iso(PK._now()), "thread": None})
        d["items"].append({"id": "PR-def456", "at": "20:02", "quote": "show her the chart", "what": "Show Gloria the chart",
                           "state": "open", "opened": iso(PK._now()), "thread": None})
        PK.save(d)
        made = A.adopt_promises(now=self.now)
        self.assertEqual(made, ["promise PR-abc123 became a want for the work lane"])
        w = self.read("current-wants.json")[0]
        self.assertEqual((w["source"], A.specific(w)), ("idle-journal", True))
        posted = []
        PK.scan(lambda s, t: "NONE", lambda text: posted.append(text) or "1.0")
        self.assertEqual(len(posted), 1); self.assertIn("show her the chart", posted[0])  # only the one that is not work
        self.intake()
        w = self.read("current-wants.json")[0]
        self.assertEqual(w["agent_work"]["promise_ids"], ["PR-abc123"])
        A.close_sources(w, "Chart rendered.", "https://example.invalid/c", A.workspace())
        self.assertEqual([i["id"] for i in PK.pending()], ["PR-abc123"])              # brought to her by results_pass

    def test_unposted_journal_promises_age_out_of_the_window_counted(self):
        old = iso(PK._now() - timedelta(days=10))
        PK.save({"day": (PK._now() - timedelta(days=1)).date().isoformat(), "scanned": [], "items": [
            {"id": "PR-old", "quote": "x", "what": "y", "state": "open", "opened": old, "thread": None},
            {"id": "PR-new", "quote": "x", "what": "y", "state": "open", "opened": iso(PK._now()), "thread": None}]})
        d = PK.load()
        self.assertEqual([i["id"] for i in d["items"]], ["PR-new"])
        PK.save(d)
        self.assertEqual((PK.aged_out_unsaid(), PK.aged_out_unsaid()), (1, 0))


class Receipt(unittest.TestCase):
    def test_email_want_receipt_is_taken_on_the_words_that_are_kept(self):
        letter = "To run the synthetic spectrum comparison and export the table."
        kept = as_his_want(letter)
        self.assertEqual(kept, "I want to run the synthetic spectrum comparison and export the table.")
        before = dict(id="w1", want=kept, source="email", **source_receipt("email", "fixture-mail", letter))
        after = dict(id="w1", want=kept, source="email", **source_receipt("email", "fixture-mail", kept))
        self.assertFalse(A.specific(before)); self.assertTrue(A.specific(after))
        self.assertEqual(as_his_want(kept), kept)
        src = open(os.path.join(REPO, "scripts", "want_email.py")).read()
        self.assertIn("text = as_his_want(text)", src)


class PausedTick(Base):
    """The room is paused: email and journal promises are still worked; the room's own conversation is not."""
    class Slack:
        def __init__(self): self.msgs, self.posted, self.n = [], [], 100.0
        def add(self, user, text, thread=None):
            self.n += 1; ts = "%.6f" % self.n
            m = {"ts": ts, "user": user, "text": text}
            if thread: m["thread_ts"] = thread
            self.msgs.append(m); return ts
        def __call__(self, method, params):
            if method == "auth.test": return {"ok": True, "user_id": SELF}
            if method == "conversations.history":
                return {"ok": True, "messages": [m for m in reversed(self.msgs) if not m.get("thread_ts")]}
            if method == "conversations.replies":
                return {"ok": True, "messages": [m for m in self.msgs if m["ts"] == params["ts"] or m.get("thread_ts") == params["ts"]]}
            if method == "chat.postMessage":
                self.posted.append(params); return {"ok": True, "ts": self.add(SELF, params["text"], params.get("thread_ts"))}
            raise AssertionError("unexpected Slack call " + method)

    def setUp(self):
        super().setUp()
        for target, name, value in ((D, "his_context", lambda: "Synthetic identity"), (D, "talking_with_gloria", lambda now: None),
                                    (D, "slack_lens", lambda lens, state: lens), (D, "study_room", lambda: None)):
            p = patch.object(target, name, value); p.start(); self.addCleanup(p.stop)
        self.now = time.time(); self.today = datetime.fromtimestamp(self.now).date().isoformat()
        D._save(D.STATE, dict(self=SELF, since=1, date=self.today, paused_said=True))
        D.set_paused(True, "fixture owner", self.now - 60)
        self.ordinary = []; self.working = []

    def writer(self, system, user):
        self.working.append(user)
        return {"text": json.dumps({"message": "Plan the exact synthetic task.", "accept": False}), "observations": []}

    def tick(self, slack, at, ask=lambda s, t: "NONE"):
        return D.tick(api=slack, think=lambda *a: self.ordinary.append(1) or "x", fable=lambda *a: self.ordinary.append(1) or "x",
                      now=at, today=self.today, want_writer=self.writer, promise_ask=ask)

    def test_paused_day_still_works_email_and_journal_promises_and_nothing_else(self):
        self.write("email-commitments.json", [ec(7, 0, base=datetime.fromtimestamp(self.now))])
        os.makedirs(PK.JOURNAL_DIR, exist_ok=True)
        Path(PK.JOURNAL_DIR, self.today + ".md").write_text("## 09:00 - Morning\nTonight I will render the tide chart.\n")
        ask = lambda s, t: ("QUOTE: I will render the tide chart | WHAT: Render the synthetic tide chart as a PNG"
                            if "tide chart" in t else "NONE")
        slack = self.Slack(); slack.add(DOT, "An ordinary room question, held while paused.")
        out = self.tick(slack, self.now, ask)
        self.assertTrue(D.paused())
        self.assertFalse(self.ordinary, out)                                            # the room's own voice stays stopped
        self.assertIn("promise EC-00000007 became a want for the work lane", out)
        self.assertIn("promise %s became a want for the work lane" % PK.load()["items"][0]["id"], out)
        self.assertEqual(len(slack.posted), 1, out)                                    # one handoff a pass, no thread
        self.assertNotIn("\U0001F4CC", slack.posted[0]["text"])
        handed = [w for w in self.read("current-wants.json") if w.get("agent_work")]
        self.assertEqual(len(handed), 1); self.assertIn("[want:%s]" % handed[0]["id"], slack.posted[0]["text"])
        self.assertTrue(any("paused by Gloria" in l for l in out))
        out = self.tick(slack, self.now + 60, ask)                                      # the next pass: the next promise
        self.assertEqual(len([w for w in self.read("current-wants.json") if w.get("agent_work")]), 2, out)
        self.assertFalse(self.ordinary)
        self.assertFalse(PK.load()["items"][0].get("thread"))                           # its work is the want, not a thread

    def test_results_channel_her_words_wait_while_paused(self):
        with patch.object(PK, "results_channel", lambda: "fixture-results"), \
             patch.object(D, "fresh", side_effect=AssertionError("her words are not read while paused")):
            self.assertEqual(D.results_pass(self.Slack(), {"self": SELF}, self.now, deliver_only=True), [])

    def test_nothing_reached_the_network(self):
        self.assertEqual(NET, [])


class PausedLinkedAndSlots(Base):
    """Follow-up, 10 November: a promise linked to room work is still worked while the room is paused; a promised piece
    of work that is not worded as a literal task is adopted with its evidence; a silent agent gives its place back;
    a journal promise past its carry-over is still kept by its want and brought to her."""
    def board(self, *open_items, history=()):
        return {"room_work": {"open": [dict(id=i, goal="an unrelated synthetic goal", opened=self.now, touched=self.now,
                                            asks=[], returns=[], steps=[]) for i in open_items], "history": list(history)}}

    def linked(self):
        row = ec(1, 0); row.update(state="in work", work_id="RW-0000aaaa")
        self.write("email-commitments.json", [row])
        return row

    def test_linked_promise_is_adopted_only_while_paused_and_keeps_its_link(self):
        self.linked()
        self.assertEqual(A.adopt_promises(now=self.now, paused=False), [])
        self.assertEqual(A.adopt_promises(now=self.now, paused=True), ["promise EC-00000001 became a want for the work lane"])
        row = EC._load()[0]
        self.assertEqual((row["state"], row["work_id"]), ("in work", "RW-0000aaaa"))   # the link is kept

    def test_want_first_then_room_work_closes_the_promise_once(self):
        self.linked(); A.adopt_promises(now=self.now, paused=True)
        self.intake(self.board("RW-0000aaaa"))
        w = next(w for w in self.read("current-wants.json") if w.get("agent_work"))
        A.close_sources(w, "Synthetic run, numbers attached.", "https://example.invalid/r", A.workspace())
        A.close_sources(w, "a second ending", "https://example.invalid/r2", A.workspace())
        state = self.board(history=[dict(id="RW-0000aaaa", state="dropped", closed_said="room dropped it", closed_at=self.now)])
        EC.sync(state, self.now)
        row = EC._load()[0]
        self.assertEqual((row["state"], row["closed_said"], row["fulfilled_want_id"]), ("done", "Synthetic run, numbers attached.", w["id"]))

    def test_room_work_first_then_the_want_does_not_close_it_again_and_its_place_is_freed(self):
        self.linked(); A.adopt_promises(now=self.now, paused=True)
        EC.sync(self.board(history=[dict(id="RW-0000aaaa", state="done", closed_said="room kept it", closed_at=self.now)]), self.now)
        self.assertEqual(EC._load()[0]["state"], "done")
        w = self.read("current-wants.json")[0]; w["agent_work"] = {"commitment_ids": ["EC-00000001"]}
        A.close_sources(w, "the want's ending", "", A.workspace())
        self.assertEqual(EC._load()[0]["closed_said"], "room kept it")
        self.write("email-commitments.json", EC._load() + [ec(i, 0) for i in (2, 3, 4)])
        lines = A.adopt_promises(now=self.now, paused=True)
        self.assertEqual(len([l for l in lines if "became a want" in l]), 3)            # the kept one holds no place
        self.assertIn("gave its place back: kept another way (1 released so far)", lines[0])   # and says so (review)

    def test_a_promise_its_room_work_kept_is_not_handed_to_an_agent_to_do_again(self):
        # review: the room work closed the promise before any agent had the want; the want is released and never
        # handed over, so the same promise is not done twice
        self.linked(); A.adopt_promises(now=self.now, paused=True)
        EC.sync(self.board(history=[dict(id="RW-0000aaaa", state="done", closed_said="room kept it", closed_at=self.now)]), self.now)
        self.assertTrue(A.adopt_promises(now=self.now, paused=True)[0].endswith("gave its place back: kept another way (1 released so far)"))
        w = self.read("current-wants.json")[0]
        self.assertEqual((w["adoption_released"]["reason"], w.get("agent_work")), ("kept_another_way", None))
        self.intake(); self.intake()
        self.assertEqual(self.posts, [])
        self.assertEqual(A.adopt_promises(now=self.now, paused=True), [])              # said once

    def test_a_want_released_before_any_agent_had_it_is_not_handed_over_later(self):
        # review: "never handed over" gives the place to the next promise; handing it over later as well would make
        # ADOPT_OPEN three more every 48 hours
        self.write("email-commitments.json", [ec(i, 0) for i in range(1, 6)])
        A.adopt_promises(now=self.now - (A.ADOPT_ANSWER_HOURS + 1) * 3600)
        rows = self.read("current-wants.json")
        for w in rows: w["timestamp"] = iso(datetime.fromtimestamp(self.now - (A.ADOPT_ANSWER_HOURS + 1) * 3600))
        self.write("current-wants.json", rows)
        lines = A.adopt_promises(now=self.now)
        self.assertEqual(sum("never handed over after %d h" % A.ADOPT_ANSWER_HOURS in l for l in lines), 3)
        self.assertEqual(sum("became a want" in l for l in lines), 2)                   # the two left come in
        released = {w["id"] for w in self.read("current-wants.json") if w.get("adoption_released")}
        for _ in range(4): self.intake()
        handed = [p.split("]")[0][len("[want:"):] for p in self.posts]
        self.assertTrue(handed); self.assertFalse(set(handed) & released)

    def test_promised_work_with_its_evidence_is_adopted_and_told_its_acceptance(self):
        plain = ec(1, 0, what="Write up the synthetic comparison for the letter"); plain["evidence"] = "a table of the synthetic numbers"
        bare = ec(2, 0, what="Write up the other synthetic comparison")
        self.write("email-commitments.json", [plain, bare])
        self.assertFalse(operational(plain["what"]))
        self.assertEqual(A.adopt_promises(now=self.now), ["promise EC-00000001 became a want for the work lane"])
        w = self.read("current-wants.json")[0]
        self.assertTrue(A.specific(w)); self.assertEqual(w["done_when"], "a table of the synthetic numbers")
        self.intake()
        self.assertIn('Done when this exists (what he promised would show it): "a table of the synthetic numbers"', self.posts[0])
        self.assertFalse(A.specific(dict(w, done_when="")))                             # without its evidence it is not work

    def silent(self, hours, answered=False):
        self.write("email-commitments.json", [ec(i, 0) for i in range(1, 6)])
        A.adopt_promises(now=self.now)
        rows = self.read("current-wants.json")
        rid = "WA-" + "b" * 24
        rows[0]["agent_work"] = {"request_id": rid, "status": "in_work", "thread": "%.6f" % (self.now - hours * 3600),
                                 "goal_sha256": A.fingerprint(rows[0]["want"])}
        self.write("current-wants.json", rows)
        if answered:
            folder = A.directory(rid, A.workspace()); folder.mkdir(parents=True)
            (folder / "working-thread.json").write_text(json.dumps({"events": [{"key": "agent:1.0"}]}))
        return rows[0]["id"]

    def test_silent_agent_gives_its_place_back_after_the_timeout_counted(self):
        wid = self.silent(A.ADOPT_ANSWER_HOURS + 1)
        lines = A.adopt_promises(now=self.now)
        self.assertEqual(lines[0], "adopted want %s gave its place back: no answer after %d h (1 released so far)" % (wid, A.ADOPT_ANSWER_HOURS))
        self.assertEqual(len(lines), 2)                                                 # and the next newest comes in
        w = next(w for w in self.read("current-wants.json") if w["id"] == wid)
        self.assertEqual(w["adoption_released"]["reason"], "no_answer"); self.assertIn("agent_work", w)
        self.assertEqual(A.adopt_promises(now=self.now), [])                           # said once

    def test_an_agent_that_answered_or_is_not_yet_late_keeps_its_place(self):
        self.silent(A.ADOPT_ANSWER_HOURS + 1, answered=True)
        self.assertEqual(A.adopt_promises(now=self.now), [])
        Base.setUp(self)
        self.silent(A.ADOPT_ANSWER_HOURS - 1)
        self.assertEqual(A.adopt_promises(now=self.now), [])

    def test_journal_promise_past_its_carry_over_is_still_kept_by_its_want_and_brought_to_her(self):
        start = datetime(2026, 11, 1, 9, 0)
        with patch.object(PK, "_now", lambda: start):
            PK.save({"day": "2026-11-01", "scanned": [], "items": [
                {"id": "PR-carry1", "quote": "x", "what": "Render the synthetic tide chart as a PNG", "state": "open",
                 "opened": iso(start), "thread": None}]})
            A.adopt_promises(now=self.now)
        later = start + timedelta(days=10)
        with patch.object(PK, "_now", lambda: later):
            self.assertEqual([i["id"] for i in PK.load()["items"]], ["PR-carry1"])     # carried: its want works it
            self.assertEqual(len(PK.close_ids(["PR-carry1"], "Chart rendered.")), 1)
            self.assertEqual(PK.close_ids(["PR-carry1"], "again"), [])                 # once
            self.assertEqual([i["id"] for i in PK.pending()], ["PR-carry1"])
        with patch.object(PK, "_now", lambda: later + timedelta(days=1)):
            self.assertEqual([i["id"] for i in PK.pending()], ["PR-carry1"])           # not yet brought: carried past midnight
            PK.mark_posted("PR-carry1")
        with patch.object(PK, "_now", lambda: later + timedelta(days=2)):
            self.assertEqual(PK.pending(), [])
            self.assertEqual(PK.close_ids(["PR-carry1"], "again"), [])                 # the archive does not bring it back

    def test_journal_promise_already_filed_away_is_found_and_closed_once(self):
        os.makedirs(PK.ARCHIVE, exist_ok=True)
        json.dump({"day": "2026-10-20", "items": [{"id": "PR-filed1", "quote": "x", "what": "y", "state": "open"}]},
                  open(os.path.join(PK.ARCHIVE, "2026-10-20.json"), "w"))
        self.assertEqual(len(PK.close_ids(["PR-filed1"], "Made.")), 1)
        self.assertEqual(PK.close_ids(["PR-filed1"], "Made."), [])
        self.assertEqual([i["id"] for i in PK.pending()], ["PR-filed1"])


if __name__ == "__main__":
    unittest.main()
