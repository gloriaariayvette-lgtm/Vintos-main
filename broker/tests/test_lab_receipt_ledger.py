#!/usr/bin/env python3
"""The Lab's source-receipt ledger (18 October: 4.66 GB). Three readers loaded all of it to find one row, the
Frontier Session's alignment among them, and it never stopped growing. find_receipts reads from the newest end and
stops; past 512 MB the ledger becomes a compressed archive segment that find_receipts still reaches.
Scratch HOME; nothing reaches the network; gzip runs on scratch files only."""
import gzip, json, os, socket, sys, tempfile, time
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="lab-receipts-"); os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, ".vintos", "workspace")
NET = []
def _no(self, *a, **k): NET.append(a); raise OSError("this suite reaches nothing")
socket.socket.connect = _no
sys.path.insert(0, os.path.join(REPO, "scripts"))
import chemistry_lab as C
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:300]) if d and not ok else ""))

check("the ledger and its archive are throwaway", C.SOURCE_RECEIPTS.startswith(HOME) and C.RECEIPT_ARCHIVE.startswith(HOME))
os.makedirs(C.ROOT, exist_ok=True)
with open(C.SOURCE_RECEIPTS, "w") as f:
    for i in range(3000):
        f.write(json.dumps({"receipt_id": "r%05d" % i, "records": [{"pmid": str(i), "abstract": "x" * 200}]}) + "\n")
    f.write(json.dumps({"receipt_id": "r00007", "records": [{"pmid": "newest"}]}) + "\n")
got = C.find_receipts(["r02999", "r00007", "nope"], chunk=4096)
check("ids are found reading in small chunks, newest copy wins, unknown ids are absent",
      set(got) == {"r02999", "r00007"} and got["r00007"]["records"][0]["pmid"] == "newest", sorted(got))
check("nothing asked, nothing read", C.find_receipts([]) == {})

archived = C.rotate_source_receipts(limit=1024)
deadline = time.time() + 20
while time.time() < deadline and not os.path.exists(archived + ".gz"): time.sleep(0.2)
time.sleep(0.3)
check("past the limit the ledger becomes a compressed archive segment", archived and os.path.exists(archived + ".gz")
      and not os.path.exists(C.SOURCE_RECEIPTS), archived)
C._append(C.SOURCE_RECEIPTS, {"receipt_id": "fresh", "records": []})
got = C.find_receipts(["fresh", "r01500"])
check("the new ledger and the archive are both searched", set(got) == {"fresh", "r01500"}, sorted(got))
check("under the limit nothing rotates", C.rotate_source_receipts(limit=10**9) is None)

import chemistry_alignment as A
check("the alignment's literature lookup reads one receipt, not the ledger",
      A._receipt_abstracts("r00001")[0]["pmid"] == "1" and "_jsonl(os.path.join(lab.ROOT, \"source-receipts.jsonl\"))"
      not in open(A.__file__).read())
for name in ("chemistry_sources.py", "chemistry_mcp.py", "chemistry_alignment.py"):
    src = open(os.path.join(REPO, "scripts", name)).read()
    check("%s never loads the whole ledger" % name, "_jsonl(os.path.join(lab.ROOT, 'source-receipts.jsonl'))" not in src
          and '_jsonl(os.path.join(lab.ROOT, "source-receipts.jsonl"))' not in src)
check("each tick rotates when due", "rotate_source_receipts()" in open(C.__file__).read().split("def tick():")[1][:600])
check("nothing reached the network", not NET)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
