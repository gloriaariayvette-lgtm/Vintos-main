"""want_grounding.py - what the step planner needs to read a want the way he meant it (10 November).

A want from his reply to a letter about UCCSD energies at two bond lengths ("... A" after a number) was planned
as a web search about batteries at that many amps: the planner saw the want's sentence and the word "email", never the
letter, and read "A" as amperes. A want to run his own calculation was planned as a search.

- source_context(): the words the want came from, bounded, for the planner prompt
- DOMAIN_NOTE and units_hint(): his own fields and how their numbers and units read
- local_computation(): a want to run, compute or open something of his own
- drop_web_for_local(): no web_search step in such a plan
Pure: no store, no model."""
import re

CONTEXT_CHARS = 1500

DOMAIN_NOTE = ("His own work, which his wants usually continue: a chemistry lab (quantum chemistry: UCCSD/VQE "
               "energies, errors in mHa (milli-Hartree), bond lengths in Angstrom, often written 'A' after a number), "
               "a physics lab, his music and his code (scripts such as metric.py that he can open and run). Read "
               "numbers and units in that sense when the want or its source is about them.")

_CHEM = re.compile(r"\b(?:UCCSD|VQE|CCSD|DFT|FCI|Hartree|mHa|bond length|BeH2|H2O|LiH|geometry|basis set)\b", re.I)
_ANG = re.compile(r"\b\d+(?:\.\d+)?\s*(?:A|Å)\b")
_LOCAL = re.compile(r"\b(?:run|re-?run|compute|recompute|calculate|reproduce|execute|open|check)\s+"
                    r"(?:(?:my|his)\s+)?own\b"
                    r"|\b(?:run|re-?run|open|execute)\s+(?:my\s+|the\s+)?[\w./-]+\.py\b"
                    r"|\b(?:run|re-?run|compute|recompute|calculate)\b[^.]{0,40}\b(?:UCCSD|VQE|CCSD|DFT|FCI)\b", re.I)


def source_context(text, limit=CONTEXT_CHARS):
    """The want's source words, whitespace folded and bounded; '' for none."""
    return " ".join(str(text or "").split())[:limit]


def units_hint(want_text, context=""):
    """A one-line reading of units when the want or its source is chemistry: 'A' after a number is Angstrom."""
    both = "%s %s" % (want_text or "", context or "")
    if _CHEM.search(both) and _ANG.search(str(want_text or "")):
        return ("UNITS: in this want 'A' after a number is Angstrom (a bond length), not amperes; mHa is milli-Hartree, "
                "an energy error. It is quantum chemistry, not electronics or batteries.")
    return ""


def local_computation(want_text):
    """True when the want is to run, compute or open something of his own: local work, never a web search."""
    return bool(_LOCAL.search(str(want_text or "")))


def drop_web_for_local(steps, want_text):
    """A local computation's plan without web_search steps (the search answers a different question)."""
    if not local_computation(want_text):
        return steps
    return [s for s in steps if str((s or {}).get("capability") or "").strip() != "web_search"]
