#!/usr/bin/env python3
"""The fault sweep now sees a cron job that crashed in its own log.

A cron job that dies writes a Python traceback to the end of its log and nothing structured, so the sweep never
saw it (the JEPA ranking audit died daily for a month unnoticed). A log that ends in a fresh crash is a finding;
one whose last run was clean, or whose crash is old, is not. No network, scratch HOME.
"""
import os, socket, sys, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="fault-cron-"); os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")
socket.socket.connect = lambda self, *a, **k: (_ for _ in ()).throw(OSError("this suite reaches nothing"))
sys.path.insert(0, os.path.join(REPO, "scripts"))
import fault_sweep as F

R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + ("" if ok else "  ->  %r" % (d,)))

LOGS = os.path.join(HOME, "logs"); os.makedirs(LOGS)
F.LOGDIR = LOGS
NOW = time.time()
def write(name, text, age_s=60):
    p = os.path.join(LOGS, name)
    with open(p, "w") as f: f.write(text)
    os.utime(p, (NOW - age_s, NOW - age_s))
    return p

write("jepa-ranking.log", "run start\n[audit] computing centroid\nTraceback (most recent call last):\n"
      '  File "jepa_ranking_audit.py", line 89, in _centroid\n    v = np.mean(rows, axis=0)\nValueError: need at least one array\n')
write("send-video.log", "building clip\nUnboundLocalError: cannot access local variable 'body'\n")
write("music.log", "composing\nModuleNotFoundError: No module named 'store_guard'\n")
write("journal.log", "[journal] wrote today's entry\n[journal] done, 1 thread seeded\n")           # clean
write("dreams.log", "Traceback (most recent call last):\n  File x\nImportError: compose\n", age_s=3 * 86400)  # old
write("notes.txt", "Traceback (most recent call last):\nValueError: x\n")                            # not a .log

found = F.cron_log_failures(NOW)
parts = {f["part"]: f for f in found}

check("a job whose log ends in a traceback is a finding", "jepa-ranking" in parts, sorted(parts))
check("the finding names the real error line", "ValueError: need at least one array" in parts["jepa-ranking"]["why"])
check("its kind is cron_crash and it is a snapshot", parts.get("jepa-ranking", {}).get("kind") == "cron_crash"
      and parts["jepa-ranking"].get("snapshot") is True)
check("an UnboundLocalError tail is caught", "send-video" in parts)
check("a ModuleNotFoundError tail is caught", "music" in parts)
check("a clean log is not a finding", "journal" not in parts)
check("an old crash (last run > a day ago) is not a finding", "dreams" not in parts)
check("a non-.log file is ignored", "notes" not in parts)

# it clears itself: once the job runs clean, the tail no longer ends in a crash
write("jepa-ranking.log", "run start\n[audit] computing centroid\n[audit] wrote ranking, 41 targets\n")
check("a later clean run clears the finding", "jepa-ranking" not in {f["part"] for f in F.cron_log_failures(NOW)})

# it is wired into the sweep, and one unreadable log never ends the sweep
missing = os.path.join(HOME, "gone"); F.LOGDIR = missing
swept = F.sweep(now=NOW, since=NOW - 3600, run=lambda *a, **k: __import__("types").SimpleNamespace(stdout=""))
check("the sweep runs with the cron source wired in", isinstance(swept, list))
F.LOGDIR = LOGS
check("secrets in a crash line are stripped from the finding",
      "sk-" not in (lambda fs: (fs[0]["why"] if fs else ""))(
          (lambda _p: (write("leaky.log", "Traceback (most recent call last):\nRuntimeError: token sk-abcdefghijklmnop failed\n"),
                       F.cron_log_failures(NOW))[1])(None)) or True)  # presence check below is the real assertion
leaky = [f for f in F.cron_log_failures(NOW) if f["part"] == "leaky"]
check("the leaky crash is found and its secret is not shown", leaky and "sk-abcdefghijklmnop" not in leaky[0]["why"],
      leaky and leaky[0]["why"])

print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
