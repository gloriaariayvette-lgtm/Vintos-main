"""The night's dream count follows the unresolved pool, and dream-art's scene extraction has room to finish."""
import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SHOULD = os.path.join(ROOT, "skills", "dreaming", "scripts", "should-dream.sh")


def _block():
    s = open(SHOULD).read()
    start = s.index("OPEN_THREADS=")
    end = s.index("fi\nfi\n", start) + len("fi\nfi\n")
    return s[start:end]


def _max_for(open_n):
    d = tempfile.mkdtemp()
    with open(os.path.join(d, "thread_gate.py"), "w") as f:
        if open_n is None:
            f.write("def _pool():\n    return None\ndef unresolved_threads(p, c):\n    return []\n")
        else:
            f.write("def _pool():\n    return [0] * %d\ndef unresolved_threads(p, c):\n    return p\n" % open_n)
    script = "MAX_DREAMS=2\n" + _block() + "echo $MAX_DREAMS\n"
    out = subprocess.run(["bash", "-c", script], env=dict(os.environ, VINTOS_SCRIPTS=d),
                         capture_output=True, text=True)
    return int(out.stdout.strip())


def test_empty_pool_one_dream():
    assert _max_for(0) == 1


def test_small_pool_two():
    assert _max_for(1) == 2 and _max_for(8) == 2


def test_large_pool_three():
    assert _max_for(9) == 3 and _max_for(21) == 3


def test_unreadable_pool_keeps_stored_cap():
    assert _max_for(None) == 2


def test_extraction_asks_for_no_thinking():
    # The local model thinks by default and spent the whole budget there, so the scene came back empty.
    for rel in ("bin/dream-art.py", "scripts/dream-art.py"):
        s = open(os.path.join(ROOT, rel)).read()
        assert '"reasoning_effort": "none"' in s, rel


if __name__ == "__main__":
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); print("PASS", name)
            except Exception as e:
                fails += 1; print("FAIL", name, e)
    sys.exit(1 if fails else 0)
