#!/usr/bin/env python3
"""The 8pm entry was shorter than every draft behind it, and nothing said why.

Gloria, 2026-09-11. A1 328 words, B1 202, C1 412; absorbed to A2 437, B2 315, C2 366.
The synthesis ran on Claude at max_tokens 6000 and the log said so. The hallucination
check said CLEAN. The arrival gate never fired. The anchor regeneration never fired.
And the entry that landed was far shorter than any of it.

It was audit 2, which runs after the synthesis, every night, and was:

  - given the drafts truncated to `a2[:800]` and `b2[:800]` — A2 was 2294 characters —
    and not given C2 at all, while being asked to flag anything in the entry "not in
    DRAFT A or DRAFT B". Everything the synthesis drew from the back of A2, or from the
    third lens, read as invented to a reader that could not see it, and the instruction
    was to remove it.
  - asked to return the WHOLE entry at max_tokens 1200, against a synthesis written at
    6000, on the one shim path that never reaches Claude: /gemma routes ["gemma", "xai"],
    so a local 12B model re-emitted the entry.
  - allowed to replace the entry on `len(_corrected) > 100` alone, with no check that
    anything had been flagged.
  - silent. No log line, either way.

The arrival-gate retry (1400) and the anchored rewrite (1000) had the same shape: a
smaller ceiling replacing a larger entry on a thin test.

This holds all of it shut, in both copies of the script."""
import hashlib
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
COPIES = [os.path.join(REPO, "bin", "idle-journal.sh"),
          os.path.join(REPO, "scripts", "idle-journal.sh")]

R = []
def check(name, ok, detail=""):
    R.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + name + (("  ->  %s" % (detail,)) if (detail and not ok) else ""))


def src(path):
    return open(path, errors="replace").read()


print("--- both copies of the journal are the same journal ---")
digests = {p: hashlib.sha256(open(p, "rb").read()).hexdigest()[:12] for p in COPIES if os.path.isfile(p)}
check("bin/ and scripts/ hold one implementation", len(set(digests.values())) == 1, digests)
S = src(COPIES[0])

print("\n--- every embedded python block still compiles ---")
blocks = re.findall(r"python3\s*(?:-\s*)?<<\s*'(\w+)'\n(.*?)\n\1\n", S, re.S)
check("the script really is mostly python in heredocs", len(blocks) >= 10, len(blocks))
broken = []
for i, (tag, body) in enumerate(blocks):
    try:
        compile(body, "<%s>" % tag, "exec")
    except SyntaxError as e:
        broken.append("%s#%d line %s: %s" % (tag, i, e.lineno, e.msg))
check("bash -n cannot see inside a heredoc, so every block is compiled here",
      not broken, "; ".join(broken))

print("\n--- audit 2 sees all three drafts, whole ---")
a2 = S.index("audit2_r = requests.post")
audit2 = S[a2:a2 + 3000]
check("A2 is passed in full, not its first 800 characters",
      '"DRAFT A:\\n" + a2 + ' in audit2 and "a2[:800]" not in audit2, "a2[:800]" in audit2)
check("B2 is passed in full", 'DRAFT B:\\n" + b2 + ' in audit2 and "b2[:800]" not in audit2)
check("C2 is passed at all — it was absent entirely, so everything drawn from the third "
      "lens read as invented", '"DRAFT C:\\n" + c2 + ' in audit2)
check("and the audit is told the drafts are complete, so absence means invented",
      "given IN FULL" in audit2)
check("no draft anywhere in the audit is sliced", not re.search(r"\b[abc]2\[:\d+\]", audit2),
      re.findall(r"\b[abc]2\[:\d+\]", audit2))

print("\n--- and it may only correct, never compress ---")
check("CLEAN leaves the entry exactly as the synthesis wrote it",
      'CLEAN' in audit2 and "entry unchanged" in audit2)
check("a returned entry under three quarters of the synthesis is refused",
      "0.75 * len(_pre_audit)" in audit2)
check("the refusal says so in the log, with both lengths",
      "audit-2 REJECTED" in audit2 and "compression, not a correction" in audit2)
check("an accepted correction is logged too, with both lengths",
      "audit-2 corrected the entry" in audit2)
check("a failure keeps the synthesis rather than losing it",
      "kept the synthesis" in audit2)
check("it is told not to shorten, tighten or re-voice",
      "Do not shorten, summarise, tighten or re-voice" in audit2)
check("the pre-audit synthesis is written to disk, so a night like this is recoverable",
      "vintos-bilateral-final-preaudit.txt" in S)

print("\n--- no path replaces the entry from a smaller ceiling ---")
final_from = S.index("_raw = (_claude_sync(")
final_to = S.index("# Final BIS outcome")
final_path = S[final_from:final_to]
ceilings = [int(m) for m in re.findall(r'"max_tokens":\s*(\d+)', final_path)]
check("the synthesis itself still runs at 6000", "max_tokens=6000" in final_path)
check("every regeneration after it can hold a whole entry",
      ceilings and min(ceilings) >= 4000, sorted(ceilings))
check("the 1000 / 1200 / 1400 ceilings are gone",
      not ({1000, 1200, 1400} & set(ceilings)), sorted(ceilings))

print("\n--- the two regenerations are guarded the same way ---")
check("the arrival retry must arrive better AND keep the entry's length",
      '_ag_scores2["arrival"] > _ag_scores["arrival"] and len(_raw2) >= 0.75 * len(_raw)' in final_path)
check("a better score on a much shorter entry is refused, and says so",
      "kept the synthesis" in final_path and "arrived better but is" in final_path)
check("the anchored rewrite is no longer accepted on 'over 100 characters'",
      "len(_rv_text) > 100" not in final_path)
check("it must keep three quarters of the entry too",
      "len(_rv_text) >= 0.75 * len(_raw)" in final_path)

print("\n--- the rule itself, on the night it was found ---")
def keeps(pre, corrected):
    """The guard, applied exactly as the script applies it."""
    if not corrected or corrected.upper().strip().strip(".") == "CLEAN":
        return "unchanged"
    if len(corrected) <= 100:
        return "unchanged"
    if len(corrected) < 0.75 * len(pre):
        return "unchanged"
    return "replaced"

check("a clean audit changes nothing", keeps("x" * 4000, "CLEAN") == "unchanged")
check("a clean audit with a full stop changes nothing", keeps("x" * 4000, "Clean.") == "unchanged")
check("a real correction, a few sentences lighter, is taken",
      keeps("x" * 4000, "y" * 3600) == "replaced")
check("an entry cut to half is refused", keeps("x" * 4000, "y" * 2000) == "unchanged")
check("an entry cut to a third — what happened — is refused",
      keeps("x" * 4000, "y" * 1300) == "unchanged")
check("the boundary is three quarters exactly", keeps("x" * 4000, "y" * 3000) == "replaced")
check("a fragment is refused however short", keeps("x" * 4000, "y" * 40) == "unchanged")
check("an empty audit response changes nothing", keeps("x" * 4000, "") == "unchanged")

print("\n--- which shim path each call actually takes ---")
shim = src(os.path.join(REPO, "bin", "vintos_claude_shim.py"))
check("/gemma is the one chain that never reaches Claude",
      'if path.startswith("/gemma"): return ["gemma", "xai"]' in shim)
check("and the plain chat path goes to Claude first, whatever model name is in the body",
      'return ["anthropic", "xai"]' in shim)
check("so a grok model name on /gemma is served by local Gemma, which forces its own model",
      'body["model"] = GEMMA_MODEL' in shim)
check("audit 2 is still on that path, knowingly",
      "8599/gemma/v1/chat/completions" in audit2)

print("\n--- it reached nothing outside the repository ---")
check("this suite only reads source", not os.path.exists(
    os.path.join(os.path.expanduser("~"), ".vintos", "workspace", "memory", "journal")))

print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
