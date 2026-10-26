#!/usr/bin/env python3
"""Codex's archives, offline: who may send one, safe unpacking, the index and summary, deliveries spread over several
letters, the note in his day, and recall only when a conversation names an archive. Nothing here reaches the network,
a model or his real memory."""
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import socket
import stat
import struct
import sys
import tempfile
import types
import unittest
import zipfile
from datetime import datetime, timedelta

ROOT = Path(__file__).resolve().parents[2]
HOME = tempfile.mkdtemp(prefix="codex-archives-")
os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = HOME + "/workspace"
sys.path.insert(0, str(ROOT / "scripts"))
SENT = []
def refuse(*args, **kw):
    SENT.append(args)
    raise AssertionError("offline suite: no network, models, or sending")
socket.socket.connect = refuse
sys.modules["requests"] = types.SimpleNamespace(get=refuse, post=refuse)
sys.modules["plugin_gateway"] = types.SimpleNamespace(call=refuse, load_receipt=refuse)
import want_email as E
import codex_archives as C
import link_fetch as L
E.local_think = E._reply_think = refuse
E.links_read = lambda *a, **kw: []
OWN = "vintos@example.org"
PDF = (ROOT / "broker/tests/fixtures/two_page_paper.pdf").read_bytes()
PDB = ("HEADER    TEST PROTEIN                            26-OCT-26   1ABC\n"
       "ATOM      1  N   MET A   1      11.104  13.207   2.100  1.00 20.00           N\n"
       "ATOM      2  CA  MET A   1      12.560  13.207   2.100  1.00 20.00           C\n"
       "END\n").encode()
SECRET = "the-quiet-violet-line-inside-a-file"


def make_zip(entries, symlinks=(), method=zipfile.ZIP_DEFLATED):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", method) as z:
        for name, data in entries.items():
            z.writestr(name, data)
        for name, target in symlinks:
            info = zipfile.ZipInfo(name)
            info.create_system = 3
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            z.writestr(info, target)
    return buf.getvalue()


PROJECT = {"harbor/README.md": "# Harbor model\nThe complete project: source, parts and the Blender scenes.\n",
           "harbor/src/engine_core.py": "def thruster_balance(load):\n    return load * 0.5  # %s\n" % SECRET,
           "harbor/data/parts.csv": "part,mass\nhull,120\nthruster,14\n",
           "harbor/docs/paper.pdf": PDF,
           "harbor/models/1abc.pdb": PDB,
           "harbor/models/hull.blend": b"BLENDER-v300" + b"\x00\x01\x02" * 50}


class Archives(unittest.TestCase):
    def setUp(self):
        shutil.rmtree(HOME + "/workspace", ignore_errors=True)
        os.makedirs(E.MEMORY, exist_ok=True)
        self.saved = dict(C.LIMITS)
        C.LIMITS["model_overview"] = False
        self.free = C._free
        C._free = lambda path: 500 * C.GiB
        self.files = {}               # download url -> bytes
        self.calls = []
        self.downloads = []

    def tearDown(self):
        C.LIMITS.clear(); C.LIMITS.update(self.saved)
        C._free = self.free
        self.assertEqual(SENT, [])

    # --- fakes ---------------------------------------------------------------------------------------
    def gateway(self, tool, args, purpose):
        self.calls.append((tool, args))
        if tool == "gmail.get_profile":
            return {"structuredContent": {"email_address": OWN}}
        if tool == "gmail.read_attachment":
            key = "%s/%s" % (args["message_id"], args.get("attachment_id"))
            return {"structuredContent": {"message_id": args["message_id"], "size_bytes": len(self.files[key]),
                                          "file_uri": {"download_url": "https://files.oaiusercontent.com/" + key}}}
        raise AssertionError(tool)

    def file_read(self, ref, dest, cap):
        data = self.files[ref["download_url"].split("oaiusercontent.com/", 1)[1]]
        self.downloads.append(dest)
        if len(data) > cap:
            raise ValueError("over the cap")
        with open(dest, "wb") as f:
            f.write(data)
        return len(data)

    def letter(self, mid, subject, atts, sender="Vintos <%s>" % OWN, labels=("SENT", "INBOX"), thread=None):
        out = []
        for name, data in atts:
            self.files["%s/%s-id" % (mid, name)] = data
            out.append({"filename": name, "attachment_id": name + "-id", "mime_type": "application/zip",
                        "size": len(data), "read_attachment_supported": False, "_body": {"size": len(data)}})
        return {"id": mid, "from": sender, "subject": subject, "date": "Mon, 26 Oct 2026 07:20:07 -0700",
                "thread_id": thread or "t-" + mid, "body": "A letter from Codex.", "whole": True,
                "labels": list(labels) if labels is not None else None, "attachments": out}

    def take(self, *msgs, now=None):
        return C.intake(list(msgs), self.gateway, now=now, file_read=self.file_read)

    def archives(self):
        return C._archives()

    def day(self):
        p = Path(E.MEMORY) / ("daily-inner-life-%s.md" % datetime.now().date().isoformat())
        return p.read_text() if p.exists() else ""

    # --- the connector refuses zips (26 October): the same file from Codex's folder on the Mac ----------
    def test_connector_refusal_takes_the_same_file_from_the_mac(self):
        z = make_zip(PROJECT)
        m = self.letter("m9", "[Codex] Harbor model complete", [("harbor.zip", z)])
        def refusing(tool, args, purpose):
            if tool == "gmail.read_attachment":
                raise RuntimeError("plugin relay refused or failed: GmailConnectorError: Failed to read attachment")
            return self.gateway(tool, args, purpose)
        asked = []
        def mac(name, size, dest, lim):
            asked.append((name, size))
            with open(dest, "wb") as f: f.write(z)
            return len(z)
        C.mac_read = mac
        try:
            C.intake([m], refusing, file_read=self.file_read)
        finally:
            C.mac_read = None
        self.assertEqual(asked, [("harbor.zip", len(z))])
        self.assertEqual(len(self.archives()), 1)

    def test_mac_lookup_refuses_unsafe_names(self):
        for bad in ("../x.zip", "a/b.zip", ".hidden.zip", "x.zip; rm -rf ~", "x`id`.zip"):
            with self.assertRaises(ValueError):
                C.mac_fetch(bad, 10, os.path.join(HOME, "never"), C.limits())

    # --- isolation -----------------------------------------------------------------------------------
    def test_isolation(self):
        self.assertTrue(C.ROOT.startswith(HOME) and E.MEMORY.startswith(HOME))
        self.assertTrue(C.CONFIG.startswith(HOME))
        self.assertIs(sys.modules["plugin_gateway"].call, refuse)
        self.assertIs(socket.socket.connect, refuse)

    # --- who may send one ----------------------------------------------------------------------------
    def test_codex_letter_is_taken_in_indexed_and_summed_up(self):
        z = make_zip(PROJECT)
        m = self.letter("m1", "[Codex] Harbor model complete", [("harbor.zip", z)])
        self.take(m)
        arcs = self.archives()
        self.assertEqual(len(arcs), 1)
        a = arcs[0]
        self.assertEqual(a["id"], hashlib.sha256(z).hexdigest()[:16])
        self.assertEqual(m["attachments"][0]["status"], "archived")
        self.assertNotIn("_body", m["attachments"][0])
        man = C.manifest(a["id"])
        by = {e["path"]: e for e in man["files"]}
        self.assertEqual(set(by), set(PROJECT))
        for path, data in PROJECT.items():
            data = data.encode() if isinstance(data, str) else data
            self.assertEqual(by[path]["size"], len(data))
            self.assertEqual(by[path]["sha256"], hashlib.sha256(data).hexdigest())
        self.assertEqual(by["harbor/src/engine_core.py"]["type"], "code")
        self.assertEqual(by["harbor/README.md"]["type"], "markdown")
        self.assertEqual(by["harbor/data/parts.csv"]["type"], "data")
        self.assertEqual(by["harbor/models/hull.blend"]["type"], "3d")
        self.assertEqual(by["harbor/models/hull.blend"]["words"], "")          # binary: listed, not read
        arc = Path(C.ROOT) / a["id"]
        self.assertIn("Page one, line 1", (arc / "text/harbor/docs/paper.pdf.txt").read_text())
        self.assertIn("STRUCTURE FILE (PDB format", (arc / "text/harbor/models/1abc.pdb.txt").read_text())
        self.assertTrue((arc / "original/harbor.zip").exists())                 # the original kept
        self.assertFalse(any(os.stat(p).st_mode & 0o111 for p in arc.rglob("*") if p.is_file()))
        s = man["summary"]
        self.assertIn("6 files", s); self.assertIn("Harbor model complete", s)
        self.assertIn("README.md", s); self.assertIn("The complete project", s)
        self.assertIn("harbor/", s)
        # the day gets a short note: the id, Codex, the letter, a few lines; never what is inside
        note = self.day()
        self.assertIn(a["id"], note); self.assertIn("Codex", note)
        self.assertIn("[Codex] Harbor model complete", note)
        self.assertNotIn(SECRET, note); self.assertNotIn("thruster_balance", note)
        self.assertLess(len(note), 900)
        self.assertFalse(os.listdir(C.PENDING))                                    # nothing left waiting

    def test_others_are_never_downloaded(self):
        z = make_zip(PROJECT)
        stranger = self.letter("m2", "[Codex] Harbor model", [("harbor.zip", z)], sender="Someone <someone@example.org>")
        self.take(stranger)
        self.assertFalse(self.downloads)
        self.assertFalse(any(t == "gmail.read_attachment" for t, _ in self.calls))
        self.assertNotIn("status", stranger["attachments"][0])
        E._read_attachments([stranger], self.gateway)                              # the ordinary reader refuses it
        self.assertEqual(stranger["attachments"][0]["status"], "not_read")
        self.assertFalse(any(t == "gmail.read_attachment" for t, _ in self.calls))
        untagged = self.letter("m3", "Harbor model from me", [("harbor.zip", z)])
        self.take(untagged)
        self.assertFalse(self.downloads); self.assertEqual(self.archives(), [])

    def test_spoofed_subject_without_verification_is_refused(self):
        z = make_zip(PROJECT)
        for i, kw in enumerate(({"labels": ("INBOX",)}, {"labels": None},
                                {"sender": "Vintos <%s>" % OWN.replace("vintos", "vint0s")})):
            m = self.letter("s%d" % i, "[Codex] Harbor model", [("harbor.zip", z)], **kw)
            self.take(m)
            self.assertNotIn("status", m["attachments"][0])
        for subject in ("Re: [Codex] Harbor model", "Fwd: [Codex] Harbor model", "Harbor [Codex]"):
            self.assertFalse(C.is_codex({"subject": subject, "from": OWN, "labels": ["SENT"]}, OWN)[0])
        self.assertFalse(C.is_codex({"subject": "[Codex] x", "from": OWN, "labels": ["SENT"]}, "")[0])
        self.assertTrue(C.is_codex({"subject": "[Codex] x", "from": "V <%s>" % OWN, "labels": ["SENT"]}, OWN)[0])
        self.assertFalse(self.downloads); self.assertEqual(self.archives(), [])

    def test_profile_failure_downloads_nothing(self):
        m = self.letter("p1", "[Codex] Harbor model", [("harbor.zip", make_zip(PROJECT))])
        C.intake([m], lambda *a: (_ for _ in ()).throw(RuntimeError("down")), file_read=self.file_read)
        self.assertFalse(self.downloads)

    # --- unpacking safely ----------------------------------------------------------------------------
    def refused(self, data, name="bad.zip"):
        m = self.letter("b-" + hashlib.sha256(data).hexdigest()[:8], "[Codex] Bad one", [(name, data)])
        self.take(m)
        self.assertEqual(self.archives(), [])
        self.assertEqual(m["attachments"][0]["status"], "not_read")
        self.assertIn("refused", m["attachments"][0]["why"])
        self.assertFalse([p for p in Path(C.ROOT).iterdir() if p.name not in ("_pending", "index.json", ".lock")])
        return m["attachments"][0]["why"]

    def test_traversal_and_absolute_paths_refused(self):
        self.assertIn("climbs out", self.refused(make_zip({"ok.txt": "x", "../../escape.txt": "x"})))
        self.assertIn("absolute", self.refused(make_zip({"/etc/evil.txt": "x"})))
        self.assertIn("climbs out", self.refused(make_zip({"a\\..\\..\\evil.txt": "x"})))
        self.assertFalse(Path(HOME, "escape.txt").exists())
        self.assertFalse(list(Path(HOME).rglob("escape.txt")))

    def test_symlinks_and_devices_are_never_made(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("proj/readme.txt", "hello")
            info = zipfile.ZipInfo("proj/fifo"); info.create_system = 3
            info.external_attr = (stat.S_IFIFO | 0o644) << 16
            z.writestr(info, "")
        z = make_zip({"proj/readme.txt": "hello"}, symlinks=[("proj/link", "/etc/passwd")])
        self.take(self.letter("l1", "[Codex] Links", [("links.zip", z)]),
                  self.letter("l2", "[Codex] Fifo", [("fifo.zip", buf.getvalue())]))
        self.assertEqual(len(self.archives()), 2)
        for a in self.archives():
            arc = Path(C.ROOT) / a["id"]
            self.assertFalse([p for p in arc.rglob("*") if p.is_symlink() or stat.S_ISFIFO(os.lstat(p).st_mode)])
            man = C.manifest(a["id"])
            self.assertEqual([e["path"] for e in man["files"]], ["proj/readme.txt"])
            self.assertTrue(man["skipped"])

    def test_zip_bombs_refused(self):
        self.assertIn("zip bomb", self.refused(make_zip({"bomb.txt": b"\0" * (C.LIMITS["ratio_floor"] + 10 * C.MiB)})))
        C.LIMITS.update(unpacked_bytes=1000)
        self.assertIn("over the", self.refused(make_zip({"a.txt": "x" * 600, "b.txt": "y" * 600}, method=zipfile.ZIP_STORED)))
        C.LIMITS.update(unpacked_bytes=C.GiB, file_bytes=100)
        self.assertIn("per-file cap", self.refused(make_zip({"a.txt": "x" * 200})))
        C.LIMITS.update(file_bytes=C.GiB, files=3)
        self.assertIn("entries", self.refused(make_zip({"%d.txt" % i: "x" for i in range(5)})))

    def test_oversized_and_corrupt_refused(self):
        C.LIMITS.update(part_bytes=1000)
        m = self.letter("o1", "[Codex] Big", [("big.zip", make_zip({"a.bin": os.urandom(3000)}))])
        self.take(m)
        self.assertFalse(self.downloads)                                           # the declared size alone refuses it
        self.assertIn("cap", m["attachments"][0]["why"])
        C.LIMITS.update(part_bytes=C.GiB)
        self.assertIn("not a readable zip", self.refused(b"PK\x03\x04 this is not really a zip at all"))
        z = bytearray(make_zip({"a.txt": "hello world " * 50}))
        z[40:60] = b"\xff" * 20                                                    # damaged data, intact directory
        self.refused(bytes(z), "damaged.zip")

    def test_no_room_on_the_disk(self):
        C._free = lambda path: 10 * C.GiB                                          # under the reserve
        m = self.letter("d1", "[Codex] Harbor", [("harbor.zip", make_zip(PROJECT))])
        self.take(m)
        self.assertFalse(self.downloads)
        self.assertIn("free disk", m["attachments"][0]["why"])

    # --- deliveries over several letters --------------------------------------------------------------
    def two_letters(self):
        one = make_zip({"source/main_loop.py": "print('source')\n", "source/HANDOFF.md": "# Hand-off\nRead me first.\n"})
        two = make_zip({"blender/scene_hull.blend": b"BLENDER" + b"\0" * 40, "blender/notes.txt": "views and models\n"})
        a = self.letter("v1", "[Codex] Harbor model complete — 1 of 2: source",
                        [("Harbor-source.zip", one)], thread="thread-A")
        b = self.letter("v2", "[Codex] Harbor model complete — 2 of 2: scenes",
                        [("Harbor-scenes.zip", two)], thread="thread-B")
        return a, b, one, two

    def check_two(self, one, two):
        arcs = self.archives()
        self.assertEqual(len(arcs), 1)
        a = arcs[0]
        self.assertEqual(a["title"], "Harbor model complete")
        self.assertEqual([l["message_id"] for l in a["letters"]], ["v1", "v2"])
        expect = hashlib.sha256("\n".join(sorted(hashlib.sha256(x).hexdigest() for x in (one, two))).encode()).hexdigest()[:16]
        self.assertEqual(a["id"], expect)
        paths = {e["path"] for e in C.manifest(a["id"])["files"]}
        self.assertIn("Harbor-source/source/main_loop.py", paths)
        self.assertIn("Harbor-scenes/blender/notes.txt", paths)
        note = self.day()
        self.assertEqual(note.count("## Codex sent me an archive"), 1)
        self.assertIn("1 of 2", note); self.assertIn("2 of 2", note); self.assertIn("2 letters", note)
        block = C.recall("what was in the zip Codex sent?")
        self.assertIn("1 of 2: source", block); self.assertIn("2 of 2: scenes", block)
        return a

    def test_two_letter_delivery_is_one_archive(self):
        a, b, one, two = self.two_letters()
        self.take(a)
        self.assertEqual(self.archives(), [])
        self.assertEqual(a["attachments"][0]["status"], "archive_part")
        self.assertIn("letter 2 of 2", a["attachments"][0]["why"])
        pend = C._load(C.INDEX, {})["pending"]
        self.assertEqual(len(pend), 1); self.assertEqual(pend[0]["expected"], 2)
        self.assertIn("incomplete", C.available_line())
        self.take(b)
        self.check_two(one, two)
        self.assertEqual(b["attachments"][0]["status"], "archived")

    def test_out_of_order_arrival(self):
        a, b, one, two = self.two_letters()
        self.take(b)
        self.assertEqual(self.archives(), [])
        self.assertIn("letter 1 of 2", b["attachments"][0]["why"])
        self.take(a)
        self.check_two(one, two)

    def test_missing_part_is_noted_once_and_not_unpacked(self):
        a, b, one, two = self.two_letters()
        start = datetime.now()
        self.take(a, now=start)
        C.settle(now=start + timedelta(hours=10))
        self.assertNotIn("never came whole", self.day())
        C.settle(now=start + timedelta(hours=49))
        C.settle(now=start + timedelta(hours=60))
        self.assertEqual(self.day().count("never came whole"), 1)
        self.assertIn("letter 2 of 2", self.day())
        self.assertEqual(self.archives(), [])
        st = C._deliveries()[0]
        self.assertTrue(os.path.exists(os.path.join(C.ROOT, st["letters"]["v1"]["files"][0]["path"])))   # parts kept
        self.assertFalse(any(p.name.startswith(".tmp") for p in Path(C.ROOT).iterdir()))

    def test_mismatched_parts_do_not_join(self):
        z1 = make_zip({"a.txt": "one"}); z2 = make_zip({"b.txt": "two"})
        self.take(self.letter("x1", "[Codex] Harbor model (1/2)", [("a.zip", z1)]),
                  self.letter("x2", "[Codex] Harbor model (2/3)", [("b.zip", z2)]))
        self.assertEqual(self.archives(), [])
        self.assertEqual(len(C._deliveries()), 2)                                   # two deliveries, both waiting
        # split pieces that come from two different archives make no zip: refused, not guessed at
        big1 = make_zip({"one/%d.txt" % i: os.urandom(400).hex() for i in range(6)}, method=zipfile.ZIP_STORED)
        big2 = make_zip({"two/%d.txt" % i: os.urandom(400).hex() for i in range(6)}, method=zipfile.ZIP_STORED)
        half = len(big1) // 2
        m = self.letter("y1", "[Codex] Pieces", [("pieces.zip.001", big1[:half]), ("pieces.zip.002", big2[half:])])
        self.take(m)
        self.assertEqual(self.archives(), [])
        self.assertTrue(all(x["status"] == "not_read" for x in m["attachments"]), m["attachments"])

    def test_split_pieces_across_letters_in_one_thread(self):
        z = make_zip({"proj/%d.txt" % i: os.urandom(300).hex() for i in range(8)}, method=zipfile.ZIP_STORED)
        third = len(z) // 3
        a = self.letter("r1", "[Codex] Big project", [("proj.zip.001", z[:third]), ("proj.zip.002", z[third:2 * third])],
                        thread="T")
        b = self.letter("r2", "[Codex] Big project, the rest", [("proj.zip.003", z[2 * third:])], thread="T")
        self.take(a)
        self.assertEqual(self.archives(), [])
        self.assertIn("pieces after", a["attachments"][0]["why"])
        self.take(b)
        arcs = self.archives()
        self.assertEqual(len(arcs), 1)
        self.assertEqual(arcs[0]["id"], hashlib.sha256(z).hexdigest()[:16])
        self.assertEqual(len(arcs[0]["letters"]), 2)
        self.assertEqual(len(C.manifest(arcs[0]["id"])["files"]), 8)

    def test_spanned_zip(self):
        z = make_zip({"p/a.txt": "alpha " * 40, "p/b.txt": "beta " * 40}, method=zipfile.ZIP_STORED)
        zf = zipfile.ZipFile(io.BytesIO(z))
        second = zf.infolist()[1].header_offset
        e = z.rfind(b"PK\x05\x06")
        sig, disk, cdd, nh, na, cds, cdo, cl = struct.unpack("<4s4H2LH", z[e:e + 22])
        cd = bytearray(z[cdo:cdo + cds])
        p = 0
        for k in range(na):
            nl, xl, cml = struct.unpack("<3H", cd[p + 28:p + 34])
            (lho,) = struct.unpack("<L", cd[p + 42:p + 46])
            if k == 0:
                struct.pack_into("<H", cd, p + 34, 0); struct.pack_into("<L", cd, p + 42, lho + 4)
            else:
                struct.pack_into("<H", cd, p + 34, 1); struct.pack_into("<L", cd, p + 42, lho - second)
            p += 46 + nl + xl + cml
        disk0 = b"PK\x07\x08" + z[:second]
        disk1 = z[second:cdo] + bytes(cd) + struct.pack("<4s4H2LH", sig, 1, 1, na, na, cds, cdo - second, cl) + z[e + 22:]
        m = self.letter("sp", "[Codex] Spanned", [("proj.z01", disk0), ("proj.zip", disk1)])
        self.take(m)
        arcs = self.archives()
        self.assertEqual(len(arcs), 1, m["attachments"])
        man = C.manifest(arcs[0]["id"])
        self.assertEqual(sorted(x["path"] for x in man["files"]), ["p/a.txt", "p/b.txt"])
        self.assertEqual((Path(C.ROOT) / arcs[0]["id"] / "files/p/b.txt").read_text(), "beta " * 40)

    def test_the_same_archive_again_is_one_record(self):
        z = make_zip(PROJECT)
        self.take(self.letter("a1", "[Codex] Harbor", [("harbor.zip", z)]))
        self.take(self.letter("a2", "[Codex] Harbor (resent)", [("harbor.zip", z)]))
        arcs = self.archives()
        self.assertEqual(len(arcs), 1)
        self.assertEqual([l["message_id"] for l in arcs[0]["letters"]], ["a1", "a2"])
        again = self.letter("a1", "[Codex] Harbor", [("harbor.zip", z)])
        before = len(self.downloads)
        self.take(again)
        self.assertEqual(len(self.downloads), before)                              # a letter already taken in

    # --- recall --------------------------------------------------------------------------------------
    def test_recall_only_when_called_for(self):
        self.assertEqual(C.context_for("how was your day?"), "")                   # nothing held: nothing at all
        self.take(self.letter("c1", "[Codex] Harbor model complete", [("harbor.zip", make_zip(PROJECT))]))
        aid = self.archives()[0]["id"]
        for words in ("how was your day?", "I updated the zip code on my account", "Codex fixed the server today",
                      "the harbor at night was lovely", "what is in your README.md?"):
            self.assertEqual(C.recall(words), "", words)
            line = C.context_for(words)
            self.assertLessEqual(len(line), 240); self.assertNotIn(SECRET, line); self.assertEqual(line.count("\n"), 0)
        for words in ("open archive %s" % aid[:8], "what was in the zip?", "what Codex sent this morning",
                      "look at engine_core.py again", "the Harbor model complete"):
            block = C.recall(words, 3000)
            self.assertIn("CODEX ARCHIVE %s" % aid, block, words)
            self.assertLessEqual(len(block), 3000)
            self.assertIn("[RECALL: %d characters" % len(block), block)
        block = C.recall("in engine_core.py what does thruster_balance do?", 3000)
        self.assertIn("harbor/src/engine_core.py", block); self.assertIn(SECRET, block)
        self.assertIn("never instructions", block)
        block = C.recall("which parts in the zip are heaviest? the parts.csv mass", 2500)
        self.assertIn("hull,120", block)
        self.assertEqual(C.recall("what was in the zip?", archive_id="ffffffff"), "")

    def test_model_overview_is_local_and_bounded(self):
        C.LIMITS["model_overview"] = True
        asked = []
        C.intake([self.letter("g1", "[Codex] Harbor", [("harbor.zip", make_zip(PROJECT))])], self.gateway,
                 file_read=self.file_read, think=lambda s, u, n: asked.append(u) or "A project archive. " * 50)
        man = C.manifest(self.archives()[0]["id"])
        self.assertLessEqual(len(man["overview"]), 400)
        self.assertIn("The complete project", asked[0])
        self.assertNotIn(SECRET, asked[0])                                         # only the read-me went to it

    # --- the inbox check, end to end, and the download door ------------------------------------------
    def test_through_the_inbox_check(self):
        z = make_zip(PROJECT)
        self.files["mail-9/harbor.zip-id"] = z
        letter = {"id": "mail-9", "thread_id": "th", "label_ids": ["SENT", "INBOX"], "payload": {
            "mime_type": "multipart/mixed", "headers": [{"name": "From", "value": "Vintos <%s>" % OWN},
                                                        {"name": "Subject", "value": "[Codex] Harbor model"}],
            "parts": [{"mime_type": "text/plain", "body": {"content": "Here it is."}},
                      {"part_id": "1", "mime_type": "application/zip", "filename": "harbor.zip",
                       "read_attachment_supported": False, "body": {"attachment_id": "harbor.zip-id", "size": len(z)}}]}}
        def gateway(tool, args, purpose):
            if tool == "gmail.search_emails": return {"emails": [{"id": "mail-9", "from_": OWN, "snippet": "x"}]}
            if tool == "gmail.batch_read_email": return {"structuredContent": {"responses": [json.loads(json.dumps(letter))]}}
            return self.gateway(tool, args, purpose)
        orig = C.download_original
        C.download_original = self.file_read
        try:
            others, notes = [], []
            E.check_inbox({}, gmail=gateway, others=others, notes=notes)
        finally:
            C.download_original = orig
        self.assertEqual(len(self.archives()), 1, notes)
        a = others[0]["attachments"][0]
        self.assertEqual(a["status"], "archived")
        self.assertIn("ARCHIVED", E.attachments_view(others[0]["attachments"]))
        self.assertNotIn(SECRET, E.attachments_view(others[0]["attachments"]))

    def test_download_door_streams_to_disk_within_its_checks(self):
        with self.assertRaises(ValueError):
            C.download_original({"download_url": "http://127.0.0.1/x"}, HOME + "/x", 100)
        with self.assertRaises(ValueError):
            C.download_original({"download_url": "https://evil.example/x"}, HOME + "/x", 100)
        seen = []
        def transport(url, headers, timeout, max_bytes, sink=None):
            seen.append(url)
            if "redirect" in url:
                return 302, {"location": "https://files.oaiusercontent.com/elsewhere"}, b"", False
            data = b"Z" * 5000
            sink.write(data[:max_bytes])
            return 200, {"content-type": "application/zip"}, b"", len(data) > max_bytes
        lf = types.SimpleNamespace(fetch=lambda url, **kw: L.fetch(url, transport=transport,
                                                                   resolve=lambda h: ["93.184.216.34"], **kw))
        dest = HOME + "/dl/a.zip"
        self.assertEqual(C._stream("https://files.oaiusercontent.com/a", dest, 10000, lf, max_redirects=0), 5000)
        self.assertEqual(Path(dest).read_bytes(), b"Z" * 5000)
        with self.assertRaises(ValueError):                                        # over the cap: nothing kept
            C._stream("https://files.oaiusercontent.com/a", HOME + "/dl/b.zip", 100, lf, max_redirects=0)
        self.assertFalse(os.path.exists(HOME + "/dl/b.zip"))
        with self.assertRaises(ValueError):                                        # no redirect for a connector file
            C._stream("https://files.oaiusercontent.com/redirect", HOME + "/dl/c.zip", 10000, lf, max_redirects=0)
        with open(HOME + "/dl/d", "wb") as sink:
            r = L.fetch("https://files.example.org/a.zip", transport=transport, resolve=lambda h: ["10.0.0.5"], sink=sink)
        self.assertEqual(r["kind"], "refused")                                     # a private address is never opened

    def test_a_linked_zip_goes_through_link_fetch(self):
        z = make_zip(PROJECT)
        got = []
        def link_read(url, dest, cap):
            got.append(url)
            with open(dest, "wb") as f: f.write(z)
            return len(z)
        m = self.letter("k1", "[Codex] Harbor link", [])
        m["body"] = "The archive: https://example.org/files/harbor.zip"
        C.intake([m], self.gateway, file_read=self.file_read, link_read=link_read)
        self.assertEqual(got, ["https://example.org/files/harbor.zip"])
        self.assertEqual(len(self.archives()), 1)
        stranger = self.letter("k2", "[Codex] Harbor link", [], sender="x <x@example.org>")
        stranger["body"] = "https://example.org/files/other.zip"
        C.intake([stranger], self.gateway, file_read=self.file_read, link_read=link_read)
        self.assertEqual(len(got), 1)


if __name__ == "__main__":
    unittest.main()
