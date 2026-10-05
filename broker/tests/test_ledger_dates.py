#!/usr/bin/env python3
"""Every script that hands his exchanges with Gloria to a model says when each was said (2026-10-03). On 30 September
the chat, avatar, voice and Slack learned it (when_said.py); about forty other scripts (dreams, wants, reflection,
outreach and more) still pasted bare lines, so whatever model ran them read yesterday as now. Source only: nothing is
imported or run."""
import glob, os, re, sys

REPO = os.path.realpath(os.path.join(os.path.dirname(__file__), "..", ".."))
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + (("  ->  " + str(d)[:900]) if d and not ok else ""))

# Read the ledger and send nothing of it to a model; each says why.
NOT_TO_A_MODEL = {
    "scripts/gloria_prediction.py": "reads chat history, not the ledger; its 'no new exchange' hash must not move with the clock",
    "scripts/pressure_gemma.py": "the ledger only gives old lines of hers as voice samples to imitate; a date would be copied "
                                 "into the lines it writes, and those are embedded",
    "scripts/relationship_pressure.py": "the ledger text goes to embeddings and voice samples, never as a conversation",
}
READS = re.compile(r"interaction-ledger\.json")
GLORIA_TEXT = re.compile(r"""get\(\s*['"]gloria['"]|\[\s*['"]gloria['"]\s*\]""")
TO_A_MODEL = re.compile(r"chat/completions|model_router|anthropic|requests\.post|\"messages\"\s*:")

seen, missing = set(), []
for path in sorted(glob.glob(os.path.join(REPO, "scripts", "*.py")) + glob.glob(os.path.join(REPO, "bin", "*.py"))):
    real = os.path.realpath(path)
    if real in seen or not os.path.isfile(real):
        continue
    seen.add(real)
    rel = os.path.relpath(real, REPO)
    src = open(real, errors="replace").read()
    if not (READS.search(src) and GLORIA_TEXT.search(src) and TO_A_MODEL.search(src)):
        continue
    if "when_said" in src or rel in NOT_TO_A_MODEL:
        continue
    missing.append(rel)
check("every script that hands the ledger's exchanges to a model marks when each was said", not missing,
      "no dates: " + ", ".join(missing))
check("every exception still exists and says why", all(os.path.exists(os.path.join(REPO, p)) and why.strip()
                                                       for p, why in NOT_TO_A_MODEL.items()))
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
