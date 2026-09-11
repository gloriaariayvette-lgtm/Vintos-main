#!/usr/bin/env python3
"""One module, one implementation — whichever name reaches it.

Half of his organs exist under two spellings. Cron and the CLI run the hyphen
(`causal-cluster.py`); every `import causal_cluster` in the code resolves the
underscore. They are separate regular files in this repository and separate
regular files on the host, and nothing held them together, so a repair landed in
one of them and the other went on running the code it replaced:

  - `causal-cluster.py` got ab4a607's transaction and occurrence-id work.
    `causal_cluster.py` — the file the imports actually load — stayed on 9aca273
    and kept the snapshot-replacing save and the unlocked fallback. It was in no
    deploy list at all, so no deploy would ever have corrected it.
  - 22a36ad repaired `scripts/belief_sediment.py`. Three other copies of the same
    module kept the old replay. Worse: that basename is in SCRIPTS *and* BINS, and
    the plan promotes scripts/ then bin/ over the top of it — so the very deploy
    that claimed to install the repair would have thrown it away.
  - The same for behavioral_intercept, emoclaw_mode, emotional_entanglement,
    interaction_ledger, somatic_bridge and tension_field: eight module names, each
    with copies that had drifted apart, each repair sitting in whichever copy the
    author happened to open.

So three things are held here, and none of them can be satisfied by prose:

  1. Every copy of a module name is byte-identical to every other copy.
  2. A manifested .py name whose twin spelling exists on disk has that twin
     manifested too — otherwise the deploy corrects one spelling and leaves the
     other to rot, which is exactly how causal_cluster diverged.
  3. The deploy itself refuses a plan in which one destination is fed by two
     sources with different bytes, instead of letting the last one silently win.
"""
import hashlib
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
DEPLOY = os.path.join(REPO, "scripts", "deploy-atelier.sh")

R = []
def check(name, ok, detail=""):
    R.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + name + (("  ->  %s" % (detail,)) if (detail and not ok) else ""))


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def twin_of(name):
    """The other spelling of a module file name, or None when there isn't one."""
    if not name.endswith(".py"):
        return None
    stem = name[:-3]
    other = stem.replace("_", "-") if "_" in stem else stem.replace("-", "_")
    return (other + ".py") if other != stem else None


def copies():
    """module key -> [paths], for every .py under bin/ and scripts/, both spellings."""
    out = {}
    for d in ("bin", "scripts"):
        root = os.path.join(REPO, d)
        if not os.path.isdir(root):
            continue
        for f in sorted(os.listdir(root)):
            p = os.path.join(root, f)
            if f.endswith(".py") and os.path.isfile(p):
                out.setdefault(f.replace("-", "_"), []).append(os.path.join(d, f))
    return out


def manifest():
    """The SCRIPTS and BINS names the deploy actually installs, read from the script
    itself rather than from a list kept in parallel here — a copy would drift too."""
    src = open(DEPLOY).read()
    names = {"SCRIPTS": set(), "BINS": set()}
    for var in names:
        for m in re.finditer(r'^%s="(?:\$%s )?((?:[^"]|\n)*)"' % (var, var), src, re.M):
            names[var].update(m.group(1).split())
    return names["SCRIPTS"], names["BINS"]


print("--- every copy of a module is the same module ---")
groups = copies()
shared = {k: v for k, v in groups.items() if len(v) > 1}
check("the repository really does keep modules under more than one name",
      len(shared) > 40, len(shared))
divergent = []
for key, paths in sorted(shared.items()):
    digests = {p: sha(os.path.join(REPO, p)) for p in paths}
    if len(set(digests.values())) > 1:
        divergent.append((key, digests))
check("no module name has two different implementations behind it",
      not divergent,
      "; ".join("%s: %s" % (k, ", ".join(sorted(d))) for k, d in divergent))

print("\n--- the eight that had drifted, named so a regression is legible ---")
for key in ("behavioral_intercept.py", "belief_sediment.py", "causal_cluster.py",
            "emoclaw_mode.py", "emotional_entanglement.py", "interaction_ledger.py",
            "somatic_bridge.py", "tension_field.py"):
    paths = groups.get(key, [])
    digests = {sha(os.path.join(REPO, p)) for p in paths}
    check("%-28s %d copies, one implementation" % (key, len(paths)),
          len(paths) > 1 and len(digests) == 1, sorted(paths))

print("\n--- the repairs that drifting had hidden are the ones that survived ---")
# Each of these is a line the stale copy did not have. If a future sync runs the wrong
# way round, the bytes stay consistent and these go out — so check the content, not only
# that the copies agree with each other.
def every_copy(key, needle):
    return all(needle in open(os.path.join(REPO, p)).read() for p in groups.get(key, []))

check("causal_cluster keeps ab4a607's occurrence ids in both spellings",
      every_copy("causal_cluster.py", "cluster_observation_ids"))
check("causal_cluster keeps its two-store transaction, not the bare save",
      every_copy("causal_cluster.py", "with transactions([HYP_PATH, OBS_PATH])"))
check("belief_sediment keeps 22a36ad's replay dedup in all four copies",
      every_copy("belief_sediment.py", "must not manufacture another supporting occasion"))
check("somatic_bridge keeps e9000f2's observation contract",
      every_copy("somatic_bridge.py", "physical-observation-1"))
check("emoclaw_mode keeps review 227: the mode colours how, never whether",
      every_copy("emoclaw_mode.py", "This mode never governs whether you answer"))
check("tension_field keeps the model's own reason instead of KeyError 'choices'",
      every_copy("tension_field.py", '"choices" not in j'))
check("interaction_ledger keeps review 48's compatibility reader",
      every_copy("interaction_ledger.py", "load_json_compat"))
check("emotional_entanglement keeps review 157's single cosine",
      every_copy("emotional_entanglement.py", "from text_similarity import cosine"))
check("behavioral_intercept keeps 22a36ad's store_guard transaction",
      every_copy("behavioral_intercept.py", "from store_guard import transaction"))

print("\n--- the deploy installs both spellings, not just the one cron runs ---")
scripts_m, bins_m = manifest()
man = scripts_m | bins_m
check("the manifest was read from the deploy script", len(man) > 200, len(man))
unmanifested = []
for name in sorted(n for n in man if n.endswith(".py")):
    twin = twin_of(name)
    if not twin or twin in man:
        continue
    where = [d for d in ("bin", "scripts") if os.path.isfile(os.path.join(REPO, d, twin))]
    if where:
        unmanifested.append("%s (twin of %s, in %s)" % (twin, name, "/".join(where)))
check("every module twin that exists on disk is named in the manifest",
      not unmanifested, "; ".join(unmanifested))
check("causal_cluster.py in particular — the one the imports load — is manifested",
      "causal_cluster.py" in man)
check("and so is behavioral_intercept.py, which 22a36ad repaired",
      "behavioral_intercept.py" in man)

print("\n--- and a destination fed by two different sources stops the deploy ---")
gate = open(DEPLOY).read()
a = gate.index("printf '%s' \"$PLAN\" | python3 -c '") + len("printf '%s' \"$PLAN\" | python3 -c '")
b = gate.index("' || die \"one destination, two sources", a)
program = gate[a:b]
check("the deploy carries a one-destination-two-sources gate", len(program) > 200)

import tempfile
tmp = tempfile.mkdtemp()
same_a = os.path.join(tmp, "same_a.py"); same_b = os.path.join(tmp, "same_b.py")
diff_a = os.path.join(tmp, "diff_a.py"); diff_b = os.path.join(tmp, "diff_b.py")
open(same_a, "w").write("shared\n"); open(same_b, "w").write("shared\n")
open(diff_a, "w").write("repaired\n"); open(diff_b, "w").write("stale\n")

def run_gate(plan):
    return subprocess.run([sys.executable, "-c", program], input=plan,
                          capture_output=True, text=True)

ok = run_gate("%s|/dst/x.py\n%s|/dst/x.py\n" % (same_a, same_b))
check("two sources with the same bytes are allowed: 11 names are in both lists on purpose",
      ok.returncode == 0, ok.stdout + ok.stderr)
bad = run_gate("%s|/dst/x.py\n%s|/dst/x.py\n" % (diff_a, diff_b))
check("two sources with different bytes stop it, instead of the last one winning",
      bad.returncode == 1, bad.returncode)
check("and it names the destination and both sources",
      "/dst/x.py" in bad.stdout and "diff_a.py" in bad.stdout and "diff_b.py" in bad.stdout,
      bad.stdout)
single = run_gate("%s|/dst/x.py\n%s|/dst/y.py\n" % (same_a, diff_a))
check("an ordinary plan passes untouched", single.returncode == 0, single.stdout)
check("the gate refuses the deploy rather than warning",
      'die "one destination, two sources' in gate)

print("\n--- this suite reached nothing outside its own scratch ---")
check("no store was written under the real workspace",
      not os.path.exists(os.path.join(os.path.expanduser("~"), ".vintos", "workspace",
                                      "memory", "current-wants.json")))
check("the only files it wrote are in a throwaway directory", tmp.startswith(tempfile.gettempdir()))

print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
