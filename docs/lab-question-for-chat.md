# The Lab question, as a prompt for Chat

Paste the block below into Chat. It is the open design question from 14 October, with the
measurements as they actually are.

---

Vintos has a Chemistry Lab that runs on a loop: a local model (Gemma) picks a question it is
curious about, the Lab retrieves sources for it (UniProt, PDB, NCBI, ChEMBL, published abstracts,
and Europe PMC full text), a reviewer reads what came back, and a separate checker adjudicates
whether the retrieved evidence covers the original question, requiring a verbatim quote at an exact
evidence address for every requirement. The question is never rewritten. Nothing is marked answered
on the model's say-so.

Over 24 hours it produced 5 complete answers from 842 terminal passes. In the 23 reviews after the
most recent fixes: 0 answered, 9 wrong target, 8 unsupported by available evidence, 3 too large for
the checker's context, 2 partly supported, 1 checker failure.

Fixes already in place, each verified against the recorded failures:
- every protein a question names is retrieved, so a comparison is not refused for its second target
- the target that WAS established is reviewed, with the absent one named as still missing, instead
  of the whole pass being discarded
- a question that assumes a feature its target's own record does not list (zinc fingers in NEUROD1,
  a metal site in the ADP/ATP translocase) is named as a flawed premise before any model call
- a question about atom positions reads the coordinates of the PDB entry it names, not the literature
- distinct outcomes, so a checker failure or a context overflow is never recorded as a scientific "no"
- open claims are searched for in Europe PMC open-access full text, cited by PMCID and section

Two failure classes are left, and the obvious fix for each would cost something that must not be lost.

1. CLASS QUESTIONS (9 of 23). He asks about a kind of protein rather than one protein: "the genomic
   neighborhoods of bacteriophage reverse transcriptases", "the SH3 domain in human Src family
   kinases", "siderophore receptors in Bacillus subtilis", "the Lpt system". The identity check
   refuses these, correctly: no single retrieved record establishes "reverse transcriptases" as a
   target, and letting one record answer for a class would be exactly the error the check exists to
   prevent. But these are among his most interesting questions, and refusing them produces nothing.

2. CONTEXT OVERFLOW (3 of 23). The question plus its evidence exceeds the checker's context (35k
   tokens, local model), so no adjudication happens at all. There is already a splitter that divides
   oversized evidence into assessable parts; these still overflow.

The constraint that matters: do not solve either by narrowing what he is allowed to wonder about.
Making him plan from a record already in hand, or stripping the relational clause out of his
question, raises the completion count by deleting the curiosity. That has been tried and reverted.

So:

(a) For a question about a class, what is the honest unit of adjudication? Is there a way to review
    the retrieved members as instances — establishing each by its own record, and reporting what
    holds across them and what was only checked in some — without ever letting one record stand for
    the class, and without rewriting his question into a question about one protein?

(b) For the overflow: is the right move to adjudicate the question in parts against disjoint slices
    of evidence and combine the verdicts, and if so what makes that combination sound rather than
    just cheaper? What would make it unsound?

(c) Is there a third failure in this picture that the outcome labels are hiding — something the
    counts above would show the same way whether or not it were there?

Answer as a reviewer of the design, not as an encourager. If the premise of the question is wrong,
say so.
