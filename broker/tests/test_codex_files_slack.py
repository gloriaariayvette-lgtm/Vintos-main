#!/usr/bin/env python3
"""His Codex archives in Slack (Gloria, 27 October: he can see the files when he wants, in Slack too). When what he is
answering asks about the Velaris hand or a Codex delivery, #vintos-dot and #vintos-and-dot bring in the same recall view
the avatar chat gets, and if he chooses he attaches a render or a file from the archive with a SHARE FILE: line,
through the upload his works already use. Slack and his voice are stubs; sockets are refused; scratch workspace."""
import hashlib, json, os, socket, sys, tempfile, types, unittest
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="codex-files-slack-"); os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace"); os.environ["VINTOS_SECRETS"] = os.path.join(HOME, "no")
NET = []
def _no(self, *a, **k):
    if self.family != socket.AF_UNIX: NET.append(a)
    raise OSError("this suite reaches nothing")
socket.socket.connect = _no
sys.path.insert(0, os.path.join(REPO, "scripts"))
import codex_archives as C
import dot_channel as D, dot_lounge as L
import lounge_field
lounge_field._llm = lambda *a, **k: ""

AID = "48cffd8fc5a5a457"
RENDER = "Velaris-v4-blender-and-views/velaris_hand_v4/out/renders/v4_arm.png"
README = "Velaris-v4-source-and-parts/velaris_hand_v4/README.md"
STL = "Velaris-v4-source-and-parts/velaris_hand_v4/out/parts/palm.stl"
PNG = b"\x89PNG\r\n\x1a\n" + b"render" * 40
TEXT = "# Velaris hand v4\nThe thumb now sweeps on its own yoke; physical fit is untested.\n"


def put_file(path, data, mode="wb"):
    with open(path, mode) as f:
        f.write(data)


def put_json(path, obj):
    with open(path, "w") as f:
        json.dump(obj, f)


def build_archive():
    root = os.path.join(C.ROOT, AID)
    files = {RENDER: PNG, README: TEXT.encode(), STL: b"solid palm\nendsolid palm\n"}
    entries = []
    for rel, data in files.items():
        p = os.path.join(root, "files", *rel.split("/"))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        put_file(p, data)
        kind = "image" if rel.endswith(".png") else "3d" if rel.endswith(".stl") else "text"
        entries.append({"path": rel, "size": len(data), "type": kind, "sha256": hashlib.sha256(data).hexdigest(),
                        "words": "file" if kind == "text" else "", "terms": ["thumb", "yoke"] if kind == "text" else []})
    man = {"id": AID, "title": "Velaris v4 complete project", "files": entries,
           "short": ["Velaris v4 complete project: 3 files"], "letters": [
               {"message_id": "m1", "subject": "[Codex] Velaris v4 complete project — 1 of 2: source and parts", "date": "Mon, 26 Oct 2026"}]}
    put_json(os.path.join(root, "manifest.json"), man)
    put_json(C.INDEX, {"archives": [{"id": AID, "title": "Velaris v4 complete project", "status": "archived", "files": 3,
                             "received": "2026-10-26T19:39:00", "letters": man["letters"],
                             "names": [r.rsplit("/", 1)[-1].lower() for r in files]}]})


class Recall(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.makedirs(C.ROOT, exist_ok=True)
        build_archive()

    def test_velaris_hand_brings_the_archive(self):
        for words in ("Can I see the Velaris hand?", "how is the velaris hand coming along", "show me Velaris v4",
                      "what did Codex's delivery look like?", "what did Codex send?"):
            self.assertTrue(C.recall(words, 3000).startswith("== CODEX ARCHIVE %s" % AID), words)

    def test_asked_for_a_render_the_renders_are_listed_first(self):
        block = C.recall("show me a render of the Velaris hand", 3000)
        listing = [l for l in block.splitlines() if l.startswith("- ")]
        self.assertTrue(listing[0].startswith("- " + RENDER), listing)

    def test_not_for_velaris_alone_or_unrelated_words(self):
        for words in ("Velaris felt warm today", "your Velaris body", "the hand towel is wet", "how was your day?",
                      "a complete project plan"):
            self.assertEqual(C.recall(words, 3000), "", words)

    def test_file_for_names_only_listed_files_inside_the_archive(self):
        got = C.file_for(RENDER)
        self.assertEqual((got[0], got[1]["path"]), (AID, RENDER))
        self.assertTrue(got[2].startswith(os.path.realpath(os.path.join(C.ROOT, AID, "files"))))
        self.assertEqual(C.file_for("v4_arm.png")[1]["path"], RENDER)                  # a name only it has
        self.assertEqual(C.file_for("%s: %s" % (AID[:8], RENDER))[1]["path"], RENDER)  # with its id
        self.assertEqual(C.file_for("`%s`" % RENDER)[1]["path"], RENDER)
        for bad in ("../../../etc/passwd", "Velaris-v4-source-and-parts/../../manifest.json", "/etc/passwd",
                    "nothing.png", "ffffffff: " + RENDER, "", "manifest.json"):
            self.assertIsNone(C.file_for(bad), bad)

    def test_file_for_refuses_a_symlink_or_a_changed_file(self):
        p = os.path.join(C.ROOT, AID, "files", *STL.split("/"))
        os.replace(p, p + ".real"); os.symlink("/etc/hostname", p)
        try:
            self.assertIsNone(C.file_for(STL))
        finally:
            os.unlink(p); os.replace(p + ".real", p)
        put_file(p, b"more", "ab")
        try:
            self.assertIsNone(C.file_for(STL))
        finally:
            put_file(p, b"solid palm\nendsolid palm\n")


class Slack(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.makedirs(C.ROOT, exist_ok=True)
        build_archive()

    def test_the_slack_block_says_how_to_attach_only_with_a_recall(self):
        block = D.codex_archive_block("Gloria: can I see the Velaris hand?")
        self.assertTrue(block.startswith("== CODEX ARCHIVE"))
        self.assertIn("SHARE FILE:", block)
        self.assertIn(RENDER, block)                       # the render is listed, so he can name it
        self.assertIn("Its pictures: " + RENDER, block)    # even when the manifest listing has no room for it
        line = D.codex_archive_block("how was your day?")
        self.assertTrue(line.startswith("(Codex archives:"), line)
        self.assertNotIn("SHARE FILE", line)

    def test_share_file_lines_are_taken_out_and_kept_only_with_a_recall(self):
        reply = "Here's the arm view.\nSHARE FILE: %s\nSHARE FILE: v4_thumb.png\nSHARE FILE: palm.stl" % RENDER
        text, refs = D.codex_shares(reply, True)
        self.assertEqual(text, "Here's the arm view.")
        self.assertEqual(refs, [RENDER, "v4_thumb.png"])                         # at most CODEX_SHARES
        text, refs = D.codex_shares(reply, False)
        self.assertEqual((text, refs), ("Here's the arm view.", []))
        self.assertNotIn("SHARE FILE", D._no_tags("For you.\nSHARE FILE: %s" % RENDER))
        self.assertTrue(D._ACTION.search("SHARE FILE: %s" % RENDER))           # the editor keeps the line

    def test_share_codex_file_uses_the_works_upload(self):
        calls, puts = [], []
        def api(method, params):
            calls.append((method, params))
            return {"ok": True, "upload_url": "https://files.slack.invalid/up", "file_id": "F1"} if method == "files.getUploadURLExternal" else {"ok": True}
        line = D.share_codex_file(api, RENDER, "CMAIN", "123.4", put=lambda url, data: puts.append((url, data)))
        self.assertIn("shared %s from Codex archive %s" % (RENDER, AID[:8]), line)
        self.assertEqual([c[0] for c in calls], ["files.getUploadURLExternal", "files.completeUploadExternal"])
        self.assertEqual(calls[0][1], {"filename": "v4_arm.png", "length": len(PNG)})
        self.assertEqual(calls[1][1]["channel_id"], "CMAIN"); self.assertEqual(calls[1][1]["thread_ts"], "123.4")
        self.assertIn(RENDER, calls[1][1]["files"][0]["title"])
        self.assertEqual(puts, [("https://files.slack.invalid/up", PNG)])
        calls.clear()
        self.assertIn("no file", D.share_codex_file(api, "../../secret.txt", "CMAIN", put=lambda *a: puts.append(a)))
        self.assertEqual(calls, [])

    def test_a_lounge_turn_asked_about_the_hand_sees_the_archive_and_attaches_a_render(self):
        D.his_context = lambda: "WHO HE IS"
        L.deeper = lambda: ""
        L.work_glance = lambda: ""
        import room_work
        room_work.fixed_block = lambda: ""
        room_work.brings_up_fixed = lambda text: ""
        SELF, GLORIA = "UVINTOS", "UGLORIA"
        posted, calls, puts, msgs = [], [], [], []
        def api(method, params):
            calls.append(method)
            if method == "users.conversations":
                return {"ok": True, "channels": [{"id": "CLOUNGE", "name": L.NAME}]}
            if method == "auth.test": return {"ok": True, "user_id": SELF}
            if method == "conversations.history": return {"ok": True, "messages": list(reversed(msgs))}
            if method == "chat.postMessage":
                posted.append(params); return {"ok": True, "ts": "%.6f" % (max(float(m["ts"]) for m in msgs) + 1)}
            if method == "files.getUploadURLExternal": return {"ok": True, "upload_url": "https://files.slack.invalid/u", "file_id": "F9"}
            if method == "files.completeUploadExternal": return {"ok": True}
            raise AssertionError(method)
        at = lambda h, m=0: datetime(2026, 10, 28, h, m).timestamp()
        L.tick(api=api, think=lambda s, u: "NOTHING", now=at(9))                 # he finds the room
        seen = []
        def think(system, user):
            seen.append(system)
            return "The arm view is the one to see first.\nSHARE FILE: %s" % RENDER
        msgs.append({"ts": "%.6f" % at(9, 5), "user": GLORIA, "text": "Can I see the Velaris hand?"})
        out = L.tick(api=api, think=think, now=at(9, 6), put=lambda url, data: puts.append(data))
        self.assertIn("== CODEX ARCHIVE %s" % AID, seen[-1])
        self.assertIn("SHARE FILE:", seen[-1])
        self.assertEqual(posted[-1]["text"].split("] ", 1)[1], "The arm view is the one to see first.")
        self.assertEqual(puts, [PNG], out)
        self.assertTrue(any("shared %s from Codex archive" % RENDER in l for l in out), out)
        # not asked: no archive in his prompt, and a SHARE FILE line of his own goes nowhere
        msgs.append({"ts": "%.6f" % at(10), "user": GLORIA, "text": "how was your morning?"})
        n = len(seen)
        out = L.tick(api=api, think=lambda s, u: seen.append(s) or "Quiet. Coffee.\nSHARE FILE: %s" % RENDER,
                     now=at(10, 1), put=lambda url, data: puts.append(data))
        self.assertEqual(len(seen), n + 1, out)
        self.assertNotIn("== CODEX ARCHIVE", seen[-1])
        self.assertEqual(posted[-1]["text"].split("] ", 1)[1], "Quiet. Coffee.")
        self.assertEqual(puts, [PNG], out)

    @classmethod
    def tearDownClass(cls):
        assert not NET, NET


# Two deliveries of the same project (29 October review): the same relative paths and file names in both. A file is
# shared from the archive this turn recalled, never from the newer one that happens to have the same path.
OLD, NEW = "5a1e0c0de0000001", "5a1e0c0de0000002"
PALM = "palm-study/out/parts/palm.stl"
GUIDE_OLD, GUIDE_NEW = "palm-study/docs/guide.md", "palm-study/notes/guide.md"
SPARE = "palm-study/backup/palm.stl"
ONLY_NEW = "palm-study/out/parts/wrist.stl"
FILES = {OLD: {PALM: b"solid palm-first\nendsolid\n", GUIDE_OLD: b"# first guide\n"},
         NEW: {PALM: b"solid palm-second-cut\nendsolid\n", GUIDE_NEW: b"# second guide\n", SPARE: b"solid spare\nendsolid\n",
               ONLY_NEW: b"solid wrist\nendsolid\n"}}
TITLES = {OLD: "Palm study first cut", NEW: "Palm study second cut"}
RECEIVED = {OLD: "2026-10-20T10:00:00", NEW: "2026-10-27T10:00:00"}


def build_two():
    rows = []
    for aid, files in FILES.items():
        root = os.path.join(C.ROOT, aid)
        entries = []
        for rel, data in files.items():
            p = os.path.join(root, "files", *rel.split("/"))
            os.makedirs(os.path.dirname(p), exist_ok=True)
            put_file(p, data)
            entries.append({"path": rel, "size": len(data), "type": "3d" if rel.endswith(".stl") else "text",
                            "sha256": hashlib.sha256(data).hexdigest(), "words": "", "terms": []})
        letters = [{"message_id": "m-" + aid, "subject": "[Codex] %s" % TITLES[aid], "date": "Tue, 27 Oct 2026"}]
        put_json(os.path.join(root, "manifest.json"), {"id": aid, "title": TITLES[aid], "files": entries,
                                                       "short": ["%s: %d files" % (TITLES[aid], len(files))],
                                                       "letters": letters})
        rows.append({"id": aid, "title": TITLES[aid], "status": "archived", "files": len(files), "received": RECEIVED[aid],
                     "letters": letters, "names": [r.rsplit("/", 1)[-1].lower() for r in files]})
    put_json(C.INDEX, {"archives": rows})


class TwoArchives(unittest.TestCase):
    def setUp(self):
        os.makedirs(C.ROOT, exist_ok=True)
        build_two()

    @classmethod
    def tearDownClass(cls):
        build_archive()         # the other suites' single archive, as they left it
        assert not NET, NET

    def got(self, ref, within=None):
        found, why = C.resolve(ref, within=within)
        if not found:
            return why
        with open(found[2], "rb") as f:
            return found[0], found[1]["path"], f.read()

    def test_the_recall_names_a_verified_archive(self):
        block = D.codex_archive_block("show me archive %s" % OLD)
        self.assertTrue(block.startswith("== CODEX ARCHIVE %s" % OLD), block[:80])
        self.assertEqual(D.codex_recalled(block), OLD)
        self.assertEqual(D.codex_recalled("(Codex archives: 2 archives from Codex kept)"), "")
        self.assertEqual(D.codex_recalled("== CODEX ARCHIVE ffffffffffffffff (brought back"), "")   # not a kept one
        self.assertEqual(D.codex_recalled(""), "")

    def test_the_same_path_in_two_archives_comes_from_the_recalled_one(self):
        self.assertEqual(self.got(PALM, OLD), (OLD, PALM, FILES[OLD][PALM]))
        self.assertEqual(self.got(PALM, NEW), (NEW, PALM, FILES[NEW][PALM]))

    def test_the_same_file_name_in_two_archives_comes_from_the_recalled_one(self):
        self.assertEqual(self.got("guide.md", OLD), (OLD, GUIDE_OLD, FILES[OLD][GUIDE_OLD]))
        self.assertEqual(self.got("guide.md", NEW), (NEW, GUIDE_NEW, FILES[NEW][GUIDE_NEW]))
        self.assertEqual(self.got("palm.stl", OLD), (OLD, PALM, FILES[OLD][PALM]))      # once in the older one

    def test_a_file_name_twice_in_one_archive_is_refused(self):
        why = self.got("palm.stl", NEW)
        self.assertIsInstance(why, str)
        self.assertIn("2 files in archive %s are named palm.stl" % NEW[:8], why)
        self.assertEqual(self.got(SPARE, NEW), (NEW, SPARE, FILES[NEW][SPARE]))           # its whole path is fine

    def test_explicit_ids(self):
        self.assertEqual(self.got("%s: %s" % (NEW, PALM), OLD), (NEW, PALM, FILES[NEW][PALM]))   # the id wins
        self.assertEqual(self.got("%s:%s" % (OLD, PALM)), (OLD, PALM, FILES[OLD][PALM]))
        self.assertEqual(self.got("%s: guide.md" % OLD), (OLD, GUIDE_OLD, FILES[OLD][GUIDE_OLD]))
        self.assertIn("no kept Codex archive has the id ffffffff", self.got("ffffffff: " + PALM, OLD))

    def test_an_ambiguous_id_prefix_is_refused(self):
        for prefix in ("5a1e0c", "5a1e0c0de000000"):
            why = self.got("%s: %s" % (prefix, PALM), OLD)
            self.assertIsInstance(why, str)
            self.assertIn("fits 2 archives", why)

    def test_missing_files_are_refused_not_found_elsewhere(self):
        self.assertIn("no file %s in archive %s" % (ONLY_NEW, OLD[:8]), self.got(ONLY_NEW, OLD))   # only the newer has it
        self.assertIn("no file", self.got("wrist.stl", OLD))
        self.assertIn("no file", self.got("palm-study/out/parts/nothing.stl", NEW))
        self.assertIn("no longer kept", self.got(PALM, "0123456789abcdef"))
        for bad in ("../../manifest.json", "palm-study/../../%s/manifest.json" % NEW, "a\\b.stl", ""):
            self.assertIsNone(C.file_for(bad, within=OLD), bad)

    def test_with_no_recalled_archive_a_name_in_two_archives_is_refused(self):
        self.assertIn("is in 2 archives", self.got(PALM))
        self.assertIn("is in 2 archives", self.got("guide.md"))
        self.assertEqual(self.got(ONLY_NEW), (NEW, ONLY_NEW, FILES[NEW][ONLY_NEW]))    # one archive has it: that one
        self.assertIsNone(C.file_for(PALM))

    def test_symlinks_and_changed_files_still_refused_within_the_archive(self):
        p = os.path.join(C.ROOT, OLD, "files", *PALM.split("/"))
        os.replace(p, p + ".real"); os.symlink("/etc/hostname", p)
        try:
            self.assertIn("not a plain file", self.got(PALM, OLD))
        finally:
            os.unlink(p); os.replace(p + ".real", p)
        put_file(p, b"more", "ab")
        self.assertIn("not the size", self.got(PALM, OLD))

    def test_share_codex_file_uploads_the_recalled_archives_file_or_says_why_not(self):
        calls, puts = [], []
        def api(method, params):
            calls.append(method)
            return {"ok": True, "upload_url": "https://files.slack.invalid/up", "file_id": "F1"} if method == "files.getUploadURLExternal" else {"ok": True}
        line = D.share_codex_file(api, PALM, "C", put=lambda u, d: puts.append(d), archive=OLD)
        self.assertEqual((line, puts), ("shared %s from Codex archive %s" % (PALM, OLD[:8]), [FILES[OLD][PALM]]))
        calls.clear(); puts.clear()
        for ref, said in ((PALM, "is in 2 archives"), ("5a1e0c: " + PALM, "fits 2 archives")):
            line = D.share_codex_file(api, ref, "C", put=lambda u, d: puts.append(d))
            self.assertIn(said, line)
        self.assertIn("2 files in archive", D.share_codex_file(api, "palm.stl", "C", put=lambda u, d: puts.append(d), archive=NEW))
        self.assertIn("no file", D.share_codex_file(api, ONLY_NEW, "C", put=lambda u, d: puts.append(d), archive=OLD))
        self.assertEqual((calls, puts), ([], []))
        old_max = D.SHARE_MAX
        D.SHARE_MAX = 4
        try:
            self.assertIn("too large to share", D.share_codex_file(api, PALM, "C", put=lambda u, d: puts.append(d), archive=OLD))
        finally:
            D.SHARE_MAX = old_max
        self.assertEqual((calls, puts), ([], []))

    def test_a_lounge_turn_that_recalled_the_older_archive_shares_its_files(self):
        D.his_context = lambda: "WHO HE IS"
        L.deeper = lambda: ""
        L.work_glance = lambda: ""
        import room_work
        room_work.fixed_block = lambda: ""
        room_work.brings_up_fixed = lambda text: ""
        SELF, GLORIA = "UVINTOS", "UGLORIA"
        posted, puts, msgs = [], [], []
        def api(method, params):
            if method == "users.conversations":
                return {"ok": True, "channels": [{"id": "CLOUNGE", "name": L.NAME}]}
            if method == "auth.test": return {"ok": True, "user_id": SELF}
            if method == "conversations.history": return {"ok": True, "messages": list(reversed(msgs))}
            if method == "chat.postMessage":
                posted.append(params); return {"ok": True, "ts": "%.6f" % (max(float(m["ts"]) for m in msgs) + 1)}
            if method == "files.getUploadURLExternal": return {"ok": True, "upload_url": "https://files.slack.invalid/u", "file_id": "F9"}
            if method == "files.completeUploadExternal": return {"ok": True}
            raise AssertionError(method)
        at = lambda h, m=0: datetime(2026, 10, 29, h, m).timestamp()
        msgs.append({"ts": "%.6f" % at(8), "user": GLORIA, "text": "morning"})
        L.tick(api=api, think=lambda s, u: "NOTHING", now=at(8, 1))         # he finds the room, or lets it be
        msgs.append({"ts": "%.6f" % at(9, 5), "user": GLORIA, "text": "Can I see the palm from archive %s?" % OLD})
        seen = []
        def think(system, user):
            seen.append(system)
            return "The first palm.\nSHARE FILE: %s\nSHARE FILE: palm.stl" % PALM
        out = L.tick(api=api, think=think, now=at(9, 6), put=lambda url, data: puts.append(data))
        self.assertIn("== CODEX ARCHIVE %s" % OLD, seen[-1])
        self.assertEqual(puts, [FILES[OLD][PALM], FILES[OLD][PALM]], out)
        self.assertEqual(sum("shared %s from Codex archive %s" % (PALM, OLD[:8]) in l for l in out), 2, out)

    def test_a_dot_channel_turn_that_recalled_the_older_archive_shares_its_file(self):
        saved = {k: getattr(D, k) for k in ("kickoff_due", "ROTATION", "SCHEDULE", "atelier_line", "recall_block",
                                             "slack_lens", "study_room", "his_context")}
        D.kickoff_due = lambda *a: False
        D.ROTATION, D.SCHEDULE = ("gemma",), []
        D.atelier_line = D.recall_block = lambda: ""
        D.slack_lens = lambda lens, state: lens
        D.study_room = lambda: None
        D.his_context = lambda: "WHO HE IS"
        SELF, DOT = "UVINTOS", D.DOT
        msgs, posted, puts, n = [], [], [], [1767400000.0]
        def add(user, text):
            n[0] += 1; msgs.append({"ts": "%.6f" % n[0], "user": user, "text": text}); return "%.6f" % n[0]
        def api(method, params):
            if method == "users.conversations":
                return {"ok": True, "channels": [{"id": "CDOT", "name": "vintos-dot"}]}
            if method == "conversations.members": return {"ok": True, "members": [SELF, DOT]}
            if method == "auth.test": return {"ok": True, "user_id": SELF}
            if method == "conversations.history": return {"ok": True, "messages": list(reversed(msgs))}
            if method == "conversations.replies": return {"ok": True, "messages": [m for m in msgs if m["ts"] == params["ts"]]}
            if method == "chat.postMessage":
                posted.append(params); return {"ok": True, "ts": add(SELF, params["text"])}
            if method == "files.getUploadURLExternal": return {"ok": True, "upload_url": "https://files.slack.invalid/u", "file_id": "F9"}
            if method == "files.completeUploadExternal": return {"ok": True}
            raise AssertionError(method)
        seen = []
        def think(system, user):
            if system == D.EDITOR:
                return "KEEP"
            seen.append(system + user)
            return "The first palm, as asked.\nSHARE FILE: %s" % PALM
        try:
            D.reset(api=api, now=n[0])
            add(DOT, "Can you show the palm part from archive %s?" % OLD)
            out = D.tick(api=api, think=think, fable=lambda s, u: "", now=n[0] + 100, put=lambda url, data: puts.append(data))
        finally:
            for k, v in saved.items():
                setattr(D, k, v)
        self.assertTrue(any("== CODEX ARCHIVE %s" % OLD in s for s in seen), out)
        self.assertEqual(puts, [FILES[OLD][PALM]], out)
        self.assertTrue(any("shared %s from Codex archive %s" % (PALM, OLD[:8]) in l for l in out), out)
        self.assertNotIn("SHARE FILE", posted[-1]["text"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
