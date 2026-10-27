"""The protein a UniProt accession is, checked against the name written beside it (27 October).

All four investigations the Lab marked answered on 26-27 October were about O43511, and two of them called it
"Trehalose phosphate synthase". O43511 is pendrin (SLC26A4, human): every cached UniProt receipt of it says so. The
name had come in with a line of inquiry about trehalose phosphate synthase and was carried, beside the accession,
into step questions and PubMed queries; nothing compared the two.

Now, when a step question, a request's text, an investigation question or its line's question names an accession
together with a protein name, the name is checked against that accession's UniProt record as the Lab already holds
it (a step's normalized record, or the Lab's own sourced record). A name the record does not carry is corrected in
place, and he is told the record's own name. Nothing is fetched for this, and nothing is said when the Lab holds no
record of the accession, or when the text names no protein beside it.

Only clear claims are read: "NAME (ACC)", "ACC (NAME)", "ACC 'NAME'", and a name with a protein head word (a
synthase, a transporter, a "...in" like pendrin) written right before or after the accession. A gene symbol is
checked only against a record that lists genes.
"""
from __future__ import annotations
import re

ACCESSION = re.compile(r"(?<![A-Za-z0-9])(?:[OPQ][0-9][A-Z0-9]{3}[0-9]|[A-NR-Z][0-9](?:[A-Z][A-Z0-9]{2}[0-9]){1,2})(?![A-Za-z0-9])")
WORD = re.compile(r"[A-Za-z0-9][A-Za-z0-9/+'-]*")
# words that end a name when read backwards from the accession, or are no name at all
STOP = frozenset("""the a an of for in on at to and or with from by about into than its his her their this that these
those which what how does do is are was were be been between within across against versus vs as per via using use
read run compare measure measured analyze analyse fold folded model models modelled structure structures sequence
sequences file files output outputs result results step data query search window region residues residue entry record
records accession uniprot uniprotkb esmfold esmc pdb prediction predicted alignment align aligned map mapped protein's
domain domains motif motifs site sites helix helices strand strands loop loops chain chains""".split())
# words that are no part of a name's identity (an organism, a hedge, a generic class word)
GENERIC = frozenset("""human mouse rat yeast bovine porcine pig bacterial viral putative probable uncharacterized
predicted protein proteins family member members subunit isoform enzyme type form homolog homologue ortholog
like related domain""".split())
HEAD_WORDS = frozenset("""protein transporter receptor channel exchanger antiporter symporter uniporter pump factor
subunit enzyme carrier toxin hormone antigen regulator repressor activator inhibitor""".split())
NOT_ASE = frozenset("""base case phase release increase decrease database please lease cease erase purchase vase
chase phrase ease""".split())
NOT_IN = frozenset("""protein domain chain within begin again origin margin brain main plain contain obtain retain
maintain remain certain explain twin skin pin bin""".split())
GENE = re.compile(r"[A-Z][A-Z0-9]*[0-9][A-Z0-9]*")


def _head(word):
    w = word.lower().strip("'")
    return (w in HEAD_WORDS or (w.endswith("ase") and len(w) > 5 and w not in NOT_ASE)
            or (w.endswith("in") and len(w) >= 5 and w not in NOT_IN))


def _tokens(text):
    return [t.lower() for t in re.findall(r"[A-Za-z0-9]+", str(text or ""))]


def _distinct(tokens):
    return [t for t in tokens if t not in GENERIC and t not in STOP and not t.isdigit()
            and (len(t) >= 4 or any(c.isdigit() for c in t))]


def _claims_name(phrase):
    words = WORD.findall(phrase)
    return bool(words) and (any(_head(w) for w in words) or any(GENE.fullmatch(w) for w in words))


def pairs(text):
    """[(accession, phrase, (start, end) of the phrase in text)] for every accession written with a protein name."""
    text = str(text or "")
    out = []
    for m in ACCESSION.finditer(text):
        acc, start, end = m.group(0), m.start(), m.end()
        found = None
        after = text[end:end + 120]
        # ACC (NAME), ACC ("NAME"), ACC 'NAME', ACC: "NAME"
        q = re.match(r"""\s*\(\s*['"“‘]?([^()'"“”‘’]{3,80}?)['"”’]?\s*\)""", after) or \
            re.match(r"""\s*[,:]?\s*['"“‘]([^'"“”‘’]{3,80})['"”’]""", after)
        quoted = bool(q) and q.group(0).lstrip(' ,:(').startswith(('"', "'", '“', '‘'))
        if (q and WORD.search(q.group(1)) and (quoted or _claims_name(q.group(1)))
                and not ACCESSION.fullmatch(q.group(1).strip()) and WORD.findall(q.group(1))[0].lower() not in STOP):
            found = (q.group(1).strip(), end + q.start(1), end + q.end(1))
        # NAME (ACC) or NAME ACC: the name-like words just before it
        if not found:
            before = text[max(0, start - 160):start]
            paren = re.search(r"\(\s*$", before)
            words = list(WORD.finditer(before[:paren.start()] if paren else before))
            if words and (paren or re.fullmatch(r"\s+", before[words[-1].end():] or " ")):
                run = []
                for w in reversed(words[-8:]):
                    if w.group(0).lower() in STOP or ACCESSION.fullmatch(w.group(0)):
                        break
                    if run and not re.fullmatch(r"\s+", before[w.end():run[0].start()]):
                        break
                    run.insert(0, w)
                if run and (paren or _head(run[-1].group(0)) or GENE.fullmatch(run[-1].group(0))):
                    offset = max(0, start - 160)
                    phrase = before[run[0].start():run[-1].end()]
                    if _claims_name(phrase):
                        found = (phrase, offset + run[0].start(), offset + run[-1].end())
        # ACC NAME ... : the words after it, up to the last protein head word among the first five
        if not found:
            words = list(WORD.finditer(after))[:5]
            if words and re.fullmatch(r"\s+", after[:words[0].start()] or "x"):
                last = None
                for i, w in enumerate(words):
                    if w.group(0).lower() in STOP:
                        break
                    if i and not re.fullmatch(r"\s+", after[words[i - 1].end():w.start()]):
                        break
                    if _head(w.group(0)):
                        last = i
                if last is not None:
                    phrase = after[words[0].start():words[last].end()]
                    found = (phrase, end + words[0].start(), end + words[last].end())
        if found and _distinct(_tokens(found[0])):
            out.append((acc, found[0], (found[1], found[2])))
    return out


def record_names(record):
    """Every name the record gives the protein: its name, aliases, entry name and genes."""
    if not isinstance(record, dict):
        return []
    names = [record.get("protein_name"), record.get("id"), record.get("uniProtkbId")]
    names += list(record.get("protein_aliases") or [])
    desc = record.get("proteinDescription") if isinstance(record.get("proteinDescription"), dict) else {}
    for block in [desc.get("recommendedName")] + list(desc.get("alternativeNames") or []):
        if isinstance(block, dict):
            names.append((block.get("fullName") or {}).get("value"))
            names += [(s or {}).get("value") for s in block.get("shortNames") or [] if isinstance(s, dict)]
    names += gene_names(record)
    return list(dict.fromkeys(str(n) for n in names if n))


def gene_names(record):
    out = []
    for gene in (record or {}).get("genes") or []:
        if isinstance(gene, str):
            out.append(gene)
        elif isinstance(gene, dict):
            value = gene.get("geneName")
            out.append(value.get("value") if isinstance(value, dict) else value)
            out += [(s or {}).get("value") for s in gene.get("synonyms") or [] if isinstance(s, dict)]
    return [str(g) for g in out if g]


def agrees(phrase, record):
    """True unless the phrase is clearly not this record's protein: one distinctive word of it is one of the record's
    own (pendrin in "human pendrin STAS"), or it cannot be judged (a gene symbol against a record listing no genes)."""
    said = _distinct(_tokens(phrase))
    if not said:
        return True
    names = record_names(record)
    known = set()
    for name in names:
        known |= set(_tokens(name))
        known.add(re.sub(r"[^a-z0-9]", "", name.lower()))
    if any(t in known for t in said):
        return True
    if re.sub(r"[^a-z0-9]", "", phrase.lower()) in known:
        return True
    if not gene_names(record) and all(GENE.fullmatch(w) for w in WORD.findall(phrase) if w.lower() not in GENERIC):
        return True    # a gene symbol, and the record held here lists no genes: not judged
    return False


def describe(record):
    genes = gene_names(record)[:2]
    organism = record.get("organism_name") or record.get("organism")
    if isinstance(organism, dict):
        organism = organism.get("scientificName")
    extra = ", ".join([("gene " + "/".join(genes)) if genes else "", str(organism or "")]).strip(", ")
    return "%s%s" % (record.get("protein_name") or (record_names(record) or ["?"])[0], (" (%s)" % extra) if extra else "")


def check(text, lookup):
    """[{accession, said, uniprot_name, is, span}] for each accession the text names with a name its record does not
    carry. lookup(accession) is the record the Lab holds, or None (then nothing is said)."""
    out = []
    for acc, phrase, span in pairs(text):
        record = lookup(acc)
        if not isinstance(record, dict) or str(record.get("accession") or acc).upper() != acc.upper():
            continue
        if not agrees(phrase, record):
            out.append({"accession": acc, "said": phrase, "uniprot_name": record.get("protein_name") or "",
                        "is": describe(record), "span": list(span)})
    return out


def correct(text, mismatches):
    """The text with each wrong name replaced by the record's own name."""
    text = str(text or "")
    for m in sorted(mismatches, key=lambda m: -m["span"][0]):
        a, b = m["span"]
        if text[a:b] == m["said"] and m.get("uniprot_name"):
            text = text[:a] + m["uniprot_name"] + text[b:]
    return text


def message(m):
    return ('%s is %s, not "%s": UniProt\'s record of %s names it %s. Corrected here; use that name for it.'
            % (m["accession"], m["is"], m["said"], m["accession"], m["uniprot_name"] or m["is"]))
