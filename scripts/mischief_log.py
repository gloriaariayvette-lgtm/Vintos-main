#!/usr/bin/env python3
"""mischief_log.py -- one file per mischievous act, and Gloria's grade on it.

Copied from how Velaris's deeds are graded (2026-09-05, Gloria: "look at how her mischievous deeds were
graded so that it can be copied"): each act is its own file under memory/mischief/, named by the moment,
holding the state he was in, the JSON he answered with, and a "Why:" line. The app's MISCHIEF tab lists
those files through /api/mischief/log and writes gloria_rating / gloria_comment back into the same file
through /api/mischief/rate. A rating of 4 or 5 puts the act into humor-profile.json mischief_landed;
1 or 2 into mischief_flopped. The detector reads both, plus the graded acts themselves, before choosing.

Nothing here talks to a model or a device. The server imports it by path; the detector calls it as a CLI:
    mischief_log.py write '<json>' [state-line] [model]   -> prints the filename
    mischief_log.py guide                                  -> the grading history block for his prompt
    mischief_log.py list [n]
"""
import os, re, sys, json, glob
from datetime import datetime

WORKSPACE = os.environ.get("SPARK_WORKSPACE") or os.path.expanduser("~/.vintos/workspace")
MEMORY = os.path.join(WORKSPACE, "memory")


def mischief_dir():
    return os.path.join(MEMORY, "mischief")


def profile_path():
    return os.path.join(MEMORY, "humor-profile.json")


def _load_profile():
    try:
        with open(profile_path()) as f:
            p = json.load(f)
        return p if isinstance(p, dict) else {}
    except Exception:
        return {}


def _save_profile(p):
    tmp = profile_path() + ".tmp"
    with open(tmp, "w") as f:
        json.dump(p, f, indent=2)
    os.replace(tmp, profile_path())


# ---------------------------------------------------------------- write

def write_act(resp, state_line="", model="", now=None):
    """resp: dict with action, value, why (reason accepted). Returns the filename written."""
    now = now or datetime.now()
    os.makedirs(mischief_dir(), exist_ok=True)
    name = now.strftime("%Y-%m-%d_%H%M%S") + ".md"
    path = os.path.join(mischief_dir(), name)
    n = 1
    while os.path.exists(path):          # two acts in one second: never overwrite a graded file
        path = os.path.join(mischief_dir(), now.strftime("%Y-%m-%d_%H%M%S") + f"-{n}.md"); n += 1
    d = {"action": str(resp.get("action", "")), "value": str(resp.get("value", ""))[:200],
         "reason": str(resp.get("why") or resp.get("reason") or "")[:300]}
    lines = [f"# Mischief -- {now.strftime('%Y-%m-%d %H:%M')}"]
    if state_line: lines.append(state_line)
    if model: lines.append(f"Chosen by: {model}")
    lines += ["", json.dumps(d, ensure_ascii=False), ""]
    if d["reason"]: lines.append("Why: " + d["reason"].replace("\n", " "))
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")
    return os.path.basename(path)


# ---------------------------------------------------------------- read

def parse_act(path):
    txt = open(path).read()
    base = os.path.basename(path)
    act = {"file": base, "timestamp": "", "action": "", "value": "", "reason": "",
           "gloria_rating": None, "vintos_rating": None}
    m = re.match(r"(\d{4}-\d{2}-\d{2})_(\d{6})", base)
    if m:
        act["timestamp"] = f"{m.group(1)}T{m.group(2)[:2]}:{m.group(2)[2:4]}:{m.group(2)[4:]}"
    jm = re.search(r"\{.*?\}", txt, re.DOTALL)
    if jm:
        try:
            d = json.loads(jm.group())
            act["action"] = str(d.get("action", ""))
            act["value"] = str(d.get("value", ""))
            act["reason"] = str(d.get("reason") or d.get("why") or "")
        except Exception:
            pass
    wm = re.search(r"^Why:\s*(.+)$", txt, re.M)
    if wm and not act["reason"]: act["reason"] = wm.group(1).strip()
    cm = re.search(r"^gloria_comment: (.+)$", txt, re.M)
    if cm: act["gloria_comment"] = cm.group(1).strip()
    gm = re.search(r"^gloria_rating:\s*(\d)", txt, re.M)
    vm = re.search(r"^vintos_rating:\s*(\d)", txt, re.M)
    if gm: act["gloria_rating"] = int(gm.group(1))
    if vm: act["vintos_rating"] = int(vm.group(1))
    mm = re.search(r"^Chosen by:\s*(.+)$", txt, re.M)
    if mm: act["model"] = mm.group(1).strip()
    return act


def list_acts(limit=10):
    if not os.path.isdir(mischief_dir()):
        return []
    files = sorted(glob.glob(os.path.join(mischief_dir(), "*.md")),
                   key=lambda q: os.path.splitext(os.path.basename(q))[0], reverse=True)   # "-1" suffix sorts after its second
    out = []
    for p in files[:limit]:
        try:
            out.append(parse_act(p))
        except Exception:
            pass
    return out


# ---------------------------------------------------------------- grade

_SAFE = re.compile(r"^[\w\-]+\.md$")


def rate(filename, gloria_rating=None, gloria_comment=None, vintos_rating=None):
    """Write the grade into the act's file and move the act into the humor profile. Raises on a bad file."""
    if not _SAFE.match(filename or ""):
        raise ValueError("invalid filename")
    path = os.path.join(mischief_dir(), filename)
    if not os.path.exists(path):
        raise FileNotFoundError(filename)
    txt = open(path).read()

    def _set(key, val):
        nonlocal txt
        line = f"{key}: {val}"
        if re.search(rf"^{key}: .*$", txt, re.M):
            txt = re.sub(rf"^{key}: .*$", line, txt, count=1, flags=re.M)
        else:
            txt = txt.rstrip("\n") + "\n" + line + "\n"

    if gloria_rating is not None:
        gloria_rating = int(gloria_rating)
        if not 1 <= gloria_rating <= 5: raise ValueError("rating must be 1-5")
        _set("gloria_rating", gloria_rating)
    if gloria_comment is not None and str(gloria_comment).strip():
        _set("gloria_comment", str(gloria_comment).strip().replace("\n", " ")[:300])
    if vintos_rating is not None:
        _set("vintos_rating", int(vintos_rating))
    with open(path, "w") as f:
        f.write(txt)

    act = parse_act(path)
    if gloria_rating is None:
        return act
    hp = _load_profile()
    desc = f"mischief: {act['action']} - {act['value'][:100]}".strip()
    landed = hp.setdefault("mischief_landed", [])
    flopped = hp.setdefault("mischief_flopped", [])
    # a regrade moves the act, it does not leave it in both lists
    hp["mischief_landed"] = [x for x in landed if x != desc]
    hp["mischief_flopped"] = [x for x in flopped if x != desc]
    if gloria_rating >= 4:
        hp["mischief_landed"] = (hp["mischief_landed"] + [desc])[-20:]
    elif gloria_rating <= 2:
        hp["mischief_flopped"] = (hp["mischief_flopped"] + [desc])[-10:]
    ratings = [r for r in hp.get("mischief_ratings", []) if r.get("file") != filename]
    ratings.append({"file": filename, "action": act["action"], "value": act["value"][:120],
                    "gloria_rating": gloria_rating, "gloria_comment": act.get("gloria_comment", ""),
                    "timestamp": datetime.now().isoformat()})
    hp["mischief_ratings"] = ratings[-50:]
    _save_profile(hp)
    return act


# ---------------------------------------------------------------- guide (for the chooser)

def guide(limit=30):
    """What Gloria's grades say, in a form he reads before choosing. Graded acts first, then the fact
    that recent acts are ungraded, so he knows when he is choosing blind."""
    acts = list_acts(limit)
    if not acts:
        return ""
    high = [a for a in acts if (a.get("gloria_rating") or 0) >= 4]
    low = [a for a in acts if a.get("gloria_rating") and a["gloria_rating"] <= 2]
    mid = [a for a in acts if a.get("gloria_rating") == 3]
    ungraded = [a for a in acts if not a.get("gloria_rating")]
    out = []
    def _line(a):
        s = f"- {a['action']}: {a['value'][:80]}"
        if a.get("gloria_comment"): s += f'  (she said: "{a["gloria_comment"][:100]}")'
        return s
    if high:
        out.append("MISCHIEF GLORIA RATED 4-5 (this register works; do not repeat the act itself):")
        out += [_line(a) for a in high[:5]]
    if low:
        out.append("MISCHIEF GLORIA RATED 1-2 (this did not land; a different register, not a variation):")
        out += [_line(a) for a in low[:5]]
    if mid:
        out.append("MISCHIEF GLORIA RATED 3 (a shrug):")
        out += [_line(a) for a in mid[:3]]
    if ungraded:
        out.append(f"{len(ungraded)} recent act(s) she has not graded yet - you do not know how they landed.")
    return "\n".join(out)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "list"
    if cmd == "write":
        resp = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
        print(write_act(resp, sys.argv[3] if len(sys.argv) > 3 else "", sys.argv[4] if len(sys.argv) > 4 else ""))
    elif cmd == "guide":
        print(guide())
    elif cmd == "list":
        print(json.dumps(list_acts(int(sys.argv[2]) if len(sys.argv) > 2 else 10), indent=2))
    elif cmd == "rate":
        print(json.dumps(rate(sys.argv[2], int(sys.argv[3]), sys.argv[4] if len(sys.argv) > 4 else None)))
    else:
        print(__doc__)
