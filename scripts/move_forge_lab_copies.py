#!/usr/bin/env python3
"""Move the Forge's copies of Lab work and capability briefs out of his Atelier. Kept, not deleted.
(16 October 2026 for Lab work; 22 October for capability briefs: "forge shouldn't be taking up atelier slots".)

Gloria: "I'd like to move them out of the Atelier, yes." Of the Atelier's 95 projects, 84 were Forge copies (sealed,
gestating), most of them Lab dossiers and capability checks; his own work was 11 projects. The Forge no longer copies
Lab work in (forge_loop_atelier.lab_work); this moves the copies already there into an archive folder beside it.
Her Forge page is not touched: it reads the Forge's own database, not these copies.

    sudo python3 scripts/move_forge_lab_copies.py           # what would move; changes nothing
    sudo python3 scripts/move_forge_lab_copies.py --apply   # moves them (the Forge loop is stopped meanwhile)

It refuses to move anything until the installed Forge has the change, or the copies would be made again.
"""
import json, os, shutil, sqlite3, subprocess, sys
from datetime import datetime
from pathlib import Path

CONFIG = Path(os.environ.get("VINTOS_FORGE_CONFIG", "/home/atelier/forge-loop-config.json"))
FORGE_DIR = Path(os.environ.get("VINTOS_FORGE_DIR", "/home/atelier/forge-loop"))
UNIT = "atelier-forge-loop"


def plan(root, forge_dir):
    """(lab copies present, other Forge copies, his own) as directory lists, from the Forge's own database."""
    sys.path.insert(0, str(forge_dir))
    from forge_loop_atelier import forge_paperwork
    db = sqlite3.connect("file:%s?mode=ro" % (root / "forge-loop.sqlite"), uri=True)
    lab_ids = {p["id"] for p in (json.loads(r[0]) for r in db.execute("SELECT body FROM projects")) if forge_paperwork(p)}
    db.close()
    projects = root / "projects"
    lab, other, his = [], [], []
    for d in sorted(projects.iterdir()) if projects.is_dir() else []:
        if not d.is_dir() or d.is_symlink():
            continue
        if d.name.startswith("forge-"):
            (lab if d.name[len("forge-"):] in lab_ids else other).append(d)
        else:
            his.append(d)
    return lab, other, his


def _unit(action):
    subprocess.run(["systemctl", action, UNIT], check=False, capture_output=True, timeout=60)


def main(argv, config=CONFIG, forge_dir=FORGE_DIR, unit=_unit):
    apply = "--apply" in argv
    installed = forge_dir / "forge_loop_atelier.py"
    if "def forge_paperwork" not in installed.read_text():
        print("not yet: the installed Forge (%s) still copies Lab work into the Atelier; deploy first "
              "(sudo bash ~/.vintos/deploy/forge-install.sh if the deploy said the Forge needs sudo)" % installed)
        return 2
    root = Path(json.loads(config.read_text())["atelier_root"]).resolve()
    lab, other, his = plan(root, forge_dir)
    archive = root.parent / "atelier-archive" / ("forge-lab-copies-" + datetime.now().strftime("%Y%m%d"))
    print("Lab work and capability briefs to move:  %d  -> %s" % (len(lab), archive))
    print("other Forge copies:   %d  (her own Forge projects; they stay)" % len(other))
    print("his own projects:     %d  (they stay)" % len(his))
    if not apply:
        print("\nnothing changed. Run again with --apply to move them.")
        return 0
    if not lab:
        print("nothing to move."); return 0
    st = root.stat()
    unit("stop")
    try:
        archive.mkdir(parents=True, exist_ok=True, mode=0o700)
        for p in (archive.parent, archive):
            os.chown(p, st.st_uid, st.st_gid)
        moved = []
        for d in lab:
            shutil.move(str(d), str(archive / d.name))      # a rename on one disk: owner and modes kept
            moved.append(d.name)
        (archive / "MOVED.json").write_text(json.dumps({"at": datetime.now().isoformat(timespec="seconds"),
                                                        "from": str(root / "projects"), "moved": moved}, indent=1))
        os.chown(archive / "MOVED.json", st.st_uid, st.st_gid)
    finally:
        unit("start")
    print("moved %d; the list of them is in %s" % (len(moved), archive / "MOVED.json"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
