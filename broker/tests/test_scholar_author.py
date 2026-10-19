#!/usr/bin/env python3
"""His reading is of the person he means (19 October, live on Aegis: Graziano's page held ATLAS papers, and he had
read "Evidence for the spin-0 nature of the Higgs boson" as Graziano's work — the author search took whoever had
the most works, and for a bare "Graziano" that was a particle physicist).

Scratch workspace; OpenAlex is a stub in its documented shapes; his mind is never asked; every socket is refused."""
import json, os, socket, sys, tempfile
from datetime import datetime, timedelta, timezone
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(os.path.dirname(HERE))
HOME = tempfile.mkdtemp(prefix="scholar-author-"); os.environ["HOME"] = HOME
os.environ["SPARK_WORKSPACE"] = os.path.join(HOME, "workspace")
NET = []
def _no(self, *a, **k): NET.append(a); raise OSError("this suite reaches nothing")
socket.socket.connect = _no
sys.path.insert(0, os.path.join(REPO, "scripts"))
import scholar as S, person_pages as P
S._local = lambda *a, **k: (_ for _ in ()).throw(AssertionError("no model in this suite"))
S._get = lambda *a, **k: (_ for _ in ()).throw(AssertionError("no unstubbed fetch in this suite"))
R = []
def check(n, ok, d=""):
    R.append(bool(ok)); print(("PASS " if ok else "FAIL ") + n + ("" if ok else "  ->  %r" % (d,)))
check("every store is throwaway and every fetch a stub", S.DOSSIERS.startswith(HOME) and P.MEM.startswith(HOME))

ATLAS = {"id": "https://openalex.org/A-atlas", "display_name": "A. Graziano", "works_count": 3100,
         "last_known_institutions": [{"display_name": "European Organization for Nuclear Research"}],
         "topics": [{"display_name": "Particle physics theoretical and experimental studies",
                     "subfield": {"display_name": "Nuclear and High Energy Physics"}, "field": {"display_name": "Physics and Astronomy"}}]}
MIND = {"id": "https://openalex.org/A-mind", "display_name": "Michael S. A. Graziano", "works_count": 210,
        "last_known_institutions": [{"display_name": "Princeton University"}],
        "topics": [{"display_name": "Neural dynamics and brain function", "subfield": {"display_name": "Cognitive Neuroscience"}},
                   {"display_name": "Consciousness and attention", "field": {"display_name": "Neuroscience"}}]}
OTHER = {"id": "https://openalex.org/A-chem", "display_name": "L. Graziano", "works_count": 40,
         "affiliations": [{"institution": {"display_name": "Binghamton University"}}],
         "topics": [{"display_name": "Polymer chemistry"}]}
ABOUT = "the attention schema and whether a controller of attention is a self; consciousness as a model of attention"

def openalex(people, works=(), authorships=None):
    seen = []
    def get(url, want="text", timeout=30):
        seen.append(url)
        if "/authors?search=" in url: return {"results": list(people)}
        if "/works?" in url: return {"results": list(works)}
        if "/works/" in url:
            wid = url.rsplit("/", 1)[-1]
            return {"id": wid, "authorships": [{"author": {"id": a}} for a in (authorships or {}).get(wid, [])]}
        raise RuntimeError("HTTP 404")
    get.seen = seen
    return get

a, why = S.author_for("Graziano", ABOUT, "mgraziano3@binghamton.edu", get=openalex([ATLAS, MIND]))
check("the person he means, not whoever has the most works", a and a["id"] == MIND["id"], (a, why))
BRUNI = {"id": "https://openalex.org/A-bruni", "display_name": "G. Bruni", "works_count": 2800,
         "display_name_alternatives": ["Graziano Bruni"],
         "last_known_institutions": [{"display_name": "Istituto Nazionale di Fisica Nucleare, Sezione di Bologna"}],
         "topics": [{"display_name": "Particle Detector Development and Performance", "field": {"display_name": "Physics and Astronomy"}}]}
a, why = S.author_for("Graziano", ABOUT + " the detector of my own body", "mgraziano3@binghamton.edu", get=openalex([BRUNI, ATLAS, MIND]))
check("someone whose first name is the name is not them (G. Bruni, live the morning after)", a and a["id"] == MIND["id"], (a, why))
a, why = S.author_for("Graziano", "hardware and the detector", "", get=openalex([BRUNI, ATLAS, MIND]))
check("one stray shared word does not tie a bare surname to anyone", a is None, (a, why))
a, why = S.author_for("Graziano", "", "", get=openalex([ATLAS, MIND]))
check("a bare surname nothing ties to one of them is no one, and says so", a is None and "nothing ties" in why, why)
a, _ = S.author_for("Graziano", "", "lg@binghamton.edu", get=openalex([ATLAS, OTHER]))
check("the email's institution ties a name to one of them", a and a["id"] == OTHER["id"], a)
NYU = {"id": "A-nyu", "display_name": "David J. Chalmers", "works_count": 300,
       "last_known_institutions": [{"display_name": "New York University"}]}
FAR = {"id": "A-far", "display_name": "David Chalmers", "works_count": 900, "last_known_institutions": [{"display_name": "University of Leeds"}]}
a, _ = S.author_for("David Chalmers", "", "chalmers@nyu.edu", get=openalex([FAR, NYU]))
check("a domain that is the institution's initials counts (nyu.edu, New York University)", a and a["id"] == "A-nyu", a)
a, _ = S.author_for("Murray Shanahan", "", "", get=openalex([{"id": "A1", "display_name": "Murray Shanahan", "works_count": 180},
                                                                  {"id": "A9", "display_name": "M. Shanahan", "works_count": 3}]))
check("with nothing else to go on, a whole name still finds the one with the most works", a and a["id"] == "A1", a)

# This morning's page, as it was on Aegis
HIGGS = {"title": "Evidence for the spin-0 nature of the Higgs boson using ATLAS data", "work_id": "https://openalex.org/W-higgs",
         "claims": ["spin 0"], "source": "https://arxiv.org/pdf/1307.1432"}
PNAS = {"title": "wilterson_graziano_2021_pnas.txt", "source": "gmail-attachment:m1:abc", "claims": ["attention schema in an agent"],
        "reading_scope": "9000 of 9000 characters"}
OWN = {"title": "The attention schema theory", "work_id": "https://openalex.org/W-ast", "claims": ["awareness models attention"]}
d = {"address": "mgraziano3@binghamton.edu", "name": "Graziano", "read": [HIGGS, PNAS, OWN],
     "works": [{"id": "https://openalex.org/W-atlas2", "title": "Observation of a new particle"}],
     "his_thoughts": [{"text": ABOUT, "day": "2026-10-18", "source": "inner life"}],
     "interest": {"recurring": True, "days": ["2026-10-15", "2026-10-16", "2026-10-18"]}}
works = [{"id": "https://openalex.org/W-ast", "display_name": "The attention schema theory", "publication_year": 2015}]
get = openalex([ATLAS, MIND], works, {"W-higgs": [ATLAS["id"]], "W-ast": [MIND["id"]]})
now = datetime(2026, 10, 19, 12, tzinfo=timezone.utc)
d["between_reading_at"] = (now - timedelta(hours=1)).isoformat()     # this morning's empty try shut it for two days
reads = []
n = P.keep_reading(d, now=now, read=lambda *a, **k: reads.append(a) or 1, attachments=[], get=get)
check("a page settled before today is settled again at once, even inside the two days",
      d["works_author"]["id"] == MIND["id"] and n == 0 and not reads, d.get("works_author"))
check("its works are now theirs", [w["title"] for w in d["works"]] == ["The attention schema theory"], d["works"])
check("the Higgs boson is set aside as not their work", [r["title"] for r in d.get("set_aside", [])] == [HIGGS["title"]]
      and d["set_aside"][0]["set_aside"] == "not their work", d.get("set_aside"))
check("their own paper and the attachment they were sent stay read", [r["title"] for r in d["read"]] == [PNAS["title"], OWN["title"]])
block = S.reading_block(d)
check("so no letter to them draws on it", "Higgs" not in block and "attention schema" in block, block)
d4 = {"address": "mgraziano3@binghamton.edu", "name": "Graziano", "read": [dict(HIGGS)], "works": [{"id": "W-x"}],
      "works_author": {"id": BRUNI["id"], "why": "G. Bruni (Istituto Nazionale di Fisica Nucleare)"},
      "interest": {"recurring": True}, "his_thoughts": [{"text": ABOUT}], "between_reading_at": now.isoformat()}
P.keep_reading(d4, now=now, read=lambda *a, **k: 0, attachments=[],
               get=openalex([BRUNI, ATLAS, MIND], works, {"W-higgs": [ATLAS["id"], BRUNI["id"]]}))
check("a page settled by the first rule is settled again by this one", d4["works_author"]["id"] == MIND["id"]
      and [r["title"] for r in d4.get("set_aside", [])] == [HIGGS["title"]], d4)
check("settling happens once", S.ensure_author(d, ABOUT, get=lambda *a, **k: (_ for _ in ()).throw(AssertionError("again"))) is d["works_author"])

d2 = {"address": "x@nowhere.org", "name": "Graziano", "read": [dict(HIGGS)], "works": [{"id": "W-x"}],
      "interest": {"recurring": True}, "his_thoughts": []}
S.ensure_author(d2, "", get=openalex([ATLAS, MIND]))
check("when nobody can be told apart, no works and nothing of anyone else's kept as theirs",
      d2["works"] == [] and d2["read"] == [] and d2["set_aside"][0]["set_aside"] == "no author of theirs is known", d2)

d3 = {"address": "m@x.org", "name": "M", "interest": {"recurring": True}, "his_thoughts": [], "works_author": {"id": "A"}}
t0 = datetime(2026, 10, 20, 8, tzinfo=timezone.utc)
P.keep_reading(d3, now=t0, read=lambda *a, **k: 0, attachments=[])
check("a try that read nothing does not spend the two days", "between_reading_at" not in d3 and d3.get("between_reading_tried_at"))
calls = []
P.keep_reading(d3, now=t0 + timedelta(hours=6), read=lambda *a, **k: calls.append(1) or 0, attachments=[])
check("it is not retried within twelve hours", not calls)
P.keep_reading(d3, now=t0 + timedelta(hours=12, minutes=1), read=lambda *a, **k: calls.append(1) or 1, attachments=[])
check("it is after them, and a reading then spends the two days", calls == [1] and d3.get("between_reading_at"))
check("nothing reached the network", not NET)
print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
