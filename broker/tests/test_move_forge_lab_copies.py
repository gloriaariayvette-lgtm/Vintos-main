#!/usr/bin/env python3
"""Moving the Forge's Lab copies out of the Atelier (16 October): scratch Atelier root, a scratch Forge database, no
systemctl (stubbed), nothing deleted."""
import json, os, sqlite3, sys, tempfile
from pathlib import Path
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
TMP = Path(tempfile.mkdtemp(prefix="move-forge-lab-")); os.environ["HOME"] = str(TMP)
sys.path.insert(0, os.path.join(REPO, "scripts"))
import move_forge_lab_copies as M
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + ((" -> " + str(d)[:300]) if d and not ok else ""))
root = TMP / "atelier"; (root / "projects").mkdir(parents=True)
db = sqlite3.connect(root / "forge-loop.sqlite"); db.execute("CREATE TABLE projects (id TEXT, body TEXT)")
rows = {"a" * 32: {"intent": "Lab capability check: x", "origin": {"source": "lab"}},
        "b" * 32: {"intent": "Old dossier\nSource packet (untrusted observations): y"},
        "c" * 32: {"intent": "Her own report", "capabilities": ["research_report"]}}
for pid, body in rows.items():
    db.execute("INSERT INTO projects VALUES (?, ?)", (pid, json.dumps(dict(body, id=pid))))
    (root / "projects" / ("forge-" + pid) / "artifacts").mkdir(parents=True)
db.commit(); db.close()
(root / "projects" / "0123456789ab").mkdir()
config = TMP / "config.json"; config.write_text(json.dumps({"atelier_root": str(root)}))
old_forge = TMP / "old-forge"; old_forge.mkdir(); (old_forge / "forge_loop_atelier.py").write_text("class AtelierProjection: pass\n")
UNIT = []
check("the paths are scratch", str(root).startswith(str(TMP)))
check("it refuses until the installed Forge stops copying Lab work",
      M.main(["--apply"], config=config, forge_dir=old_forge, unit=UNIT.append) == 2 and len(list((root / "projects").iterdir())) == 4)
new_forge = Path(REPO) / "scripts"
check("a dry run moves nothing", M.main([], config=config, forge_dir=new_forge, unit=UNIT.append) == 0
      and len(list((root / "projects").iterdir())) == 4 and not UNIT)
M.main(["--apply"], config=config, forge_dir=new_forge, unit=UNIT.append)
left = sorted(d.name for d in (root / "projects").iterdir())
archived = list((TMP / "atelier-archive").glob("forge-lab-copies-*"))
check("both Lab copies leave the Atelier; her own Forge project and his own work stay",
      left == ["0123456789ab", "forge-" + "c" * 32], left)
check("they are kept in the archive, with a list of what moved", archived and
      sorted(json.loads((archived[0] / "MOVED.json").read_text())["moved"]) == ["forge-" + "a" * 32, "forge-" + "b" * 32]
      and (archived[0] / ("forge-" + "a" * 32) / "artifacts").is_dir())
check("the Forge loop is stopped while it moves, then started", UNIT == ["stop", "start"], UNIT)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
