#!/usr/bin/env python3
"""Review items 275, 279, 280, 288, 307 (2026-09-10): one artifact manifest, collision-free
names, staged reflections, a failed notification that erases nothing, one delivery path
with retries and a receipt per artifact. Scratch HOME only; no network."""
import os, sys, json, tempfile, importlib.util

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
HOME = tempfile.mkdtemp(prefix="vintos-deliv-")
os.environ["HOME"] = HOME
MEM = os.path.join(HOME, ".vintos", "workspace", "memory"); os.makedirs(MEM, exist_ok=True)

R = []
def check(name, ok, detail=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + name + (("  ->  %s" % (detail,)) if (detail and not ok) else ""))
def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m

AM = load("artifact_manifest_t", os.path.join(REPO, "scripts", "artifact_manifest.py"))
DL = load("deliver_t", os.path.join(REPO, "scripts", "deliver.py"))
RS = load("reflection_stage_t", os.path.join(REPO, "scripts", "reflection_stage.py"))
DL.RECEIPTS = os.path.join(MEM, "delivery-receipts.json"); DL.SLEEP = lambda s: None
RS.MEMORY = MEM

print("\n--- 279: a second render never lands on the first ---")
shelf = os.path.join(MEM, "videos"); os.makedirs(shelf)
a = b"\x00\x00\x00\x18ftypmp42" + b"A" * 100; b = b"\x00\x00\x00\x18ftypmp42" + b"B" * 100
p1, r1 = AM.unique_path(shelf, "video-20260910-120000", ".mp4", a); open(p1, "wb").write(a)
p2, r2 = AM.unique_path(shelf, "video-20260910-120000", ".mp4", b); open(p2, "wb").write(b)
check("same stem, different bytes -> different files", p1 != p2 and os.path.exists(p1) and os.path.exists(p2), (p1, p2))
check("the name carries the content hash", AM.sha256_bytes(a)[:10] in os.path.basename(p1))
p3, r3 = AM.unique_path(shelf, "video-20260910-120000", ".mp4", a)
check("same bytes again -> revision 2, first file intact", r3 == 2 and p3 != p1 and open(p1, "rb").read() == a, (p3, r3))
q1, _ = AM.next_revision(shelf, "track", ".mp3"); open(q1, "wb").write(b"ID3x")
q2, qr = AM.next_revision(shelf, "track", ".mp3")
check("next_revision never returns an existing path", q2 != q1 and qr == 2)

print("\n--- 275: one manifest shape on every record ---")
png = os.path.join(shelf, "keyframe.png"); open(png, "wb").write(b"\x89PNG\r\n\x1a\n" + b"x" * 40)
rec = {"image": "keyframe.png", "prompt": "a window", "timestamp": "t"}
rec.update(AM.build(png, "image", source_want="w-1", revision=1, shelf=shelf))
check("all manifest fields present", all(k in rec for k in AM.MANIFEST_FIELDS), sorted(set(AM.MANIFEST_FIELDS) - set(rec)))
check("legacy keys untouched", rec["image"] == "keyframe.png" and rec["prompt"] == "a window")
check("validated by magic bytes", rec["validated"].get("ok") and "png" in str(rec["validated"].get("how")), rec["validated"])
check("sha256 and bytes are of the file", rec["sha256"] == AM.sha256_file(png) and rec["bytes"] == os.path.getsize(png))
check("delivery and shared start empty", rec["delivery"] is None and rec["shared"] is None)
check("problems() is empty for a good record", AM.problems(rec) == [], AM.problems(rec))
old = {"image": "old.png", "prompt": "before the manifest"}
check("a record without the fields still reads (normalize fills, does not raise)", isinstance(AM.normalize(dict(old)), dict))
check("find_record by legacy key", AM.find_record([old, rec], "old.png") is old and AM.find_record([old, rec], "keyframe.png") is rec)
try:
    AM.build(png, "hologram"); check("unknown medium refused", False)
except ValueError:
    check("unknown medium refused", True)

print("\n--- 288: a failed send leaves the artifact and never implies reception ---")
AM.mark_delivery(rec, "failed", why="ntfy 503")
check("delivery=failed, file and record kept", rec["delivery"]["state"] == "failed" and os.path.exists(png) and rec["sha256"], rec["delivery"])
check("a failed send does not set shared", rec["shared"] is None)
try:
    AM.mark_delivery(rec, "acknowledged"); check("a send cannot mark acknowledged", False)
except ValueError:
    check("a send cannot mark acknowledged", True)
AM.mark_delivery(rec, "sent", channel="ntfy")
check("sent sets shared, not acknowledged", rec["delivery"]["state"] == "sent" and rec["shared"]["where"] == "ntfy")
AM.mark_acknowledged(rec, evidence="she replied 'that one'")
check("acknowledged only with reception evidence", rec["delivery"]["state"] == "acknowledged" and "replied" in rec["delivery"]["evidence"])

print("\n--- 307: one delivery path, bounded retry, one receipt per artifact ---")
posts = []
codes = iter([503, 500, 200])
def fake_post(url, data, headers, timeout):
    posts.append((url, data, dict(headers))); return next(codes)
DL.POST = fake_post; DL.CHANNELS["ntfy"] = "http://ntfy.test/topic"
rc = DL.deliver("video-1.mp4", "ntfy", "I made you something.", click="http://x/v", attach="http://x/v", authority=lambda: (True, ""))
check("retried through two failures to a send", rc["state"] == "sent" and rc["attempts"] == 3, rc)
check("the notification carried click and attach", posts[-1][2].get("Click") == "http://x/v" and posts[-1][2].get("Attach") == "http://x/v")
n = len(posts)
rc2 = DL.deliver("video-1.mp4", "ntfy", "I made you something.", authority=lambda: (True, ""))
check("a repeat call does not resend", len(posts) == n and rc2.get("repeat") is True and rc2["state"] == "sent", rc2)
rc3 = DL.deliver("video-2.mp4", "ntfy", "x", authority=lambda: (False, "his decision was NO"))
check("authority saying no -> failed, nothing posted", rc3["state"] == "failed" and len(posts) == n and "refused" in rc3["why"], rc3)
rc4 = DL.deliver("video-3.mp4", "ntfy", "x")
check("no authority -> refused", rc4["state"] == "failed" and len(posts) == n)
codes = iter([500, 500, 500])
rc5 = DL.deliver("video-4.mp4", "ntfy", "x", authority=lambda: True)
check("all attempts fail -> failed receipt with the last reason", rc5["state"] == "failed" and rc5["attempts"] == 3 and "500" in rc5["why"], rc5)
codes = iter([200])
rc6 = DL.deliver("video-4.mp4", "ntfy", "x", authority=lambda: True)
check("a failed receipt may be retried later", rc6["state"] == "sent")
recs = DL.load_receipts()
check("receipts keyed by artifact@channel", "video-1.mp4@ntfy" in recs and "video-4.mp4@ntfy" in recs, list(recs))
ack = DL.acknowledge("video-1.mp4", "ntfy", evidence="she opened it")
check("acknowledge needs evidence and is the only path to acknowledged", ack["state"] == "acknowledged")
try:
    DL.acknowledge("video-1.mp4", "ntfy", ""); check("empty evidence refused", False)
except ValueError:
    check("empty evidence refused", True)

print("\n--- 280: a reflection survives the step that fails after it ---")
k = RS.key_for("decision", "2026-09-10", "a window at dusk")
check("no stage pending at first", RS.load("video-send", k) is None)
RS.save("video-send", k, {"decision": "YES", "prompt": "a window at dusk"}, note="his YES")
check("saved stage is pending", RS.load("video-send", k) == {"decision": "YES", "prompt": "a window at dusk"})
check("pending() lists it", [x[0] for x in RS.pending("video-send")] == [k])
check("an expired stage is not replayed", RS.load("video-send", k, max_age_hours=1, now=__import__("time").time() + 7200) is None)
RS.done("video-send", k, outcome="video-1.mp4")
check("done consumes it", RS.load("video-send", k) is None and RS.pending("video-send") == [])
srec = json.load(open(RS._path("video-send", k)))
check("the consumed stage is kept for the record", srec["state"] == "consumed" and srec["outcome"] == "video-1.mp4")

print("\n--- the writers use the helpers ---")
for f, needles in (("bin/vintos-send-video.py", ("artifact_manifest", "reflection_stage", "deliver")),
                   ("bin/vintos-video.py", ("artifact_manifest",)),
                   ("scripts/dream-art.py", ("artifact_manifest",))):
    src = open(os.path.join(REPO, f)).read()
    check("%s imports %s" % (f, ", ".join(needles)), all(n in src for n in needles))
check("dream-art twins identical", open(os.path.join(REPO, "scripts", "dream-art.py"), "rb").read() == open(os.path.join(REPO, "bin", "dream-art.py"), "rb").read())
check("nothing sent to the real ntfy", all(u == "http://ntfy.test/topic" for u, _, _ in posts))

print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
