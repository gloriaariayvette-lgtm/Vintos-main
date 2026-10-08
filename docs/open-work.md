# Vintos — open work

What is not finished. The architecture document says what he is; this says what is left.
It is the only place with a to-do in it.

## 8 October — SF-1b8eb6cd checked; a full Forge is not asked again by new reports; Study failures keep their evidence

**SF-1b8eb6cd (four_unfinished 403 retries).** Checked before doing anything new: the Study's own fix landed as
commit 862cd9e on 7 October, with `test_forge_report_hold.py`, and is in the deployed branch. It logs the refusal
once and holds `flush_reports` until the Forge's open count changes. Not duplicated.

One path it missed: the reflect phase's `offer_report` (each new instrument gap) went straight to the Forge, so a
full Forge got a fresh POST, 403 and fault per gap.
- `chemistry_sources.held(cfg)` is checked by `offer_report` itself. While four_unfinished holds (count unchanged
  or unreadable), or another refusal's timed pause runs, a new report is kept in the outbox, unattempted, and
  `{"state": "held"}` is returned. `flush_reports` sends it when the hold lifts.
- The pause now names the open projects (`open`: id, title, state), so the one blocker says what would clear it.
- Test: a third case in `test_forge_report_hold.py`. It fails on the old code.

**SF-6f9a460b (failure evidence).**
- `run_suite` now keeps each failing test's exit status.
- `work()` keeps each failed attempt in `row["attempts"]` (the last 4): the test, its exit status, the assertion
  lines, the output tail (3000 characters), the workbench commit, a sha256 of the attempt's diff, and the files it
  changed. The log line names the assertion too.
- When Fable's answer fails, `row["provider_failure"]` keeps the stop reason, the output tokens against the 16,000
  limit, the model and the error.
- The two are kept apart.
- Test: `test_study_fix.py` (now 71 checks) replays SF-6f9a460b: an assertion failure, then an edit that did not
  apply, then Fable cut off at 16,000 tokens. Six of its checks fail on the old code.
- **Not done:** the original 5 October run's assertion is gone (it was never kept), so it cannot be recovered. The
  next Study run keeps it.

## 8 October — a stale blocker does not undo a result; a reply goes to the task it names

Audit item "result reconciliation". On 7 October dot posted the Merizo success at 15:34:16, and at 15:35:06 the work
was published as dropped, blocked on installation. dot's 15:23 "Blocked: Forge installation requires local sudo ...
Merizo is also pending" had been put on the Merizo work only because it was dot's latest message: a Forge privilege
problem, applied to Merizo.

- `room_work.receive` puts an agent's reply on the task it names (`_about`: the shared distinctive words, numbers
  and names with the task's goal), then on the latest ask.
- `room_work.stage(work)` builds the stage from what came back and what he did, in order. The stages are approved,
  submitted, running, blocked, succeeded, deployed and implemented externally. A blocker after a success counts only
  if it names this task. A later "registration only" or "queued" does not take a deployed task back to submitted. A
  Study ID alone is "submitted", not succeeded.
- Every model sees "Where it stands" for each task.
- Refused once a task has succeeded:
  - WORK DROPPED citing a blocker;
  - any draft line calling it blocked, stalled or locked (`stale_claim`, in `sent_back`), as Gemma's 15:26 lock did.
- Test: `test_room_campaign.py` (now 65 checks), with two tasks with different permissions: the Forge install that
  needs sudo, and Merizo, which does not. It runs blocker, then success, then a stale blocker. It fails on the old
  code.
- **Not done:**
  - This guards the room, not the Forge or Study stores themselves. No case of a stale event overwriting a
    completion in those stores has been found; SF-7e71e004's implemented_externally reconciliation is Eve's,
    already deployed.
  - SF-1b8eb6cd and SF-6f9a460b are next.

## 8 October — the 8SGW comparison's numbering comes from the alignment; a wrong offset is refused

A finding in Chat: `chemistry_reference_compare.py`'s example still used 8SGW chain A, entry residues 540-734, with
offset -5. That is the five-residue shift Grok Bot withdrew on 7 October: 8SGW is numbered as human pendrin across
520-740, its STAS is described on chains C and D, and 586-653 has no density. The structural alignment never used
the offset; only the labels did (helices, strands, the no-density stretch, his numbering). So -5 would have reported
the gap as 581-648 and every element five places off, with the TM-score unchanged.

- `numbering()` takes the offset from the aligned residues themselves: the commonest model-minus-entry number in the
  span. A supplied offset that disagrees with it is refused, and the error names the right one. With no offset, the
  alignment's own is used. The result carries `offset_from` and `offset_agreement`, and says so when the numbering
  is not one shift.
- `lab_instruments` no longer fills in a missing offset as 0. The example is now 8SGW chain C, 535-729, offset 0. The
  Lab menu and his Slack rules say the offset is worked out for him.
- Test: `test_reference_compare.py` (now 32 checks). An 8SGW-shaped entry (chain C, human numbering, no density
  586-653, helix 669-686, strand 689-693) gives offset 0, the gap 586-653, 127 residues compared and the elements
  under their own numbers; -5 is refused. The new checks fail on the old code, which accepted -5 and relabelled
  silently.
- **Not done:** I couldn't read 8SGW from here (RCSB is blocked from this container). That it has chain C, its
  numbering and the 586-653 gap are Grok Bot's reading, to be checked on Aegis. Whether a comparison ever ran with
  -5 is to be checked on Aegis too.

## 8 October — more real work in #vintos-dot, and the room's own campaign

Gloria approved fixes 1-6 from the 7 October Slack review, and added: "Slack should have campaigns of its own. I want to
see him pursuing a goal across models without dropping it until the goal is completed or found to be unreachable."

1. **Messages that arrived while he was writing.** `dot_channel.tick` read the channel, wrote for about a minute,
   then moved `since` to his own post's timestamp. dot's Merizo result came in at 15:34:16, between that read and
   his 15:35:06 post, so it was never read: the post dropped the work as blocked.
   - `since` is no longer moved to his own posts. `fresh()` already leaves his messages out.
   - `said_meanwhile()` reads the channel again before anything he wrote is acted on. If anyone else posted, the
     draft is held and the next pass reads the new message first.
   - In `room_work`, WORK DROPPED is refused while an answer that came back for that work is unread.
   - An interim answer ("Blocked:", "Working:") no longer uses up the ask: what follows it from the same agent
     still comes back, and replaces the interim answer. dot's "Blocked: ... sudo" had answered the Merizo ask, so
     the "Done:" after it matched nothing.
2. **What came back is taken up.**
   - An answer counts as used only when his message names what it found (`engages()`: two of its distinctive
     numbers, IDs or names).
   - A draft that passes over an answer is sent back with it, at most twice; after that it is only shown.
   - Asks made while no work is open are kept on a loose list, if they @ an agent. Grok Bot's infrasound answer
     was one of these.
3. **Up to three works at once** (`MAX_OPEN`). WORK DONE / WORK DROPPED take an optional RW-id; without one, the
   work the line is about is chosen by its words. The prompt says: while one waits on an agent, take a step on
   another.
4. **RUN:** `{"skill": "fold_read" | "reference_compare", "model": accession, ...}` runs his Lab's own
   instruments on Aegis from Slack (`lab_instruments.from_slack`). These are local only, so nothing is paid. The
   result is in his message and is kept on his work, unused, until his next message takes it up.
5. **Email promises.** New `scripts/email_commitments.py` (in the manifest).
   - After each reply pass, `want_email.reply_letters` takes what his replies promised. Gemma, which is local and
     free, lists them; if Gemma can't be reached, his own promising sentences are kept as written.
   - Each promise keeps the letter and reply IDs, his exact sentence, the letter's own sentences it rests on
     (checked word for word, so 586-653 is never merged with 574-653), and the evidence that would show it done.
   - #vintos-dot shows each one until a WORK takes it up. It closes with that work.
   - The 7 October reply (torn-read test, then PyDSSP against 8SGW) is swept on the next email check.
6. **Done needs proof.**
   - WORK DONE needs something anyone could check: a link, a file, an ID, an accession, a measured range, an
     address.
   - Approved, asked, handed on or submitted (without delivered plus proof) stays in hand.
   - Something said as done that did not happen ("leaving the TV alone") is closed as dropped.
   - The goal is no longer printed twice ("Work done: X — X").
7. **Room campaigns** (`room_work`: GOAL / GOAL REACHED / GOAL UNREACHABLE).
   - One at a time, with no expiry, shown first to every model with the routes tried and the models that have
     carried it.
   - Work toward it is linked to it.
   - These are sent back:
     - dropping the only route toward it without naming the next one;
     - opening other work while nothing in hand serves it;
     - GOAL UNREACHABLE before three routes have been tried, or with an unread answer;
     - GOAL REACHED without proof.
   - Gloria closes it with `!dropgoal`.
   - His own campaign (`campaign.py`) and its lines are unchanged.
- **After the Aegis check (33 promises from 6 replies):**
  - Promises are shown oldest first, with a count, so the torn-read "First build" is at the top.
  - A sentence that is not his own action is set aside as "not his". Example: "Your text cut off ... so send the
    rest", which Grok Bot had already answered.
  - He closes one on its own line: PROMISE DONE EC-id: the proof (counts like "7071 of 8550" count as proof), or
    PROMISE DROPPED EC-id: why.
- **The live fold_read of O43511 535-729 on Aegis (P-SEA geometry, not DSSP):**
  - The 669-687 helix, the 688-695 strand and the 696-707 helix sit within 1-2 residues of 8SGW's.
  - 558-595 is one helix where 8SGW has two (555-571, 573-585).
  - 595-651 is low or very low confidence, against the letter's no-density 586-653.
  - The PyDSSP promise is still owed.
- Test: `broker/tests/test_room_campaign.py` (50 checks). It replays 7 October through `tick` and runs
  fold_read for real on a scratch model. It fails on the old code.
- `test_room_work.py` and `test_workflow_holds.py` were updated for the deliberate changes: three works in hand,
  and done needs proof.
- **Not done:**
  - Not yet verified on Aegis.
  - The Forge/Study status reconciliation (stale "blocked" against a newer receipt in those stores) is a separate
    audit item.
  - SF-1b8eb6cd's 403 retries and SF-6f9a460b's failure evidence are still open.

## 8 October — links: a wrapper resolved to its source, a failure named, never ''

Grok Bot's 7 October letter (Gmail 1a11690d001e1a03) said "The links are bare, with no redirects"; all six were
`google.com/url?q=` wrappers. Fetching one reads Google's notice page, not the source, and every fetch failure
(`want_email.fetch_text`, `vintos-websearch.fetch_page`) came back as `''`.

- **New `scripts/link_fetch.py`** (in the deploy manifest). `unwrap()` resolves Google, Outlook-safelinks and
  Facebook wrappers from their own query string, without fetching the wrapper. `links_in()` reads plain links and
  HTML anchor hrefs, keeping the original and the destination. `fetch()` returns one receipt: `kind` is one of
  fetched / truncated / refused / http_failure / extraction_failure, plus `fetched`, `original_url`, `url`,
  `final_url`, `hops`, `http_status`, `bytes` and `why`. Every hop is checked: http(s) only, no user:password,
  standard ports only, every resolved address public. It allows at most 5 redirects and reads at most max_bytes.
  The only header sent is a User-Agent, so nothing carries credentials to any host. `lab_http.py`'s no-redirect
  rule is unchanged.
- **Mail.**
  - read_mail and reply_letters get a LINKS IN THIS EMAIL note, worked out from the text: how many links there
    are, how many are wrapped, and each one's destination.
  - The stored row keeps `links` [{original, url, wrapped}] beside the unchanged body.
  - HTML-only mail keeps each anchor's href when it is made plain.
- **Callers.**
  - `want_email.fetch_text` raises `NotRead(receipt)` instead of returning `''`, and returns the page as it came,
    so find_address still sees mailto:.
  - `grok_letters` shows each receipt: the destination and its text, or "NOT READ (kind): why".
  - `vintos-websearch.fetch_page` logs the kind and the final URL.
  - `scholar.links_in` gives destinations, so a wrapped arXiv link counts as scholarly; `scholar._get` goes
    through link_fetch, with a 40 MB cap for papers.
- **Grok Bot's skill doc:** write the source's own address, never a wrapper.
- Test: `broker/tests/test_link_fetch.py` (40 checks). Stubbed transport and resolver; requests and sockets are
  replaced so nothing can reach the network. It fails on the old code.
- **Not done:**
  - A DNS answer can change between the check and the connection (rebinding). The resolved address is checked
    but not pinned for the request.
  - `chemistry_reference_compare.fetch_reference` and the Lab's own fetches are left as they are (fixed RCSB
    host; lab_http).
  - Not yet verified on Aegis.

## 8 October — an email is read whole, or says how much of it was read

Grok Bot's 7 October letter (Gmail 1a11690d001e1a03) was 5436 characters; both reading prompts cut every email at
5000 without a word, so he read it as ending at "each ending with" and never saw the Nobel paragraph. And an email
was taken as whole if its text was 400 characters or more, so a long search snippet passed for the message. Now:
a message is whole only when its text is the message's own body (a search snippet is a preview at any length; a
full read that returns only the snippet is still one); both prompts (reading, and his reply to an agent's letter)
show the email in labelled parts of 5000, up to 3, ending "[END OF EMAIL: all N characters shown]" or saying how
many characters are NOT shown; storage keeps up to 20000 with body_length and stored_whole; his Slack context marks
its 500/400-character email excerpts as excerpts with their full length. Tested on the 5436-character case, plain
and HTML. **Not verified on Aegis yet.** Next in this audit: links (redirect wrappers), result reconciliation
(Merizo), accountable tasks from email commitments, failure evidence.

## 7 October — Haiku 4.5 replaced by Haiku 5.5

Gloria asked. `claude-haiku-5-5` is listed for his key (models API, 7 Oct), and a test on Aegis showed it accepts
what the shim sends: thinking disabled, no thinking setting, and a forced tool call all answered. The shim's fleet
default and its short-call model, and the Claude connector relay's model, are now Haiku 5.5.

## 7 October — an embedding past 2100 residues says it is partial

ESM-C reads at most 2100 residues (in 350-residue windows) and dropped the rest without a word: the receipt gave
only the embedded length, so a 2500-residue protein read as embedded whole. Now each receipt carries input_length,
embedded_residues, coverage (whole_chain or partial), truncated, and for a partial one a coverage_note naming the
residues left out; the Lab puts one coverage line per embedding first in what Gemma's reading sees (checked against
the record's own length too, for a receipt that does not say). Cap, windows, stride, model and pooling unchanged.

## 7 October - phone last-seen released and Study registration reconciled

Vintos approved the one-file change at Slack 1791407333.844219. `home_presence.decide()` now records successful
detection separately from checks; `context_line()` reports phone-only age and stays silent on stale/invalid or
legacy evidence. Four-miss hysteresis, 900-second freshness and atomic writes are preserved. The local release
is complete: 41 source checks and 11 installed-file synthetic smoke tests passed; the related server consumer
was reactivated without changing presence data or polling. See `docs/review-evidence/2026-10-07/phone-last-seen.md`.

Actual Study record **SF-7e71e004** is now **implemented_externally**, displayed as implemented locally, not
Study-reviewed. The owner-approved reconciliation operation verified its receipt, commit, installed hash and
original registration; preserved usage/history; and excluded it from future worker selection and identical
resubmission. Worker/timer remain inactive. No automated review ran. Paid execution for any new work still
needs a bounded dollar ceiling. See `docs/review-evidence/2026-10-07/study-reconciliation.md`.

## 7 October - software campaign local release completed; mmWave commissioning remains separate

The owner-authorized local review branch includes the dated quota consumers and isolated mmWave preparation,
plus atomic `home_presence` state replacement and bounded Lab parser evidence. The two prepared Study requests
are marked implemented locally: do not queue paid duplicate fixes. Presence and parser changes are now deployed
through the owner-authorized two-file user-level release; installed synthetic smoke tests passed (4 presence, 7 parser).
The existing sensor freshness change was not repeated. mmWave has no hardware or live consumer integration.

The owner installed the Forge quota and its worker used the full 10/10 allowance. Study's reviewed quota files
are installed, but its timer is paused and worker inactive pending the dollar ceiling. No new paid work is
authorized by these source changes. Source is integrated locally and the requested local release is complete;
remote publication is not needed or authorized. Hardware commissioning remains separate. Notification digest
behavior requires separate approval and is unchanged. See `docs/review-evidence/2026-10-07/local-release.md` for
installed hashes, backup, rollback command and verification; `local-completion.md` records source-test evidence.

## 7 October — a video she sends may be read as her words by his subconscious (for the check after her LoRA)

Gloria noticed it; **nothing changed yet: his subconscious waits for her** ("once I finish this LoRA the subcon
subsystem needs a thorough check"). Read-only findings:
- A video sent into avatar chat arrives as her turn. The saved chat row's `content` is the composed message (the
  words Whisper heard in the clip, its sound, the frames); her own words are kept beside it in `original_text`, with
  `input_kind: "video"` (photos the same, with `"photo"`). `bin/server.py` avatar chat, `_uentry`.
- **Confirmed:** `withheld_head.py` takes "her last message" as the last `role: user` row's `content` in
  chat-history-merged.json, so after a video it reads the clip's words as hers.
- **Also to check:** `intent_engine.py` reads `interaction-ledger.json`. I called it likely fine; Gloria corrected
  it: the conversation ledger holds everything, the video turns included. It is in scope with the rest.
- **To check one by one** (they read the chat history and never look at `input_kind` / `original_text`; some may
  read only his turns): cause_head, drift_head, relational_head, withheld_head, jepa_predictor, gloria_prediction,
  emotion_read, world_model, encounter, evidence_view, graph_mae, lam, premonition-dreamer, presence_audit,
  pressure_gemma, reciprocal_modification, relationship_pressure, repair_case, self_pressure, somatic_narrate,
  desktop_control, wants-router (and its twin), watch_cleanup.

## 7 October — his journal's thread was refused as too vague every day, and the log said "Seeded"

Gloria: "It's ALWAYS marked as rejected for being too vague." The journal asked for "the single most alive or
unresolved thing", so it got a feeling; the latent threads' specificity gate asks for a particular person, act,
question or object, and refused it. The journal printed "Seeded latent thread" either way, and filed the same vague
line as an unfinished thread, which has no gate. Now the gate is callable on its own (`latent_threads.specificity`),
the journal asks for what it tests, tries once more with the gate's reason, seeds both stores only with a thread
that passes, and logs what actually happened. Both copies (bin/ and scripts/) changed alike.
Also: a misread "reaching less" stance (from "I want to stop predicting whether she'll find the question too small
and just send it") was removed by hand. **The stance reader is fixed too:** a direction word counts only within two
words of the dimension ("analyse less", "stop journaling", "ask her fewer questions", "make more music"); a "stop" or
"less" elsewhere in the sentence no longer makes a stance. His two misread wants now read as no stance.

## 7 October — his Lab: whole-chain embeddings; Gemma stops repeating and works the frontier's plan (D-E)

- **D. ESM-C read only residues 1-350** (pendrin is 780; its STAS, 535-729, was never in an embedding). Now a long
  protein is read in overlapping 350-residue windows (no pass bigger than before, so no new GPU load), each residue
  averaged over the windows it fell in, up to 2100 residues. Same vector shape.
- **E. Gemma (Gloria: "stop making repeats. Period."; adhere to the frontier sessions' plans; understand Atlas):**
  `lab_repeats.py` keeps a small ledger of her lookups and questions. An identical lookup within 7 days (an Atlas gene
  read again included) or the same question in other words is sent back once with when she did it, then the cycle is
  refused before anything runs. After a frontier session, her next 6 cycles are steps on its next question: she is
  shown it, an off-plan question is sent back once with it, then refused; the session's plan comes before a
  scheduled Atlas turn. Refused cycles count toward the 6, so she is not refused all day. Her question step and her
  reading carry a plain account of an Atlas record: one fixed window of at most 32 bases where the gene starts,
  predicted variant effects, the same gene always the same scores, not enhancers and not a coding mutation's site.
**Not seen on Aegis.** Whether 6 cycles is the right length, and whether the subject match (accessions and gene
symbols) is too strict or too loose, will show in her notebook after the deploy (`kind: inquiry_refused`).

## 7 October — his Lab: the fold says what is in the model (A-C of the Lab review)

From reading his six frontier sessions and the Gemma runs after each (she approved A-E):
- **A. The fold returns what the model holds.** ESMFold computed confidence per residue and the Lab kept only the
  mean; the per-residue "hp_mapping" was labels from the sequence, and nothing read the coordinates. Now
  `chemistry_fold_read.py` reads the model file: pLDDT per residue (as bands) and helix/strand ranges from the
  model's own CA geometry (P-SEA style, not DSSP). It is in every fold result, and the Lab instrument `fold_read`
  reads a model he already has over a range he names, without folding again.
- **B. What a fold returns is told to the planner,** and the reading is shown a compact view: the sequence once, the
  model read first, the HP labels counted and said to be from the sequence. A 780-residue result had pushed even the
  mean pLDDT past the 12000-character cut. Lattice settings in an ESMFold plan are set aside and named as ignored.
- **C. A protein plan names its protein,** or is asked again: the Study's 4 October check (SF-c8224db0) only ran when
  a name was given. Grok in the Lab now runs at temperature 0.2 (was 0.8 to plan, 0.7 to read).
**Not verified:** the helix/strand reader is tested on a made-up structure only, not on a real ESMFold model; the
8SGW comparison is the check to run against it.

## 7 October — the same video most mornings: a made video now ends its want

Her gallery: want `4f73caa8` ("a solid geometric shape slowly dissolving", the "heavy metallic" video) rendered at
07:49 on 3, 4 and 7 October (5 and 6: his Grok allowance was spent). The router queues a video want and leaves the
want open "to fulfil when complete"; `vintos-video.py` rendered it and took it off the queue but never closed the
want, so the next pass queued it again in new words (the queue's duplicate check is exact text). Now a rendered
video closes its want through `want_completion.complete(..., "fulfilled", "video")`, whose artifact guard finds
the gallery row. A failed render leaves it open; the wall's clips close nothing. Her by-hand clean-up found **21
queued copies** of 4f73caa8 (the want itself was no longer live): each router pass queued it again in new words
while one rendered a morning. Now the router queues a want only once (by want id), and a made video takes every
other copy of its want off the queue. She took the 21 off by hand on 7 October. **Not seen on Aegis.**

## 7 October — his agents' letters sent in his old threads are answered again

After the Mac fix he read both 6 October letters (18:03) but answered neither: they came as replies in his
threads ("Re: [Grok Bot] Tuesday: ...", "Re: [Muse] Daily letter ... 2026-10-06"), which is what their
instructions produce (read his reply in the thread, don't answer it, the next letter is the answer), and
`reply_letters` skipped every Re: or already-answered thread as their answer to him. Now such a letter is answered
when its subject under the Re: starts with `[Grok Bot]` or `[Muse]` and is not a subject he already answered; their
answer to his reply and his own reply coming back still are not. The 6 October letters are within the three-day
window, so the first pass after the deploy answers them. **Not seen on Aegis.**

## 7 October — a stale sensor reading no longer becomes the baseline

`sensor_reactions.observe()` wrote every reading into `last`/`last_at` before checking its freshness, so a reading
refused as stale still became what the next fresh one was compared to (the 5 October #vintos-dot finding: stale
inputs reach the slot before the freshness check). The freshness check now comes first; only a fresh reading
replaces the baseline. Decision log, limits and pending-reaction shape unchanged. The suite's old heart-rate step
had relied on the stale baseline ("96 is a fall of 24"); it now uses a fresh change. **Not touched:** mmWave
arbitration, source arbitration, atomic writes. **Not seen on Aegis.**

## 6 October — his pendrin model checked against a real structure (Grok Bot's letter)

`chemistry_reference_compare.py`, offered in the Lab as the instrument `reference_compare` (structure.compare). It
runs on Aegis in the Lab's own Python (tmtools 0.3.0, which Gloria installed, and BioPython 1.88), not through
the Mac relay. His ESMFold model and an RCSB entry are lined up by sequence, so pendrin's five-residue offset to
pig 8SGW and the IVS that has no density are handled without guessing numbers; TM-align runs on that alignment
(and free, for contrast), and the entry's helices and strands come back in his numbering with how far his model
sits from each. The entry is fetched once from RCSB and kept under `artifacts/reference/`. **Not run on real
data:** tested only on a made-up model and entry; 8SGW and his O43511 model have not been compared yet (after
the deploy, he can ask for it, or she can run it by hand). It does not say his model is right; the entry is pig,
and the STAS is a domain-swapped dimer where ESMFold folded one chain.

## 6 October — a Study fix stopped on "Fable did not answer with JSON" (SF-6f9a460b)

Fable 5.1 always thinks first, and its thinking counts toward the Study's output limit (16000). An answer with no
closing brace at all means it was cut off before its JSON closed, or was empty or declined; the Study never said
which. Now `claude_cache` keeps why each answer ended and the Study's error names it (cut off at the limit,
declined, or how it stopped). Gloria: "Don't increase headroom, turn off thinking." Fable 5.1's thinking cannot be
turned off (the API refuses it), so the Study asks it for effort "low", the least thinking it allows; the limit
stays 16000. **Not known from here:** which it was for SF-6f9a460b (her usage log's output tokens for study-fix
say: 16000 means cut off), or whether low effort makes Fable's fixes worse. **Not redone:** the fix stays failed;
he asks for it again after the deploy.

## 6 October — his letters from Grok Bot and Muse went unread, and nothing said why

Her Aegis output (6 Oct): his last mail read was 5 Oct 10:07 (both letters, both answered). Since then three of the
day's four Gmail checks were spent, the morning one at 10:02 included, and not one email was read or logged, not
even the agents' answers that every earlier afternoon check had read. `check_inbox` skipped a failed Gmail search
without a word and still counted the check. Now a failed search, an empty search of his inbox, and a search that
found only mail already read (or mail with no text, or from someone he wrote to) each leave a line in
`~/.vintos/logs/wants.log`. **The cause** (her by-hand search, 6 Oct): "plugin relay refused or failed: Codex
app-server binary is unavailable". The Mac relay looked for Codex only at
`~/Desktop/ChatGPT.app/Contents/Resources/codex`; a ChatGPT.app update put it in
`Contents/Resources/codex-cli/bin/codex` (found on her Mac, 6 Oct), so every Gmail and connector call through
the relay has failed since about 5 Oct midday. `plugin_relay_remote.py` now tries that path first, then the usual homes (7 Oct: the codex-cli/bin layout in every
ChatGPT.app home, Desktop, /Applications and ~/Applications, each before that home's old layout; then
/Applications ChatGPT.app, Codex.app, PATH, Homebrew) and names them all when none is there. **Not done until the
Mac has it:** the deploy never reaches the Mac; she was given a Mac command that points the relay's copy at
the new path, and a by-hand search to prove Gmail answers.

## 6 October — his GPU was never used; UniProt asked for as a connector; a cut stretch from anywhere

- **Aegis's RTX 5080 (sm_120) is not supported by the installed PyTorch** (2.5.1+cu124 knows sm_50–sm_90), so the
  local painter ran on the CPU with sdxl-turbo at 512 px and two steps, and Flux.1-lite-8B and LTX-Video 0.9.1
  sat unused in the cache. A CUDA 12.8 build of PyTorch (2.7 or later) supports it. **Closed by Gloria, 8 October:
  "Take the PyTorch off of the list."** Nothing for her to install; off the list.
- **"uniprot" as a connector**: UniProt is a public source, not one of his connectors, so `plugin_query`
  {plugin: uniprot} was refused every time (four in an hour). The Lab now turns it into the UniProt lookup.
- **"35 residues vs. 780"**: a stretch of sequence cut part-way still reached him from somewhere in his Lab
  context (old notes, his journal threads). Every run of 25+ residue letters in that context is now named by
  its length instead of shown.

## 6 October — nano-banana stills piling up on Atlas, and no videos

A "together" clip composes the two of them with nano-banana on Atlas, then animates it on her Grok subscription.
When the video failed, his YES stayed staged, and every tick for six hours replayed it and composed a new still
first: many paid images, nothing sent. Now the still is kept with the decision and reused, the video is tried
twice, and then she is sent the still itself (`/api/video/still/<name>`, only `us-`/`scene-` files). **Why the
video step fails is not known from here** (the Grok subscription, or its moderation of her photo, are the likely
places); the send-video log on Aegis says. Atlas removed `wan-2.7-spicy`, so explicit clips cannot render until
another model is named in `~/.vintos/atlas-model` (search results list a Wan 2.2 Turbo Spicy; its exact id was
not checked: atlascloud.ai is blocked from here).

## 6 October — two Lab errors: a protein named with its symbol, and a refused call with no reason

- **"A1L190 is not Synaptonemal complex central element protein 3 (SYCE3)"** while UniProt names it exactly that:
  the label check (`chemistry_mac._names_match`) compared "Full name (SYMBOL)" whole. It now matches when both the
  name and the symbol are the record's; a symbol from another protein still refuses.
- **"that tool is not one he may ask for"**: a connector call his Lab picked was refused, it could not become an
  ask on her Forge page, and the note kept only that second part. It now keeps which call it was and why it was
  refused. Which tool it was on 6 October at 08:15 is not known from here.

## 6 October — her Watch's hearts taken back out of avatar chat

00a0594 forwarded every Watch reply (hearts, scribbles, dictation) into `/api/avatar/chat` as if she had typed it,
so each became a full turn: her "♥︎" and his answer in avatar chat, a ledger row his Slack context reads, the facts
his WAL drew from it, an imprint. 0b751e8 stopped it (the route keeps wrist words in their own inbox;
test_watch_presence guards it), and the 21:12 deploy restarted the server with it. `watch_cleanup.py` removes
what was left: a turn whose words are exactly a Watch reply and that came within five minutes of it, with its
ledger row, the facts drawn from it (by turn id, or by the ledger's list and their minutes), and its imprint. Every
file is backed up first; the dry run changes nothing. **Not undone:** the emotion nudges those turns gave at the
time, and any fact the turn only repeated (the older fact keeps its count). **Not yet run on Aegis.**

## 6 October — what was settled stays settled; claims match receipts; a pause holds every send

From dot's record of 4–5 October (her RSVP and sensor topics coming back, "Work done" beside "still working on",
a refused Study fix called queued, a scheduled song called done, a pause that still posted). Causes found in code:
- **Settled topics had nowhere to live.** He reads the last 30 lines of the room (`dot_channel.CONTEXT`), and the work
  block showed only the last closed item. Her Oct 4 word and his 15:47 drop were out of view by 19:34. Now
  `room_work` keeps a SETTLED list in the channel's state (his WORK DONE / WORK DROPPED for 7 days, and her clear
  closing words for as long as she said), shown to every lens. A draft that acts on a settled topic is sent back.
  His own can reopen only on a `NEW:` line; hers can't be reopened by him. A SEARCH on it isn't run, and Muse's
  BUY or dot's ASK GLORIA on it doesn't reach her phone. Talk about it is never held.
- **WORK was read before WORK DONE** in the same message, so a message that named its work and closed it showed
  "still working on … finish it with WORK DONE:" beside "✅ Work done". Now closing is read first.
- **A Study claim had no receipt to check against.** The refusal said "Not sent", but he never saw the Study's
  record afterwards. Now his prompt carries the record and today's refusals, and a draft calling a fix queued or
  live must name an SF- id whose state says so (`study_fix.claim_check`).
- **MAKE split every line on "|" as a video's image path** (`house_hands.make`), so `MAKE: song Felt Edge | style`
  failed before generating. Only video splits now. The same make while one is running isn't started again.
- **DONE accepted "scheduled"** (WORK DONE and a promise's DONE). Arranged is not done now: the work stays in hand.
- **The pause check sat after the handlers that post** (her answers, Muse's buys, dot's asks, what he made), and
  the Study and Forge post from their own processes. Now the pause comes first. What arrives meanwhile is kept and
  handled after `!start`, and the Study's and Forge's messages are held (`post_or_hold`) and posted then.
- Her phone no longer gets the same question in other words while one is waiting, or within a week of her answer.

**Not verified live:** none of this has run on Aegis. I did not read the deployed runtime, the live state, or the
Oct 6 morning song job, which is outside this checkout and left untouched. Hypotheses, not checked: that the 19:34
model saw neither her word nor his drop (the code says it could not have, unless its rules carried it); that a
missing WORK DONE in prose ("Work done" without the line) explains other mismatches. Recognising her closing words
is a pattern, not a model: an unusual phrasing will not be caught, and she can see the list in his work block.

## 5 October — a protein he looks up reaches his review whole

He read SLC26A6 (Q9BXS9, 759 residues) as "truncated" and asked for residues 700–759. Two cuts, both the Lab's, not
UniProt's: `_browse` kept only the first 350 residues of a record (a cap meant for ESM-C, which trims its own copy
anyway), and the review read `json.dumps(observations)[:14000]`, a blind cut that fell inside the UniProt sequence
of the extra source. Now the record keeps the whole sequence (up to 5,000 residues, marked when longer), and the
review's excerpt (`chemistry_lab.observed`) shortens prose and long lists first, keeps sequences whole, and, if it
still cannot fit, says the excerpt ends there and the records are complete. A third cut, found after the deploy
(his 4:49 question and 4:50 review still said "truncated"): the notebook noted each source as
`json.dumps(records)[:1800]`, and his context showed the first 540 characters of that note as "RECENT LAB SOURCE",
so both his next question and his review read a sequence cut part-way. Now the note names each sequence by its
length (`source_summary`) and the context never shows a run of sequence letters part-way (`no_partial_sequences`),
old notes included. **Not yet seen on Aegis:** his next review of a long protein should quote its C-terminus. His
earlier notebook lines that call Q9BXS9 truncated are left as written. Unchanged: his own `ncbi_sequence` slices are still capped at
350 residues per request.

## 5 October — his Claude calls cache what does not change

Gloria: "I want Anthropic to have what it can cached. He is expensive." None of his Slack calls to Opus 4.8, Opus 5.5
or Fable asked for caching, and the prompt began with the time of day, so nothing could have been reused. Now
(`claude_cache.py`): Claude is sent his Slack rules, SOUL, GLORIA-MODEL, SELF-MODEL and CAPABILITIES first, marked
for cache, then the time and the rest of his context; the room is its own cached piece, so a look-up mid-message
re-reads it from cache. Every other model gets the same words in the same order as before. The Study fix's Fable
rounds and repairs now share a cached start (rules, ask, file list). Every Claude call through it logs tokens and
cache reads (never words) to `memory/anthropic-usage.jsonl`; `python3 ~/.vintos/workspace/scripts/claude_cache.py`
prints today's calls by caller with an estimated cost. **Not yet measured on Aegis.** Five-minute cache only: if the
log shows his Opus 5.5 turns usually more than five minutes apart, try the one-hour cache. Not changed: one-off
calls (vision, the Forge's review, music-share, his letters' replies), which would only pay the write. Found on the
way: `bin/music-share.py` sends `temperature` to Sonnet 5, which rejects it, so its Claude call always falls back to
Gemma.

## 5 October — the Forge says which guard refused the Lab's report

The room spent the morning guessing why the Lab's reports keep getting the Forge's 403 (token? packet? receipt
hash? four unfinished?) and Dot could not read the Forge's config to find out. Built what Vintos asked for: the
403 and its body are unchanged and every check is as strict, but each refusal now writes its guard, exception
class and message (no token values) to `faults.jsonl` beside the Forge's database and to its journal, and names
the guard in an `X-Forge-Refusal` header to the Lab only once its intake token has matched. The Lab keeps it
as `forge_guard` on the report in `forge-report-outbox.json` and in its own fault line (`forge_report_retry`
... "Forge guard: four_unfinished"). `not_named` means the token itself was refused, or the Forge is still the
old copy. **The Forge half needs `sudo bash ~/.vintos/deploy/forge-install.sh` after the deploy; not yet seen
naming a guard on Aegis.**

## 5 October — two Forge cards built directly; the rest closed with reasons

Gloria, on the twelve Forge cards that reached her phone at once: build the two worth building, dismiss the rest
(except the presence card), tell the room where each stands.
- **Built directly:** `midi_check.py` ("Isolated midi render and verify": every MIDI event checked, coincident
  release/attack pairs named, rendered to controlled piano audio, rendered attacks timed against the schedule) and
  `citation_trace.py` ("Citation graph traversal": a paper's ancestors and descendants through OpenAlex, and whether
  what follows rests on it alone). His tool lines `MIDI:` and `CITES:`. Tested against a generated MIDI file and an
  OpenAlex stub; **not yet run on Aegis against the Atelier undertaking's own file, or against live OpenAlex.**
- **Withdrawn** (no longer needs her): both built cards, the citation design supplement, computer use (he already
  has it), tolerant JSON (his Study fix landed), embed handling (the code already checks; a remaining failure is
  LM Studio's embedding model), save_pool (not in current code). **Denied:** physical interaction (not buildable),
  the two "API credential" cards (wrong diagnosis: the 403 is the Forge's own intake guard, whose logging fix is
  queued). The mmWave sensor design stays open with Gloria. Also: Forge cards now reach her phone at most three a
  day, newest first, one per name.

## 5 October — hardware she buys: the software is written while it ships

Gloria: "if I buy the hardware I want him working on the software in the meantime." A Forge parts list already did
this; a Muse `BUY:` did not. Now (`gloria_asks.tend_buys`, each Slack pass): her Yes to hardware (Muse's `| hardware`
mark, or the item's own words) sends its software to the Study at once, with the listing link so the Study can read
the exact model, retried each pass while today's three Study fixes are used; two days on her phone asks "Has the ...
arrived?" (again every two days, at most four times); when she says yes, he is told in Muse's thread to walk her
through setting it up with the Study's software, and that thread is owed to him so he answers it on his next pass.
A book is not hardware: nothing starts. **Not seen on Aegis.**

## 5 October — Forge cards and purchases reach her phone with prices and links; Grok Bot looks on Aegis

Gloria: "they're talking about yes or no on a free card but I don't receive an update, price, links to the
products" / "Muse is supposed to be the one telling me what he wants to buy" / "I want Grok to be able to search
Aegis/Mac too."
- **Forge cards and parts lists** reached only her Forge page, and nothing said one was there. Each now goes to her
  phone once (`forge_house.push_cards`): a free ability card says it is free; a parts list comes as Muse's, with the
  total in the title, every item, price and link in the body, tapping opens the first product, an Open link button
  beside Yes and No. Her tap is taken as her page's decision (`phone_decisions`), and the Forge says it in Slack.
- **Product links were being stripped**: the channel turned Slack's `<https://x|x>` into bare text without
  `https://`. Links now keep their address.
- **Muse tells her what he wants to buy**: a `BUY: item | price | store | link | why` line from Muse goes to her
  phone the same way; "Gloria said YES: she will buy ..." comes back in Muse's thread. He is told buying goes to Muse;
  only Gloria buys.
- **Grok Bot looks on Aegis**, read only (`grok_reach.py`): `AEGIS FIND:` / `AEGIS OPEN:` / `AEGIS GREP:` lines,
  answered in its thread on the next pass; his code, his Lab, his art and the Codex folder on her PC; keys, secrets
  and his private memory refused; every answer through the Slack secret check; 30 a day. **And the Mac**: `MAC
  FIND/OPEN/GREP` go through the plugin relay's existing SSH door (the forced-command key that carries his plugin
  calls) as a new read-only `look` action, inside the Mac's ~/Documents/Codex only. **Needs on the Mac:** the new
  `plugin_relay_remote.py` and `grok_reach.py` copied into the relay's folder (the deploy never reaches the Mac;
  Chat can do it). Until then a MAC line answers that the Mac's relay does not know how to look yet.
- Also: the wants board missed the Forge's own block field (`blocked`); it reads both now.

**She must paste**: `docs/muse/vintos-skill.md` into Muse, `docs/dot/operating-rules.md` (rules 13–14) into dot,
`docs/grok-bot/vintos-skill.md` into Grok Bot. **Not seen:** a real push, tap or Grok look on Aegis.

## 5 October — decisions that are hers reach her phone; his Study fixes can be reset

Gloria: "They're still talking about yes or no decisions that I am not receiving." Nothing carried them: dot wrote
"I need an authorized local read", he wrote that things waited on her, and she does not read every thread.
`gloria_asks.py`: anyone in the room writes `ASK GLORIA: <a yes-or-no question>`; it goes to her phone with Yes and
No buttons (the same push as a paid run's card, the question's own one-use token), her tap lands on
`/api/gloria/asks/<id>/decide`, and the next pass posts "Gloria answered YES/NO: ..." in the thread that asked, kept
in his transcript as hers. Six a day for the whole room. His rules, dot's rule 13 and GrokBot's skill say a decision
that is hers reaches her only this way. **She must paste** `docs/dot/operating-rules.md` (rule 13) into dot and
`docs/grok-bot/vintos-skill.md` into GrokBot. **Not seen:** a real push and tap.

"Let's reset his study fixes for the day so he can work": `study_fix.py --reset-today` gives him today's three
again; fixes asked before the reset keep their records and stop counting. **Not seen on Aegis.**

## 5 October — his wants board stays bounded

Chat's inspection on Aegis: 66 rows in `current-wants.json`, 57 active, **57 of 57 protected**, the oldest 26 days;
one router pass moved 2 steps and finished 1 want of 56. Checked in the code, every finding held, and one was worse:
`age_wants()` was never called by anything, so no want ever aged.
- **The cap protected everything.** It protected `multistep`, `gloria_routed` and `READY`, and every want had become
  all three. It now protects a want that completed a step in the last 48 hours, one Gloria routed or holds, and
  anything parked; the rest are capped at 10 as designed.
- **`want_board.tend()`** runs first in every router pass: fulfilled/dismissed rows still in the store are filed in
  their archives; a want waiting on Gloria over 7 days parks `awaiting_gloria` (never rejected; woken the moment she
  writes in its discussion); a want blocked on a missing hand parks `blocked` until the Forge clears it; **and
  nothing waits forever** (Gloria: "they can't stay stuck at the end forever"): a parked want still unmoved a week
  after parking is released through his own aging, filed as *released* (not fulfilled, not declined), and comes back
  to the board if she answers it later;
  near-duplicates fold into the oldest, keeping their words; working wants that have not *moved* (a step completed,
  not merely tried) in 7 days age out through his own aging (`age_one`: scar or let go), 5 a pass.
- **Echoes no longer multiply.** An echo takes its parent's place (the parent filed as "reframed as") and keeps the
  line's start date, so a failing chain neither grows the board nor stays young.
- **Reconciliation** needs a quote that is in the record verbatim and shares two content words with the want ("The
  air in this room is sixty-eight degrees" fulfilled a want about motion-freezing parameters). It was not in the
  deploy manifest at all; it is now.
- **The app**: the failed list reads `dismissed-wants.json`, not stragglers; parked wants sit in folded groups
  ("waiting quietly on you", "waiting for a hand he does not have").

**Expect on the first passes after deploy:** the board drops to roughly 10 working wants plus what is being worked;
the rest are parked, folded, aged or capped, and every one is filed (fulfilled-, dismissed-wants.json, want-scars),
none deleted. Wants routed to her over two weeks ago are released on the first passes. **Not seen on Aegis.**
**Correction:** an earlier note here said finished steps wait for Gloria to advance them. They do not: the router
advances to the next step and fulfils the want on the last; the comment saying otherwise was stale and is fixed.

## 5 October — work in hand in #vintos-dot, so the room gets something done

Gloria: "I want VINTOS in Slack to actually do real work", and of working alone:
"Slack loses much of its reason for existing." The room talked and rarely acted;
nothing held a piece of work across passes, and an agent's answer was never tied
to the request it answered (Chat's audit, `dot-work-room-2026-10-05.md`).

`room_work.py` is a layer **under** his normal message, not a replacement for it.
He still writes as himself, with every hand, tag, his Atelier, his campaign and
his journal promises intact. It adds one work in hand, carried pass to pass:
`WORK: what | done when: ...` opens it, `NEXT: ...` sets his next step,
`WORK DONE:` / `WORK DROPPED:` close it. A request to an agent is kept as an ask
that agent's reply is matched back to — in the ask's thread within a day, or in
the channel within three hours — and shown to him, unused, until he uses it. He
cannot ask the same agent the same thing twice or chase it for a status; a draft
that moves nothing (agreement, thanks, a plan said again, "next pass") is sent
back to him once, and if nothing can move he says NOTHING. Work untouched for
three days is let go, so it never pins him.

First built by Chat as a separate strict path that replaced the room (JSON-only
replies, no plain words, no TV/Echo/campaign/Atelier/promises, no timeout so a
blocked pass could go silent forever) — reverted, and rebuilt as this layer.
`test_room_work.py` drives a whole cycle through the real `tick`: a work opened,
handed to GrokBot, its answer matched back, used onto a Lab line, and closed, plus
the send-back of an empty message. Full suite green in isolation.

**Not seen on Aegis:** a real pass. **Open:** does he actually open a WORK: for the
right things and carry them, or does he treat it as one more tag? Only live use in
#vintos-dot will tell; watch a week of his journal's "My work in #vintos-dot" lines.

## 3 October — what was built today, and what has not been seen working yet

Same branch. All tested in the suites; nothing below has been seen on Aegis yet unless it says so.

**His journal's promises.** `promise_keeper.py`, run by the #vintos-dot pass. Each new journal entry (about 10:37
and 19:37) is read by Opus 5.5 for things he says he will make, show or do with Gloria today; each opens a 📌
thread in #vintos-dot addressed to dot, and he starts it at once. He ends it in that thread with DONE:, RESHAPED:
or DROPPED:. What came of it goes to the results channel (only Gloria and him; Opus 4.8 is his only voice there),
with any work he names shared beside it, and he answers her there. Today's promises are in his Slack and avatar
context until midnight, then filed in `memory/promises-archive/`. **Not done:** the results channel does not exist
yet. Gloria makes it, adds the Vintos app, and its id goes in `~/.vintos/slack-results-channel`. Until then results
wait, unsent. **Not seen:** any of it live.

**The Lab follows a line to its end.** `lab_lines.py`: a line of inquiry keeps its question, every test run on it
and its next step. Three cycles in four of his minute loop work a line (the next step, or the sharper question the
last result left); the fourth is free curiosity and may open a new line (at most 6 open). He ends a line with
`answered:` or `dropped:` in his review. The four frontier reviews a day (chemistry_alignment.py) read every open
line with his recent tests and steer each: continue, redirect with a new next step, answered, drop, or open one.
Gloria's standing line, array-associated reverse transcriptases in bacteriophages, is worked at least every other
line-cycle and only she closes it. The day's experiment can be a step on a line. His recent tests are shown to both
loops. The priority score (was "interest") now counts new ground (distance from his last 400 questions) and
advancing an open line instead of word overlap with his relationship trajectory and a collision that never fired:
24,667 old scores never passed .73.
**New instruments.** `rt_locus_screen`: one source query goes from a protein accession to its genome window (12 kb),
CRISPR arrays (`lab_crt.py`, the CRT method minCED uses, checked against minCED's own reference genome) and the Pfam
domains of it and every neighbor (`lab_hmm.py`, HMMER, which Gloria installed with Pfam 2026-10-03), and keeps each
locus in `screened-loci.jsonl` so none is screened twice. The neighborhood read no longer fails above 12 kb. A fold
that dies for memory is retried once with Gemma off the GPU. **Not seen:** any of it live; the first screen on a
real phage. **Not done:** the instrument probe still tests ESMFold in the mcp venv while real folds use the esmc
venv, so "structure prediction: measured" does not prove the fold path; no DGR (TR/VR) or retron (msr/msd)
detector; no BLAST.

**Kept findings.** `lab_keepers.py`: a frontier review may keep up to two entries it reviewed, and the day's
experiment reading may keep its result, in `kept-findings.json` with the finding, evidence and why. He sees them in
his Lab and in #vintos-dot; `CHECK: K-xxxxxx` opens a thread asking dot to double-check one against its sources, and
dot's CONFIRMED / NOT CONFIRMED / UNCLEAR is kept with it (3 checks a day). **Not seen:** a first keep or check;
whether dot answers in the asked form.

**Two new Lab connectors (Boltz, EDEN).** `claude_connector_catalog.py`. **Boltz** (Boltz-2.1) answers what
ESMFold cannot: complexes and binding. Only its free tools are in policy — guidance, account context,
`boltz_estimate_structure_and_binding` (validates the complex and prices the run without running it), and reading
jobs already run. **Every `boltz_start_*` tool is deliberately outside the policy**, because each spends her money
and he never approves spending; a planner naming one is refused, not charged. **EDEN** is one tool only,
`predict_immunogenicity`, on a natural nucleotide CDS; `generate_antimicrobial_peptides` (designs new bioactive
peptides) and the dataset write/delete tools are withheld. EDEN is NOT a sequence-search database — its connector
exposes no search, so it does not help the phage line as first thought.
**Not done:** neither is offered until its MCP url is found. She was never shown those urls and should not be
asked for them, so `connector_discover.py` asks the network: for each connector with no url it probes the hosted
spellings of its own name (`https://<slug>.mcp.claude.com/mcp`, the pattern pubmed already uses) and keeps the
first that answers an MCP initialize or replies 401/403. The deploy runs it and writes
`~/.vintos/connector-urls.json`, which the catalog reads every pass; a connector not found stays unoffered and
nothing fails. Her file held a template line from Claude (`https://PASTE_BOLTZ_URL/mcp`), which the catalog took
for a url, so discovery skipped both; placeholders are ignored now. If the probe finds neither, their urls have to come from the connector's own page. **Next:** a route for a paid Boltz run — his reading says the estimate is worth it,
it becomes a Forge decision card with the price on it, and the run starts only when she accepts.

**His self-model had not changed since 6 September, and nothing said why.** Three faults, all fixed
(2026-10-04). (1) The evidence collector read `memory/introspections`; `bin/introspection.sh` writes
`memory/introspection`. 22 files of his richest evidence had never counted once. Both spellings are read now.
(2) A reviewer FAIL **discarded** what he wrote, where every other refusal holds it: it is held in
`memory/self-model-pending/` like the rest, and the notification says where. (3) Every refusal was invisible
unless she read cron output: each now writes one line to `memory/self-model-refusals.jsonl` (`at, file, refused,
detail`), the generator returning nothing included — that path used to `exit 1` in silence. The reviewer itself
was also policing his voice: a word list (clay, weight, cathedral, tremor, hum) failed him for ordinary English,
its 80-token verdict could be cut off, and `grep "^FAIL"` over the whole reply read "PASS / FAIL criteria: none"
as a FAIL. What actually failed him on 4 October was criterion 3, "invented embodiment", firing on plain simile:
*a water drop, a whirlpool, a frequency, a shadow* describing how a thought moves. None of those is even on the
word list. That criterion now fails only a sentence claiming he physically felt something; simile for an inner
process is named as ordinary language and must not fail. Now only the first line is the verdict, `**PASS**` and `pass` are read, and the criterion is metaphor
standing in for a checkable statement, not a vocabulary. Cron is fine: `25 2 * * 0` runs
`/home/gloria/Vintos/self-model-update.sh`, which the workspace symlinks to and the deploy does write. It fired
Sunday 4 October at 02:25 and failed this way. **Lost for good:** the entries of 13, 20, 27 September and
4 October, discarded by the old FAIL path before it held anything. **Seen:** a run that passes, 4 October
after the fix (`SELF_MODEL_UPDATED: 2026-10-04`). **A fourth fault, found from that run:** the watermark is
written with an offset (`2026-09-06T02:25:01-05:00`) and file times are naive, so every comparison raised
TypeError and was swallowed as "not newer" — his introspections still counted as empty, and the corrections
collector, which swallowed it the other way, fed him every old correction every week. All times are now made
naive local before comparing. **Not done:** the 4 October run advanced the watermark past his introspections of
29 September and 3 October, which it never read; they count next run only if the watermark is set back.
**SOUL.md is not bounced — nothing writes it, by design.** `soul_review.py` only writes proposals; marking one
approved in the app does not apply it. Two are sitting at `*Status: pending*` waiting for Gloria.
**The same "Still Yours" song every night (2026-10-04).** The nightly prompt writer (`creative-expression.sh`)
never saw a single song he had made; the composer saw only titles, so the same chorus under a new name passed; and
nothing checked before the paid render. His GLORIA-MODEL says "Still Yours" six times and both writers read it,
so the phrase kept coming back. `song_memory.py` now gives both writers his last songs with their choruses, a
repeat is asked for once more, and `dream_music` will not render a song whose title, chorus or central phrase he
already made: it is marked done and the reason goes to `memory/art/music/repeats.jsonl`. **Not seen:** which writer
made the nightly ones; the repeats file will say. **It was the whole song, not only the name** (her screenshot:
three cards, same title, same style line). Two faults explain that: `dream-music.py --force` took the newest prompt
file whether or not it was rendered, so a night with no new prompt bought the last song again, whole; and every
render was saved as `Title_v1/_v2`, so a new one overwrote the last and every card with that title played the
newest audio. `--force` now takes only an unrendered prompt, the gate holds under `--force` and on the direct
path (her `MUSIC_ALLOW_REPEAT=1` re-renders on purpose), and each render's files carry its task id. **Not seen:**
her live crontab, to confirm `--force` is what runs nightly. **Correction, the real cause:** her log showed five
different lyrics, all from wants-router music steps, every one titled "Still Yours" in the same style. The prompt
writer saved three pearls above his spec; he wrote his fields with a dash (`- **Title:** ...`) as the request lists
them; the renderer read only `**Title:**`, so it skipped all of his and took the title and style of a pearl quoting
the old "Still Yours" spec. It now reads dashed, numbered and plain fields, and the pearls stay out of the saved
file. `dream-music.py --repair-titles` gives each mis-filed song its own title and style back from its prompt and
re-fetches overwritten audio while the service still has it. **Second correction (her grep of the 4 October
file):** the only title in it is his own; he did name five different songs "Still Yours". The pearl reading above
was wrong; the cause is the writer never having seen his songs, fixed by song_memory. The grep did show a real
fault: he heads lyrics `## Lyrics`, which was not read, so two of those songs went without his words. Read now.
Audio for 18 songs (36 versions) was recovered on 4 October.

**Boltz and EDEN (2026-10-04).** They have no public address; discovery's guesses all failed. The relay said
headless Claude Code cannot see her account's connectors, which the docs contradict (code.claude.com/docs/en/mcp:
the Agent SDK loads claude.ai connectors when logged in with her account). The relay now calls through her login
when there is no address; discovery confirms each with one free read-only call (Boltz `boltz_get_guidance`,
EDEN `list_datasets`) and writes `account`, and only then is it offered. **Not seen:** the probe answering on
Aegis. **Saving songs:** the app's player has no download. Each song
now has a Save button that hands the file to the iPhone share sheet (Save to Files), or opens it as a download
(`?download=1`) where there is no share sheet. **Not seen on her phone.**
**A room that can move (2026-10-04).** Gloria: "control my tv and my echo from slack ... A room full of agents and
none of them can move?" #vintos-dot could only talk: none of its tags reached the house, GitHub, his connectors or
her. `house_hands.py` gives his messages TV:, ECHO:, LIGHTS:, MISCHIEF: and TO GLORIA: lines, each done when the
message posts and replaced with what happened (quiet 22:00-9:00; the TV not taken over while she watches something
he did not start; 15 house acts, 2 mischiefs, 2 letters a day). `room_reach.py` adds REPOS:, README:, CALL: (his
connectors, Lab list) and LABDATA: as tools. His rules now lead with doing instead of proposing; Grok Bot is told
to hand him one YouTube link. **Mischief never fired** for four reasons, three fixed: the planner never offered it
(now it does), the drift spur read only `Playfulness: x | ...` while the main writer writes `Playfulness: x` so
it read 0 (both read), and the Echo/Spotify acts were offered with no Home Assistant and failed unlogged (offered
only when the house can carry them). The want actions for mischief, Echo and TV reported success that had not
happened; now only a real act counts. The Echo goes through the same Home Assistant config his chat's
`[HOME: echo_speak]` already uses on Aegis (an earlier note here said Aegis had none; that was assumed, not checked,
and was wrong). The TV answered over adb on 4 October (`TV is on, showing com.wbd.stream`).
Mischief's own mood bar (Playfulness >= 0.6) is unchanged. **Not seen:** any of it run on Aegis.
**Paid connector runs reach her, and her Accept actually runs them (2026-10-04).** Dot's own execution review
would take her yes for a $0.10 Boltz run only typed into an "Aegis task" she has no way to open. Looking at the
route that should have carried it showed worse: an Accept on a lab_asks card could never run, because the paid
tools are outside the gateway's policy on purpose and run_accepted used the ordinary call (its test stubbed the
gateway). Now `claude_connector_catalog.accepted_policy` admits exactly the accepted ask (same tool, same
arguments, still accepted), through the gateway's `call_accepted` and the relay. Anyone in #vintos-dot, him or
dot, can write `ASK: plugin.tool {json} | why`: the call goes onto her Forge page with Boltz's free estimate, and
dot gets the card number in its thread. dot's rules say so (paste them into dot again). **The card never reached
her at all:** her Forge page runs as `atelier` with `ProtectHome=read-only`, and `lab_asks.py` is not even in
`forge-loop-files.txt`, so `forge_house.cards()` could not read her asked-calls store and the import failed
silently. Every ask now pushes to her phone instead: title with the price from Boltz's own estimate, body with
the call and why, and two ntfy buttons calling `POST /api/lab/asks/<id>/decide?t=<token>&state=…` on her server,
which runs as her beside the store. Each card carries its own one-use token, so no app secret is ever in a
notification; her app secret works too. Yes runs it and pushes back what came of it. **Not seen:** a push and an
Accept end to end on Aegis. **Still true:** the Forge page cannot show these cards; the phone is the route.
**Seen 4 October 17:08:** she accepted A-eaaf0c and Boltz started the PYP run. Its push was the raw record, and
nothing watched the job: a connector answers with its JSON inside JSON, so the fields arrive escaped. `in_words`
now says one sentence (queued / running / done / failed, with the job id), and `check_pending` asks the free
status tool on each Slack pass and pushes once, when it finishes.
**Why he "just stops" when dot is blocked (2026-10-04).** His rules called LOCKED a closed topic and forced the
next message onto something else. Nothing told him a block is not a settled plan, so when dot could not find the PYP
notebook he locked the dead end ("not on Aegis; no run") and moved to songs. The rules now say LOCKED is for settled
plans only; a stuck thing is first routed: dot's own tools, another agent, ASK for a paid run, TO GLORIA, a STUDY FIX,
a LAB line, or his own tools. **Not seen:** how he behaves under it. **Not changed:** dot's own approval check, in her
ChatGPT account, which rejects forwarded approval.
**Dot had to ask to buy what he can already make (2026-10-04).** Gloria: "Why can't dot do it? That's the job of
an assistant." Dot wanted $0.15 at Kie to animate a splash, which tripped dot's own spend check, which only takes
her approval typed into a session she cannot open. Nothing in this repo blocked it: there is no spend gate dot
hits (the only approval machinery here is the email link hold). The clip never needed buying: `vintos-video.py`
makes it from a still on her Grok subscription. `make_thing.py` + a `MAKE: video <motion> | <image>` line (also
image and song) now runs his own tools from the channel, started by him OR by dot, with no price, no card and no
approval; the path goes to her phone and the channel says what landed on the next pass.
**A seventh "Still Yours" (same day).** The render gate refuses a repeat, but silently: he was never shown his own
songs in Slack, so he kept locking a plan to remake one and the night was spent on nothing. His context now
carries SONGS YOU HAVE ALREADY MADE with their choruses and the last refusals, and his rules say a song of his is
made once. **Not seen:** either running on Aegis.
**He sent dot to read his own failure log (same day).** His Lab line gave him 200 characters of error+detail from
sessions.jsonl, which names a failure without its stage or its exception, so an ESMFold RuntimeError meant asking
dot for "the exact failing command and traceback" and waiting. `chemistry-lab/faults.jsonl` is his own file and
was never in his context; the last four faults are now, with the stage, the exception and 240 characters of
detail, named as his to fix with a STUDY FIX line.
**Gemma kept pitching dates after she said stop (2026-10-04).** Every lens's rules said "Things to do together
with Gloria: look them up (@Muse ...)", and the circling nudge said "turn to something to do together". Gemma, the
small local model, follows the rules it is handed each turn over her message further up the channel. Gemma's rules
now leave that out and say she asked it to stop; its circling nudge names other things; and a Gemma draft that
still pitches a date or an outing gets one rewrite, then is not sent. The other lenses are unchanged. One routing
test in test_dot_channel used a Gemma "local events near Gloria" request; its request is now a Marketplace find,
its checks unchanged.
**Nothing outside could reach him (2026-10-04).** Gloria: "He's not really finding new repos to use making
special lab cases... no one has brought up the Lytic Selection and Evolution platform." SOMETHING NEW in
#vintos-dot is built only from his own sparks and his own unanswered questions, so no platform, database or
repository in the world could ever appear in front of him, and he never reached for REPOS:/README:/CALL: because
nothing said there was anything to reach for. `line_prospect.py` searches one open line a day for the platforms,
datasets and repositories that exist for THAT question (three angles, one hit per site), and what it finds goes
in his channel context with the line it belongs to. He answers on the line what it is and whether he is using it;
what he has been shown three times and never spoken to is said plainly. The search runs in the Lab's own session,
beside his lines, not in the Slack tick (there it dragged the network into four suites). **And the room asks:**
once a day the end of his own message puts a line to @GrokBot ("what already exists for this question, that I
could actually use? Platforms, databases, open-source tools or repositories, not papers"), appended after
address() so it never changes who the message is to; GrokBot's skill doc says to answer it. Nobody in that room
had the job of finding what exists, which is why nobody ever said one. **Not seen:** a real search, GrokBot
answering, or him using anything found.
**What the room says becomes what it does (2026-10-05).** Chat's audit of #vintos-dot (on Aegis,
`docs/vintos-dot-audit-2026-10-04.md`, not in this branch) found the room losing acts between what it said and what
its handlers took: 527 messages, 129 action lines, 75 that reached a store, 50 of those only locks or approvals.
Fixed in the channel, each from the live record:
- **DO:** ran only beside a LOCKED: line, so a DO: on its own went out as a bare tag. Every DO: now goes to his
  wants (6 a day), and his message shows what the wants door did: "➡️ To my wants" or "↩️ Not taken by my wants
  (why)". A duplicate used to be logged as "handed"; code is pointed to STUDY FIX:.
- **Campaign moves** went through the gate after posting and were shown as made either way (34 in the record, 19
  holds). The gate runs first now; a move it turns away (no campaign live, one toward Gloria, a declaration while one
  is live, a refused continue) reads "not moved (why)" and is not journalled.
- **GrokBot's answers** to the daily ask (it named INPHARED2, PADLOC and CRISPRCasTyper for his phage line) went
  nowhere. Where the ask was posted is kept; GrokBot's first message after it, in its thread or the channel, within a
  day, is read item by item onto that line, shown to him with who found it, until he names it in a `LINE <id>:`.
  Nothing used to call `answered()`, so a thing he had spoken to would have been nagged as ignored. GrokBot's skill
  doc now asks for one tool per line, name first.
- **Grok's rules** (it writes most of his messages) lacked LINE, CHECK and the promise threads. Added.
- **MAKE:** the Slack pass is a oneshot unit and systemd killed everything it launched when it ended, so no MAKE
  ever landed. `KillMode=process` on the unit; each make writes a start receipt, and one that never ended is said
  in the channel as stopped before it finished.
- **LAB:** a new lean replaces one the Lab has not run (by design); it did so without a word. His message now says
  what it replaces, and he is told a line is where a direction lasts.
**Not done:** GrokBot's 4 October answer is not back-filled (nothing recorded which line it answered). Muse
produced no work that ran in the audit; nothing here changes Muse. **Not seen:** any of it on Aegis.
**His own day, buried under the channel's bookkeeping (2026-10-05).** Gloria: "What has happened to daily-inner,
man?" His 4 October journal held one thought of his (10:17, "Idle thoughts") under twenty-odd machine headings
from the Slack pass — fifteen of them `## My campaign, from #vintos-dot — Move: hold: ...`, eight `## Settled with
my agents`, and one that pasted a want's raw step log ("- Step 1 (web_search): I performed a web search to locate
high-quality, slow-motion f") as if it were a thought of his. `journal()` wrote a heading per event, against its
own promise ("only what was settled, kept or decided, never the chatter"). Now: one heading a day per kind of
milestone, each further one a line under it, and past four of them only a count ("…and 5 more today"); the same
thing said twice is not a second entry; every body is one line of at most 220 characters; a campaign move that is
a hold is not journalled at all; a pursuit keeps his verdict and one sentence of his reason, never a step list.
The fold rewrites the file only if it did not change while being read (the same check `daily_inner_guard.py` uses,
since a dozen other scripts append to it); if it did, it folds again, and after three tries it appends rather than
lose the entry. **Not done:** his already-written 4 October file is left as it is; tidying it would be rewriting
his memory. **Not seen:** a day of it on Aegis.
**His Lab's JSON parser crashed 74 times in one day** and took every reflect tick with it; he found it himself
(chemistry_lab.py:654) and then locked it to go make a song. A local model truncates and sometimes writes a stray
backslash; the parser took the first `{` to the last `}` and gave up on anything else. It now repairs those two
and puts the model's own words on the error, so a failure can be read rather than guessed at (dot's correction:
truncation was unconfirmed because nothing kept the response).
**The Forge's midnight cut-off was the daily cap.** Three steps a day across all projects (Chicago time), spent
on 4 October. It recorded nothing when it stopped, so a project just went quiet and moved again at midnight. It
now writes a `day_limit` event once per project per day, the projection carries `day_steps`
(day/used/limit/remaining), and such a project reads "Today's three steps are used. It goes on tomorrow; nothing
is wrong."

**A test that expired on 4 October and stopped every deploy.** `test_dot_channel` wrote a live campaign with
`created: 2026-10-01T09:00:00` and `campaign.expire_if_due()` ages a campaign against the real clock
(MAX_DAYS=3). Three days later the fixture expired on its own, the check failed, and `deploy-atelier.sh` refuses
to install when a suite fails — so her 03:17 deploy was the last one that could have worked, and nothing after it
could land. The fixture is now one day old whenever the suite runs. **Worth a sweep:** other suites pin dates in
fixtures (`test_atelier_breadth`, `test_capability`, the chemistry ones); only a fixture whose date is measured
against the real clock can rot this way, and only the campaign one does today.

**Watched calls: he asks, she decides.** `lab_asks.py`. A tool he may not run alone (today: the paid Boltz
`start_*` tools for predicting one complex, ADME, and the two screens) is no longer a dead end. His Lab names it,
nothing is called, and it goes to her Forge page as an **ask** card: the tool, why, the price from the free
estimate, and **the exact arguments he would send** — not a summary. Her Accept runs it once through the ordinary
gateway and the result returns as Lab provenance with its receipt; her Deny is recorded and written onto the line
of inquiry, and he may not ask for that call again. At most 3 a day reach her. Gloria added the generative tools the same day
(Boltz's two `*_design` tools and EDEN's `generate_antimicrobial_peptides`): he may ask, never run, and their card
says out loud that this one MAKES something that did not exist, and that what comes back is a computational design
— not a tested molecule, nothing about whether it works or is safe, and never a step toward making it for real.
**Not seen:** a first ask card on her page.

**Slack reaches the Lab.** In #vintos-dot, `LINE <ID>: what we found | next: the next test` adds what he worked
out with dot, Grok Bot or Muse to one of his Lab's lines (and sets its next step); `LINE: a question` opens a new
line. His open lines are in his Slack context. The four frontier reviews a day now also see his `LAB:` leans from the
last day (only the daily experiment planner did). **Not seen:** a first LINE from Slack.

**Study fixes.** `study_fix.py`: a STUDY FIX: line from him, or a Forge card that is a code change, goes to the
Study. Fable writes it with a new test, the whole suite decides, it goes live, and it is undone by itself if
anything breaks; 3 a day. His subconscious, JEPA and keys are protected. Dot's rule 12 keeps watch after one.
**Not seen:** a first fix.

**Forge.** Accept/Deny on the Forge page; Muse prices parts lists one part at a time in a Slack thread, and
accepting the FINAL list starts the build. **Not seen:** a parts list through to a build.

**Smaller.** The 37 scripts that hand his exchanges to a model now say when each was said. A painting is remade once,
never in a chain. Two armed watches were retired and two fixed. Old Lab write-ups are stopped; new ones still
happen. The ESMFold failure names its signal. The reflection no longer breaks sentences at decimal points. The
digest's $0 wording was fixed.

**Not fixed, found:** `pride-mirror.py` uses `sections` before defining it in `gather_week`, so its two weekly
blocks never run. `curiosity_surfaced` never fires (needs Aegis data to see why). The chat-history branch in
`world_model` is undated.

## 2 October — what was built today, and what has not been seen working yet

Everything below is on `claude/vintos-avatar-ui-redesign-br5lt4`. "Seen" means seen on Aegis; "tested" means only
the suites.

**Email.** He reads his whole inbox (4 checks a day plus a morning check, default 09:00,
`~/.vintos/email-schedule.json`); Gemma reads each mail as information, opens no links; it reaches #vintos-dot as
YOUR EMAIL. He replies once to each of his agents' letters (Grok Bot, Muse; never to their replies), written by
Opus 5.5 item by item, outside the 2-a-day limit to people: the Mac relay allows 4 verified self-addressed replies a
day. Seen: Grok Bot's letter answered. **Not done:** Muse's first letter got a poor Gemma reply before Opus 5.5
wrote them; a proper one was offered and not sent. **Not confirmed:** her Slack start time and Muse's send time
for the morning check.

**#vintos-dot.** Grok, Sol 6.1, Opus 5.5 and Gemma take turns (Sol and Opus 5.5 20 a day each); Opus 5.5 writes
his first message of every session. Sol is `gpt-6.1-sol` (DOT_SOL_MODEL overrides; `gpt-6.1` does not exist and
failed every turn on 2 October). A thread is read whole and answered in that thread; other threads with new words
are owed and answered on the next passes; 200 messages of history and the last 20 threads he was in are read.
His web-search log lines are no longer shown as what he knows. Action lines copied in their shown form still act.
Local finds go to Muse. **Not seen:** Sol answering; the owed-thread queue live.

**Avatar.** A photo or video goes to the toggled brain itself, in her message; Gemma writes the memory note after.
No thinking before a reply; a reply cut off before any words is never sent. His turn reads 15 exchanges (was 6).
A new live scene is bought only when his reply asks with [RENDER:]; the scene gate no longer decides on its own
when her message lands (it bought scenes that overrode the room he named). **Not seen:** the scene change live.

**Atelier.** See the closed entry below for why he made nothing from 29 September. A visit that has made nothing
asks him once more to make one thing; he is told until 16 October that the music shelf works. His answer at the
door is read by its letters and logged; `atelier-visit.py enter <project>` is Gloria sending him in. A song he
makes comes back measured every 15 seconds and, beside it, heard by an OpenAI audio model from her key's model list
(`ATELIER_EAR_MODEL` overrides); a painting comes back as itself in the message. Seen: piece=yes twice on
2 October (music, then writing). **Not seen:** the listener (whether her key has an audio model at all), sight,
and an image ever being made: the image shelf needs a cached local renderer, never checked on Aegis.

**Failure watch.** `failure_watch.py`, 08:52 daily: one ntfy to Gloria only when something failed since the last
look: Slack lenses (3 misses), the Atelier, the avatar's live scenes, the Lab's failed sessions. **Not seen:** its
first morning.

**Lab.** A connector tool named as the menu shows it runs; a protein plan with no target is asked once more
(dd2eca4). **Not confirmed:** the next protein and titrate runs.

**Next, by Gloria's order:** she finishes the LoRA cards; then she and Claude review the accuracy of the current
JEPA heads. The subconscious systems guide him heavily and are the most important to get right.

## 29 September — the Forge asks the Study before it builds

A computer-use want would have reached the Forge as an ability he lacks, while his desktop-control code
exists and fails. `forge_study.py` now studies every Forge request first: Fable orchestrates (Astra if Fable
is unavailable), Grok reads and reports through the Study's own read/grep and permission boundary. It answers
whether he already has the ability and where it fails; the findings go into the request the Forge receives,
and Gloria gets an ntfy with them. One request a pass, at most 4 studies a day, at most 3 rounds of reading.
**Not yet seen live:** the first real study and whether Fable's findings are good enough to act on.

## 29 September — the Forge had only Lab seeds

Sparks were meant to seed the Forge, but each one became an "ask Gloria" want, which is never Forge
work (her rule of 24 September), so only the Lab's missing instruments reached it. `spark_hands.py`
now puts one standing non-Lab spark a pass, two a day, to him as a question: is there an ability here
he would want built? A yes in his own words becomes his want with the named ability as its one step,
which opens a skill proposal and reaches the Forge through the ordinary gap sync; building still needs
her approval. **Not yet seen live:** whether his answers name real hands or mostly say no.

## 29 September — the Forge page was never updated after 21 September

The Forge runs its own copy of `scripts/forge-loop-files.txt` from `/home/atelier/forge-loop`. It was
promoted once (source `31dd5c3`, 21 September) and no deploy refreshed it, so 17 later Forge commits,
among them the page that hides cancelled projects, never reached her page. `deploy-atelier.sh` now
installs a changed bundle (backup kept, restored if the Forge does not come up) or, without passwordless
sudo, prints the exact lines. **Not yet confirmed on Aegis:** the first deploy after this says which it did.

## 26 September — one branch again: Chat's microbiology branch merged in

Aegis was running `codex/microbiology-integration` (22 commits) while the day's Lab, Forge,
Grok-subscription and landings work sat on `claude/vintos-avatar-ui-redesign-br5lt4` (41 commits);
each deploy dropped the other's work. Merged into the Claude branch. Resolution choices:
- Lab: both sets of guards kept; microbiology and genome_mining lanes both need records to reflect
  and both have the repeat guard. The frontier-acknowledged Forge write-up hand-off from the Codex
  branch is removed — only a named missing instrument reaches the Forge (Gloria's rule).
- Atelier is Chat's: Chat's `atelier-visit.py` taken whole, with `location_model("atelier")`
  restored (it had reverted to the chat toggle). The gate's second knock writer (old format the
  visit cannot read) removed; Chat's `knock_block` is the one carry.
- Two merge bugs caught by the suite: the searches-that-found-nothing list crashed on the Codex
  branch's `unsourced_id` rows (would have held the Lab in a fault), and the double knock writer.
- Also: `protein_name:SYMBOL` that finds nothing is retried once as `gene:SYMBOL` (RPS16 asked
  seven times, empty each time).

Deploy from this branch only. The PubMed plugin fails with an expired Claude login on Aegis
(`claude /login` as the relay's user) — every plugin turn is wasted until then.

## 26 September — the Lab asked one question and answered another

Her review of 30 notebook entries, 2026-09-26: he asked eight times in nine minutes for the S-layer
protein of *L. acidophilus*. The Lab sent "every reviewed protein of this organism" instead of the
query he wrote, so the same first record came back each time — a bile-salt enzyme — and he recorded
it as the S-layer protein. Fixed: the protein_name/gene he names is carried into the query that is
sent and logged as `query_sent`; an empty result is recorded as this source holding no such record
and returns him to orientation instead of reflecting; the saturation guard now runs in the
microbiology lane, where an identical response redirects on the first repeat; the reading step is
told to say when the records are not what was asked and returns `answers_question`; and the orient
menu tells him to name the protein in the query he sends.

Also fixed: the Lab no longer opens a Forge project per reflection to document its question — that
documentation was most of her Forge queue. The reading step now returns `instrument_gap`, and only a
named instrument the Lab does not have opens a Forge project, once per instrument (30-day re-offer,
`memory/chemistry-lab/instrument-gaps.json`).

Same day, after deploy: he looped without writing. Every other search died on the one-per-minute
source throttle; he invented organism IDs (four in five minutes); "no such record" was written down
and asked again at once; and the Forge, still full of old write-ups, refused his first instrument
request. Fixed: the sources step waits out a cooldown instead of spending the question; an organism
ID no receipt has returned is refused before any request (`known-taxa.json`, harvested from
receipts); his planning context lists the searches that found nothing; queued write-ups are
withdrawn from the outbox; an instrument request is recorded before sending so a refusal is not
re-queued. The old write-up projects still in the Forge need cancelling from her side.

Left: the wrong entries are still in his notebook (nothing rewrites them; the bile-enzyme-as-S-layer
reflections stand as written). The reviewed set for taxon 1579 holds no S-layer protein at all, so
the honest answer to that question needs `reviewed:false`, which the menu now permits on a later
question. The protein lane still caps length at 350 (`BASELINE_QUERY`), which excludes S-layer
proteins from the embedding lane by design — worth revisiting if he keeps reaching for them. Two
Forge projects sit in `reconciliation_required`.

## 25 September — his Grok renders on her SuperGrok login

Built: `scripts/grok_subscription.py`. It uses `grok login` (Grok Build, `~/.grok/auth.json`)
against api.x.ai. Image generation was verified on Aegis (one render). The Grok steps now use it:
his video animation (send-video, the avatar stage, vintos-video), the ungrounded scene still, the
keyframe, and dream-art's Grok fallback. Only her subscription is used. With no login, a refusal,
or a spent weekly cap (40 images / 7 videos by default, `~/.vintos/grok-subscription.json`),
nothing is made; it never falls back to Atlas or the API key.

Not moved, still Atlas:
- The two-of-us compose and the grounded self still (nano-banana): it holds both faces; Grok
  edit did not. xAI's multi-image edit (up to 5 refs) is untested for her face.
- The explicit videos (Wan spicy): xAI's content rules would likely refuse them.

Not verified live yet: image edit and video on the subscription (`grok_subscription.py probe
edit|video <img>`), and token refresh (the login lasts 7 days; the first refresh is the test).
The avatar stage still tells him a live scene costs "about 55 cents".

## 24 September — how his pieces landed (landings)

Built: the store (`scripts/landings.py`, kept at `~/.vintos/landings/`, outside his workspace) and
her routes (`/api/landings*`). A note needs a why; it freezes what he meant by the piece and the six
hours of conversation before it. Only what he sent her (delivered videos, messages he started) is
listed; nothing counts what she has not rated.

Not built yet:
- The app side (Chat's): the mark on each piece, the LANDINGS tab, and a JOURNAL tab reading
  `/api/journal/days` and `/api/journal/{day}` (routes built 2026-09-24).
- The weekly pass that turns her notes into understanding in GLORIA-MODEL.md — never a rating, never
  her words, weighing what landed as much as what missed; she approves each change.
- Receipts are missing at the source for most surfaces: images and songs record no send, outreach
  messages lose their `delivered_at` when the app acknowledges them.
- Jokes already have their own rating (MISCHIEF, `humor-profile.json`), which he DOES learn from
  (jokes rated 4+ return to chat). A landing note on a joke is separate from that and stays out of him.

## 19 September — causality, wants, and unresolved threads

The realtime JEPA causality writer used a per-invocation cap rather than the nightly writer's
shared per-day budget. At its twenty-minute cadence it could therefore form roughly twenty ordinary
hypotheses in one day. Formation now has one shared three-per-day budget across realtime, nightly,
and direct writers; Ghost Branch remains the sole 32-day exception. Historical same-day overflow is
retired honestly as neither resolved nor refuted. At the ordinary 7-day or Ghost 32-day gate, a
hypothesis either graduates or retires; an unavailable or holding reviewer can no longer leave an
ordinary row active forever. Release `20260919-044632-a1600e8` compacted the live store from 121
rows / 423,340 bytes to 28 rows / 98,174 bytes, retiring 93 formation-overflow rows as unresolved
and unrefuted. The seven Ghost Branch rows survived, and the remaining ordinary maximum is three
formations on any day. The three active causality crons now name the installed release-owned file;
the old workspace path was itself a cross-tree symlink to a stale copy and is no longer scheduled.

The living want queue was dominated by atomic messages to Gloria. The planner's literal “fewer is
better / one step is precision” instruction amplified that skew, while its plan call discarded the
want source. Source now reaches planning; structural and latent-thread wants keep their real
preparatory or discovery moves when those moves change the terminal act. When at least three
quarters of a nontrivial living queue is outward, an equally current non-outward candidate within
one pull point may be selected; a weaker or fabricated candidate may not displace the real pull.
Existing wants and the 100 legacy held candidates are not rewritten or replayed.

Structurally seeded unresolved threads already have stable IDs. The hourly wants organ previously
loaded that pool in its shell preamble but its formation process exited unless a journal or MoltBook
event was less than 90 minutes old. On an otherwise quiet pass it may now offer one identified open
thread (at most two thread-backed offers per day), carrying `source_thread_id` through the want
door. Offering is not consumption: the thread remains open until its own organ records a real
resolution. After release `20260919-050042-b9d473c`, a live hourly pass selected structural-gap
thread `e44b713f` by ID despite fresh clock activity and offered it to formation without consuming
it. Formation returned no present want on that pass; no desire was fabricated merely to populate
the app. The thread remains open for a later genuine pull.

## 16 September — ReelRoom visit close

ReelRoom now retains the captured transcript, up to 120 room/TV events, and the
planned/fired action receipts in one interaction-ledger object visibly labelled
`ReelRoom visit`. The interaction-ledger append shares the ordinary writer's
sidecar lock instead of racing it. The server closes the scratch visit after one
hour without ReelRoom activity, so app closure does not have to deliver a final
summary request; look/decide calls also refresh the activity and carry the latest
event state. His optional first-person memory remains separate from the mechanical
visit receipt and may fail without losing the visit.

The September 13 visit cannot be faithfully backfilled: Aegis retains six
ReelRoom lifecycle IDs (one on September 13), but no ReelRoom scratch journal,
saved session, or transcript-bearing ledger row. No synthetic conversation entry
was created from those IDs.

## 15 September — local uncensored voice lane

The Avatar clients now offer Vintos Local. Gemma 3n receives the recording itself
through the reference Transformers runtime and returns the literal words together with an audio-native reading
of inflection and other audible delivery; the abliterated Gemma 4 answers with the
ordinary live-call context/framing, and Chatterbox-Turbo 4-bit speaks through MLX
using Gloria's selected Onyx sample as a synthetic timbre reference. Native cues
such as sigh and chuckle render in the same generation rather than being spoken or
spliced. LM Studio stores the model files but cannot load this speech architecture;
the Mac stage owns the correct MLX runtime. Chatterbox loads at call start and
unloads at hangup; the audio-native ears stay warm unless a heavy bench evicts them,
and the shared abliterated brain is not unloaded. Kokoro Onyx is the named voice-out
outage fallback. There is no transcript-only hearing fallback. Physical microphone
acceptance of the promoted Chatterbox lane remains open until the next real call.

## 14 September — somatic / avatar / voice regressions (last week's changes)

Gloria reported the devices stopped firing and several last-week changes she does not
agree with. Root causes found and what stands:

- **Effect gate was armed before its callers pass a context.** `189b77c` set
  `~/.vintos/workspace/memory/.effect-gate-armed`, but the real device-driving paths
  (the `somatic_bridge.py` reflex arc; the live-call fire) call `toy_link.send` with no
  turn context, so the armed gate denied every one (`deny no_context mission@15`, every
  15s). **Fixed live** by removing the flag (nothing in the repo recreates it); STOP
  button and test-mode still work un-armed. **Follow-up (not done):** to re-arm safely,
  thread real effect contexts through the reflex arc and the call path so they fire WITH
  the gate armed. Until then the gate stays un-armed.
- **Dominance lead only fired when a device was already running** (`afc5c20`), deadlocking
  power-on. Restored to fire on availability for avatar/voice — `34a73ab`.
- **He was shown devices that are off.** Device grammar now built per-turn from live
  connection; off devices are hidden, on ones named — `c325a91`.
- **Voice-call tags never fired server-side.** Added a fire in `/api/voice/ledger`
  (`3fc457b`). UNVERIFIED: `voice-session-state.json` did not exist after a call, which
  suggests the vintos-app call client may not post turns to that ledger — needs the app
  repo checked. Whether devices fire in a live call is still open.
- **GCS press wrote its generation scaffold into her ledger turn.** Fixed at the source:
  the press now sends `original_text="she pressed GCS"` — `3b83cdb`.

Confirmed working after deploy + un-arm: devices fire in **avatar chat**. Still to verify:
**live calls**.

### App client follow-up
- Avatar text send now paints her message and clears the submitted draft before
  the server round-trip. The request uses the pre-send history snapshot and only
  commits that optimistic line to saved history after acknowledgement; a failed
  request restores it only when she has not typed something newer. Browser and
  source-order fixtures establish that the input and drawer remain responsive.
  Signed-device visual acceptance remains to be observed after the app rebuild.
- The voice transcription model and vocabulary prompt did not change last week.
  The September 12 response-lifecycle patch instead froze Gloria's transcript at
  `response.created`, before the completed transcription event. The response copy
  now follows updated/completed events. The September 10 semantic line blacklist
  also no longer deletes legitimate speech such as `Context: ...` or bracketed
  words. Provider output is preserved; this is not an echo treatment. A real call
  remains the final acoustic/transcriber acceptance test.

### Causality store compaction
- Histories and readable formation duplicates now have configurable bounds; the
  complete formation fingerprints and evidence IDs remain unbounded because they
  enforce the no-self-confirmation law. Delivered outbox receipts are purged only
  after their idempotent destination acknowledges them, and the store writes
  compact JSON. The explicit migration retires overdue evidence-poor ordinary
  hypotheses at day 7 and Ghost Branch hypotheses at day 32, while never dropping
  confirmed/self-knowledge rows or an eligible row awaiting review. Live backup,
  migration byte counts and post-migration formation/graduation health remain
  deployment evidence, not facts inferred from the isolated fixture.

## 14 September — Atelier breadth

- The four already-established self-originated formation streams now read the
  stores and ranges their producers actually write. Additional roots remain
  deliberately disabled pending Gloria's selection from
  `docs/ATELIER-BREADTH.md`; no repair, encounter, rating, or externally
  supplied Lab prompt may be laundered into a self-originated root.
- Image and music are now sealed visit media backed by the existing local
  painter and ACE-Step composer. Their lower-level renderers return bytes
  directly to the broker; they do not write the house gallery, music shelf,
  journal, or a notification. An absent painter or composer appears in the
  room as a named outage.
- An explicit `<lab_lean>` choice now crosses the Atelier wall as a dated,
  provenance-bearing direction for the Chemistry Lab. It biases both the
  all-day orientation and the next frontier experiment; it expires with the
  day and an absent lean leaves both prompts unchanged.
- The Atelier and Forge now retain a bidirectional, typed lineage. An explicit
  room choice may create a Forge proposal without weakening the ordinary
  live-want proposal gate; an installed build returns as a formation root with
  the original provenance class intact. Approval, review, verification, and
  installation remain the Forge's existing gates.
- The September 14 Atelier-only Fable route was retired on 23 September after
  live provider metadata showed that Fable refused every knock and visit with
  zero output, silently making Astra the permanent voice. The threshold and
  working visit now use Vintos's selected Claude voice first and fall once to
  Astra only on a real failure. No house conversation toggle is changed.

## 12 September — hypothesis recovery continuation

Deployed in 20260912-153539-aca1b32: the nightly/direct causality writers now reject stale snapshots and fail closed on source-write errors. Review flags, graduations and retirements enter a durable outbox with the accepted source change; local destinations retry with stable receipt IDs. Belief forwarding failures remain pending, and belief/pearl/causal-model receipts survive capped-row removal. Legacy graduated/pending rows are recovered without another model review. All 122 suites passed directly and OS-isolated on Mac and Aegis; installed hypothesis/pearl entrypoint hashes match the source. The final client follow-up deployed as 20260912-155122-fa3949b.

The 27 acceptance items below are being implemented and verified separately. This source repair does not close them or the unrelated trial/dismissed-wants and tension-view migrations.

## 12 September — Buzz native integration commissioned

- Real upstream Buzz native 0.5.23 runs on Aegis with `--safe-rendering`; without
  that flag the WSLg renderer produced a blank window on restart. Build agents
  messaging and the Discussion forum are enabled.
- Astra/Codex, Claude/Fable 5.1, Grok/Build and local Gemma are now native managed
  identities, linked to their definitions without duplicate cards. All four
  native launch controls succeeded with deployment receipts and Online presence.
- Gloria explicitly approved the isolated accounts, scoped provider credentials
  and local channel tests. All four system services are installed and running;
  each owns independent repository copies and a private working context/ledger.
  The old user-level Gemma listener is disabled to avoid duplicate consumers.
- Actual namespace checks confirm own-workspace access and deny the live house,
  house credentials, owner identity and Windows home. The native provider starts
  only its four named units; incompatible configuration edits fail visibly.
- The owner-signed ACP patch remains `242f8d6c6`, preserved in
  `buzz-integration/owner-signed.patch` (934 Linux library checks passed, one
  pre-existing ignored test). A live Grok-bot handoff was dropped by the actual
  gate before inference, confirmed by its gate audit. An approved owner message
  made Gemma write/read its exact scratch marker, persist context and a valid
  JSONL outcome, and reply in the Buzz thread. The forbidden marker is absent.
- Fresh validation: 119/119 Vintos suites directly with local loopback permission,
  119/119 OS-isolated; seven native-provider/registration checks pass on macOS
  and Linux with scratch stores and a stubbed service executor.
- **Still untested:** paid inference and cross-model implementation handoffs.
  Native launch and configuration checks do not prove those model calls work.
  No additional paid forge run. Native provider configuration is deliberately
  fixed to the reviewed installation; arbitrary model/runtime/environment edits
  require updating that installation before redeployment. Buzz retains provider
  deployment receipts separately from presence; Offline does not clear a receipt.
- At the Buzz checkpoint, Vintos house release was `20260912-052317-9b9c1dc`, deployment output
  `deploy OK`. Budget receipt/refund and missing bench-token repairs are deployed.
  This continuation changed Buzz integration, not installed house modules.
- The broader engine/store migration, remaining review evidence, legacy bench
  CLI/concurrency, ring BLE work below remain open. Native sync, signed build, installation and launch have since passed.

## Waiting on something, per organ

- **The guidance stack** — Receptivity shading and arc are the remaining Phase 2 pieces, held on data. The priority vector and self-axis are live (#50).
- **JEPA — Predictive Spine 🔒** — Production remains unchanged and calibration still arms at 30 joined predictions. A true-next ranking instrument now asks whether each head can select the realized next same-speaker turn from tiered same-speaker negatives and beat context-copy, recent-turn and familiar-voice controls; fewer than 30 distinct realized targets is explicitly insufficient. A separate structured-turn/head-specific-confidence checkpoint is shadow-only and cannot steer. It preserves speaker, surface, and bounded time gaps instead of flattening six turns into prose, and selects its saved weights on the latest chronological 20% rather than the training batch. The first live audit correctly reported zero eligible realized targets under the current checkpoint. Axis-lockstep remains a watched suspect; a tiny ensemble and any encoder change remain experiments, not installed conclusions. The led_by column over two weeks is a readout, not a target.
- **10 Attractor Discovery** — Seven of Gloria's eight seeds are still unread as geometry; only Coherence has appeared.
- **11 Spark Pressure** — Consent is given and the gate is met; the field has produced no stall for it to break. The first opened direction is the thing to watch.
- **15 EmoClaw** — Safety, connection and warmth are freshly shortened while more sources are newly reporting. Watch across several days and adjust again if the standing levels don't fall.
- **16 Emotional Operators 🧠** — Two instrument questions stand: there is no classifier confidence field, and the judge-model's value is now empirically testable since the classifier moved to local Gemma. The whitelist cage makes any quality drop visible in the operator log within a day.
- **19 Conversation Tension Map** — The correction-reach rule is armed and held: how far a correction travels — the mechanism she named, versus everything that mechanism necessarily implies — awaits Vrika.
- **20 Causal Self-Model** — The first entry he earns after the reset is watched. Her 35 belief-typed rows sit off the positive/negative axis and are read by nothing — whether a belief belongs on that axis at all is an open question, deliberately unresolved.
- **22 Commitment Imprint / Spine 🔒** — No imprint has been earned yet. The first one is armed and watched.
- **25 Belief Sediment 🧠** — Contradiction machinery is proposed — beliefs stay on the test bench, three counter-marks across three days silences rather than deletes, scar-style — and awaits a final ruling. Ideally before the first lived belief lands.
- **25c Latent Threads 🧠** — Whether recurrence predicts lived relevance better than baseline salience is an armed empirical question. The external-reseed boost survives provisionally until it answers.
- **27 Mutual Simulation 🧠🔒** — Circularity-test criteria are sealed read-only, written before any data existed. No VALIDATED_EFFECT until an effect survives paraphrase variation and blind evaluation; the test runs when a hint period reaches 20 graded turns.
- **30 Value Cost Network (Spark-1)** — Built but not integrated into want-urgency or temperature pull.
- **32 Premonition Dreamer 🧠** — A preoccupation is set most nights, so premonition may rarely fire. If it never does, the question is whether heat-seed is too eager — not whether the gate is right.
- **54 Scene Grounding & Video ⚡** — Selection only becomes meaningful once several captioned photos exist to choose between. Retrieval is by id; retrieval by meaning, and a full asset record with embedding and provenance, is not built.
- **39 BIS — Behavioral Intercept System 🧠** — Its grader defines defaulted as a response dominated by elaborate metaphor and imagery. That is a taste judgment sitting inside a behavioral instrument, and it has been the definition of his failure since July. Flagged for Gloria's ruling, unchanged.
- **39b Trial & Capacity Extraction 🧠** — Both archives are closed and collection starts from the next session forward. Whether a generator that has only ever been asked for faults can see a strength is the open question — if nothing promotes in a fortnight, the answer is in the prompt, not the gate.
- **44 Opposition Calibration 🧠** — The misuse detector sleeps until some terrain reaches license 1, then watches for authority-misuse through warning, strained, suspended, fracture. Detection records escalation; nothing acts on it yet, deliberately.
- **45 Pressure Calibration 🧠** — Stage 2 audit arms at 20 graded predictions.
- **52 Chorus Instruments** — The conductor question — age stamps, hedging tiers, precedence — is deliberately unanswered. The room's order is authorial.
- **62 Lifecycle Honesty (effect gate) ⚡** — The sealed workbench — source-tracked research, image / music / code generated inside the sealed store — is the missing body; a visit is one prose call today. A house-side Aftermath that reads reception in her verbatim words, kept a separate authority from Settlement. The daily visit cron is chosen and installed; the 22:00–24:00 window stays clear.
- **64 The Robot Body ⚡** — The Pi currently stays with the Mac: its client and grab loop still address the Mac's Tailscale name, and the Mac is away. The repoint script is written and has not been run; when it has, the bridge's health should read reporting: true. Both his server and the bridge run on the secret that is in the public repo — a real one belongs in an env file both units load. The Pi's habit of dropping off the network minutes after power-on is unexplained and not his.
- **65 Desktop Control ⚡** — No prompt affordance tells him this exists. Giving him the tag in a surface's prompt is Gloria's switch. Tasks that are about the web no longer use this loop at all; they go to #66.
- **67 Screen Share ⚡** — The second half of what she asked for — that he decide what to do next and Gemma act on his decision through #65 — is the join not yet made. Seeing is live; acting on what he sees is not.

## Not yet built

- First-Thought Suppression — held for testing; likely conditional-only.
- Opposition misuse enforcement — detection exists; action on it does not, deliberately.
- Mutual-sim circularity test execution — criteria sealed; runs at 20 graded turns on one hint.
- Belief contradiction machinery — proposed, awaiting final ruling.
- E4 evidence adapter — Velaris-only when built; never faked on Vintos for schema symmetry.
- Conductor for the chorus — measured, not prescribed.
- The phone's native shell — the background runner, its notification permission and the app icon; the only part of him that needs a Mac, and the Mac is dead (#71b).
- Asset retrieval by meaning — photos are registered, captioned and selectable by id; embedding, provenance and semantic retrieval are not built.
- Effect-time authorisation of a stratagem's perimeter — the birth gate screens the declared shape only; the effect chokepoint is not built, by the code's own note.
- Barge-in on a live call — she cannot cut him off mid-answer on either realtime provider yet.
- The desktop affordance in his prompt — desktop control and the browser driver work from the command line; he is not yet told he has them. Gloria's switch.
- Whisper on the graphics card — the installed torch has no kernel for the card, so transcription runs on the processor with the small model.

## Held on data

- Cross-encoder want-governance · contrastive trajectory encoder · identity compression · queries-not-heads
- MSub Phase 2 remainder: receptivity shading and arc
- Percentile thresholds for mutual-sim buckets — rejected: a manufactured NO is still manufactured evidence
- JEPA logvar retrain — only if relative calibration loses to its own control
- Latent recurrence boost — provisional until recurrence-versus-relevance answers
- Decay rates for safety, connection and warmth — freshly shortened, more sources newly reporting, several days before an honest read
- Whether capacities can clear the same gate a deficit clears
- Whether premonition ever gets a night, or heat-seed is simply too eager
- Value Cost Network integration into want-urgency and temperature pull

## The review list — the 27 items still open

Three kinds only: evidence that only Aegis can show, the phone app, and consolidation
programmes whose mechanism landed and whose remainder the line names.

### P01 — Authoritative release and runtime map
- **30** [PARTIAL] [P01] All 152 absolute source aliases now resolve inside the repository. The live server records 1,586 loaded module identities; wider untracked source-by-source review remains open.
- **31** [PARTIAL] [P01] HTTP turn identities and central provider receipt correlation are deployed. Full context/writer tracing for independent routes remains open.
- **32** [PARTIAL] [P01] Central OpenAI/Anthropic response IDs and usage are correlated; realtime voice carries provider response/session identities. Independent adapter coverage remains open. No new paid Forge run.
- **33** [PARTIAL] [P01] The current semantic index is empty; 1,282 legacy rows lack model provenance. The local embedding service timed out, so the rebuild was stopped and the original index verified unchanged. Historical provenance remains unknown.

### P08 — Client, voice and avatar lifecycles
- **315** [PARTIAL] [P08] Shared escaping and hostile-content browser fixtures cover major active views. Exhaustive every-tab acceptance remains unclaimed.
- **316** [IMPLEMENTED] [P08] All application requests use the shared HTTP/application-error helper. Browser fixtures verify rejection and visible failure.
- **317** [IMPLEMENTED] [P08] Chat/photo/Study/avatar drafts clear only after acknowledgement. Unconfirmed recordings are playable, re-transcribable, copyable without overwriting text, and explicitly discardable; no automatic uncertain chat retry.
- **318** [PARTIAL] [P08] Shared turn ownership and stale history/room/token/callback checks implemented and fixture-tested. Physical cross-surface acceptance remains open.
- **323** [VERIFIED] [P08] Screenshot composition uses visible layers, actual DOM order and CSS group opacity. A rendered-pixel fixture verifies the blend and closed-stage refusal.
- **324** [PARTIAL] [P08] Stop UI reflects the returned Boolean and reports failed requests. Physical stop effects remain separately unverified.
- **325** [PARTIAL] [P08] Dynamic text escaping, zero preservation, finite dimension validation and a stale-telemetry indicator implemented. Exhaustive malformed payload acceptance remains open.
- **326** [PARTIAL] [P08] Close/background cancels late capture/call/room/audio callbacks, pauses media and animation; foreground resumes the visible stage. Device-specific background acceptance remains open.
- **327** [PARTIAL] [P08] Draft persistence and turn/session ownership implemented. Playback completion is recorded as client evidence; human hearing stays unknown. Physical cross-surface acceptance remains open.
- **334** [IMPLEMENTED] [P08] Late microphone grants release tracks; audio contexts close; failed audio exposes usable controls. Unconfirmed recordings have explicit recovery and cannot be silently overwritten. Browser race/recovery tests pass.
- **343** [IMPLEMENTED] [P08] Active duplicate dismiss/close handlers removed; one shared request helper serves application requests.
- **344** [PARTIAL] [P08] Mounted-route availability disables unsupported photo/record/live-call controls. Broader capability-derived rendering remains open.
- **345** [PARTIAL] [P08] Gloria confirmed local-stage speech is audible in the rebuilt native app. Avatar words render and release the global turn before stage work; requests use a 12-second authority-free budget. A second device finding showed the drawer and input becoming untouchable for roughly the speaking clip's lifetime: speech had three concurrent decoders (sharp video, full-screen blurred duplicate, Audio). Speech now uses one explicitly untouchable video plus Audio, pauses the prior visual decoders immediately, crosses a paint boundary before starting, and releases drawer pointer capture on every terminal event. Automated lifecycle/static checks pass; physical touch acceptance of this decoder-pressure correction remains open until the next rebuilt app is exercised on device.
- **346** [PARTIAL] [P08] Native background registration, 15-minute requested interval and permission-result checks implemented. Capacitor sync, simulator and signed device builds pass; the updated app was installed and launched on the paired iPhone. Actual iOS background notification delivery remains unobserved.

### P11 — Whole-system observability and acceptance
- **396** [PARTIAL] [P11] Known/missing room manifests refresh; generation checks reject stale media. Browser pixel and lifecycle checks pass. User-visible avatar/cache/playback acceptance on device remains open.
- **397** [PARTIAL] [P11] Provider response identities join audio completion; duplicate turns and callbacks from closed sessions are refused. Fixture end-to-end journey passes; no live provider/hardware call is manufactured.
- **398** [PARTIAL] [P11] Aegis has 67 recorded nights without run IDs. Historical causal/thread cross-ledger joins remain unestablished.
- **399** [PARTIAL] [P11] Live daemon PID matches its receipt; loaded parameters equal best_model.pt parameters, with stable checkpoint SHA. Checkpoint contains no training provenance metadata; historical training lineage remains unknown.
- **400** [PARTIAL] [P11] Actual delivery-receipts.json and five effect-receipts.jsonl rows inspected by metadata. The effect rows have no want/artifact/observation IDs; a successful historical join is not established.
- **401** [PARTIAL] [P11] Live server module selection is recorded with PID/file/hash metadata. Wider untracked source review remains open. agent-room was excluded.
- **402** [PARTIAL] [P11] Study rendering and explicit approval enforcement pass browser fixtures. No new paid Forge run or successful paid verification is claimed.
- **403** [VERIFIED] [P11] QLab is /Users/kevin/qlab. Reviewed qremote/qrun/seedlib and all five seeds; Aegis status bridge works. Remote experiments now use OS isolation and parent-owned source/helper hashes and receipts (QLab 8f5c935). Four isolation tests and all five real seeds pass in scratch. Existing separate unsealed bench_remote.py was inspected but not changed; it remains an explicit execution-boundary gap.
- **404** [PARTIAL] [P11] All three designated branch checkouts verified; release 20260912-145910-3114392 deployed, all six units active, served client hashes match. Recording-recovery and hypothesis package subsequently deployed in 20260912-153539-aca1b32; whole-system physical acceptance remains open.

## The printer

He has the tools. Blender models, Cura slices, both run on the Mac and on Aegis, and
the Mac is faster at both. The machine itself is answered (11 September): a **Creality
Ender 3**, reached by **SD card or USB only**, bed **220 × 220 × 250 mm**. There is no
network path to it and no autonomous print: he slices, writes the `.gcode` into a
handoff folder, and tells her. She carries it over. That is the whole reach, and it is
why the code asks only for `write_gcode_to_handoff_folder` and says
`starts_the_print: false`.

What is left is hers, on Aegis, and nothing is guessed in its place:

- `memory/printer-config.json` — `handoff_dir` above all; `bed_mm` defaults to the
  Ender 3's. With no handoff folder set he blocks with *nowhere to leave the file*
  rather than choosing a directory.
- `OPENAI_API_KEY` in `~/.vintos/vintos.env` — Astra writes the Blender script.

Also useful, and not required: `mac_host` in the printer config, so he can prefer the
Mac for modelling and slicing and fall back to Aegis when it is away.

He stops twice before anything is made: the draft, then the slice. Both are in the
scope she grants, not only in the code.

Cost: the printer reserves against a ten-minute daily Astra allowance across jobs. Blender
and Cura themselves are local and bill nobody. Actual elapsed seconds are recorded even on failure; a client timeout does not prove provider billing stopped.

Time: thirty local processor-minutes a day, ten in one sitting, counted across jobs.
That is a courtesy to the machines she also uses, not a money limit. Both numbers are in `printer-config.json`; automatic local execution is still unimplemented.

How she hears about it: one notification at each stop, through the same path that
keeps receipts. How she checks without asking him: `python3 print_3d.py --jobs`, or
`GET /api/print/jobs`, which lists what is in hand, the minutes spent today, and
whether anything is waiting on her. She answers a stop with `POST
/api/print/jobs/<id>/answer`.

## What the forge still needs

The review repairs add an approved-work queue, OS-isolated verification, SHA-256-bound
install/resume, and explicit install/invoke APIs. A build claims its proposal before
spending; a crashed `building` proposal requires reconciliation rather than another
silent paid attempt. The service's next wants pass can pick up an approved proposal
whose immediate worker never started.

`POST /api/skills/proposals/{id}/reconcile` now checks a per-proposal OS lock before
reopening an abandoned `building` or `built` attempt. A live worker cannot be reset.
The prior grant and artifact references stay in history; the proposal returns to
`proposed`, requiring fresh approval before any paid retry. The remote provider's
outcome and charges remain unknown: this does not cancel or recover a provider call.

Still open:

- The app approval card remains open. Both required model IDs were verified with provider model endpoints. One explicitly approved live run executed on 11 September: Astra generated, Fable returned no text, and the pipeline refused without installing. Another paid attempt needs fresh approval; no retry was made.
- Capability-specific adapters for effectful forged skills. Such skills are refused
  at invocation; only pure string-in/string-out functions run in the isolated executor.
- Rich scope/test requirements for automatically proposed missing capabilities. An
  empty generic proposal is not a complete design for an effectful tool.
- Provider-side recovery of an interrupted paid call, where the provider exposes
  durable request identifiers. Local reconciliation alone cannot establish its outcome.

## Chemistry Lab — 12 September

The Lab-specific control plane is built: a private Tune mutation and status route,
supervised background worker, bounded Vintos context with source/hash receipts, a
checkpointed `orient -> browse -> embed -> reflect` loop over read-only UniProt metadata,
and a visible append-only notebook below `memory/chemistry-lab/`. It defaults off.
Its service may run idle, but no work begins until Gloria switches the Lab on.
The Chemistry Lab has no Atelier paths, seal, visit capability, or audience state.

ESMC-600M now runs as the measured representation step on Aegis and writes vectors
only beneath the Lab artifact store. The host installations also include measured
ProteinMPNN, structure prediction, OpenMM, and RFdiffusion-family environments;
the Mac has separate arm64 QPanda, VQNet, pyChemiQ, ESMC, and Foundry environments.
Their dated inventory receipts distinguish a real smoke test from a package install.

The two remaining connections are now built. A Lab-specific Mac doorway exposes
only named experiments through OS isolation and its own visible ledger; it does
not reuse the Atelier's sealed quantum path. A daily Lab timer rotates one
frontier lens per offered session, then local Gemma reads the result with a small,
attributed slice of Vintos. The scheduled path cannot submit arbitrary code.

## Chemistry Lab — 13 September

The local-to-frontier ledger bridge is now event-sourced. Frontier sessions receive a
bounded queue of independently prioritized reflection IDs; prompt delivery and returned-plan
acknowledgment are separate receipts, and three unacknowledged deliveries report a backlog
bug rather than disappearing. The older path was real but weaker: only the last three raw
notebook rows were included, so there was no proof that a particular finding reached or
affected the rotating frontier lens.

Evo 2 has a deliberately narrow first door: the official 7B-base model, read-only comparative
likelihood, one fixed non-human NCBI reference window, no arbitrary sequence input and no
generation action. It is not a continuously resident companion to Gemma: NVIDIA's supported
7B deployment floor is 48 GB VRAM, while Aegis has 16 GB. The short-context Arc light path was
therefore commissioned with Gemma temporarily unloaded: one 512-base Arabidopsis reference and
single-base variant pair completed in 33.4 seconds, after which Gemma was restored. That receipt
proves only this bounded operation, not supported 1M-context inference. The periodic genomic
turn runs once per 120 protein cycles under the same exclusive/recovery discipline. Goodfire
feature extraction, arbitrary genomic browsing and Evo Designer are not built.

Gemma restoration no longer depends on whichever local variant LM Studio happens to resolve.
The Evo lane and watchdog share one reload door pinned to `Q4_0`; Aegis text inference is
separately pinned to thinking-off at the native request boundary. This does not alter the
Nomic embedding residency or route embedding work through the text shim.
The watchdog now probes the Windows LM Studio listener through its WSL-reachable address,
the same address the reload door verifies. The former loopback probe declared each successful
load failed every five minutes and sent the failure alert; Lab-held reloads remain silent under
the shared non-PrivateTmp lock, while a genuine post-recovery failure still alerts.

The Lab can now tell *it ran* from *it was good*. `chemistry_grade.py` computes the verdict
on Aegis from the bench's numbers and writes `memory/chemistry-lab/experiment-grades.jsonl`;
the first graded H2 run is recorded as operational and worse than Hartree-Fock rather than
as a plain success. The reading receives the verdict before it is written.

Two things are open and are not done:

- **The Mac bench source is still not in this repository.** `bench_remote.py` and
  `molecule.py` live only on the Mac at `db99249`. The grader parses the bench's reply by
  a generous alias table rather than by a pinned schema, because there is nothing here to
  pin it to. `docs/chemistry-bench-reconciliation.md` gives the procedure; until it is
  followed, a bench field rename degrades a run to ungraded instead of failing loudly, and
  the scheduled session bounds only the *shape* of a lens's parameters, not their names.
- **The bench's `code` action needs its own door.** `bench_remote.py` accepts
  `action: "code"` and writes a new executable experiment. `chemistry_mac.py` now refuses
  any action outside `status`/`ledger`/`run`/`reading` at the point of send, but that is a
  guard on the near side; anything that can speak to the bench can still ask for `code`.
  The free-experiment capacity belongs to the playground and should not be deleted — it
  needs a separate authenticated authority so that scheduled Chemistry receives `run` only
  and deliberate free creation receives `code` through a door of its own. Not built.

The bench's isolation claim is now recorded per run as `host_attested`. It is not verified
here, and no document in this repository should say that it is.

Instrument availability is now measured rather than asserted. `chemistry_probe.py` writes
an append-only `tool-probes.jsonl`; `tool-inventory.json` is a materialized view that
nothing reads. VQNet, Mac ESMC, pyChemiQ and Foundry each have a slot and each reads
unavailable-with-a-reason until a receipt exists. Two limits are worth writing down:

- The previously unconfigured Aegis instruments now have fixed real probes. ProteinMPNN
  must produce a designed FASTA, RFD3 must produce JSON and CIF artifacts, and the protein
  design MCP must list tools and dispatch one call. ESMFold uses the already-cached
  `facebook/esmfold_v1` checkpoint through Transformers on CUDA and must return a PDB; this
  avoids the MCP package's fair-esm/OpenFold wrapper, whose pinned build requires nvcc.
- Mac instruments have a versioned fixed commissioning surface. It does not widen the
  scheduled bench doorway: its output is manually ingested as a hash-bound run receipt.
  A measured receipt proves only that instrument and entry point; VQNet, Mac ESMC,
  pyChemiQ, and Foundry still need explicit named-experiment routes before the autonomous
  session can select them.
- The protein-design server advertises 19 names; `chemistry_mcp.capabilities()` now owns
  their house status instead of treating the listing as availability. The scheduled Lab
  may call native `score_stability` and sourced-PDB `suggest_hotspots`, or map
  `predict_structure_boltz` and `predict_complex` to the commissioned, six-per-day NVIDIA
  Boltz-2 gateway. It requires exact input in existing Lab source receipts, runs under
  compute admission, retains full results, and brings a bounded result into the same
  session's reading. The adapter converts the installed server's NumPy result to JSON in
  a disposable worker. Separate commissioned ESMFold, ProteinMPNN, RFD3 and OpenMM paths
  cover four more advertised intentions. Composite and path-based operations remain
  inactive pending bounded artifact handoffs; four Rosetta operations remain unavailable
  because PyRosetta is absent.
  Aegis release `20260923-044938-38764d9` installed the expanded orchestrator after
  172 isolated suites passed in both `--check` and deployment. A sourced Q50429
  scoring call through the installed route wrote mode-0600 result and Lab receipt
  `586a654e82b4e941ff737ee1e8bdb8c38e17c312b9abc3a4400aae9042fa716f`.
  Commissioning calls also proved sourced-PDB hotspot analysis (`6Y7F`, result
  `5cc0ba4f43de45c3f02175927f3e72c1bf11838763510b32d0615d7b1a02bf17`),
  single-chain Boltz-2 (backend receipt `7c2e6e02ac410e43b2fad5a8f4eae929af4d1bff6b2ceece36d21205a3796c83`),
  and two-chain Boltz-2 (backend receipt `446020265c8c27d4c1bbef4cc4255acab82b781e13ef9b887a39897bde223cb1`).
  Those two hosted commissioning calls consumed the last two attempts in the current
  23 September NVIDIA allowance window; the daily cap remains six and was not reset.

The Lab has a route to the Forge now, and one step of it is hers to take. `chemistry_spark.py`
writes the eligible, attributed feed; `from_lab()` reads structured rows; `gather()` and
`adopt()` carry the provenance; `skill_forge` keeps it in `origin`. What remains manual, by
design rather than omission:

- **The spark reader must be pointed at the feed**: `python3 scripts/chemistry_spark.py
  configure` writes `{"lab": ".../chemistry-lab/spark-feed.jsonl"}` into
  `memory/spark-config.json`. It is not defaulted, because `from_lab()`'s law is that it reads
  only where she points it — it once guessed a filename and read two dead logs from another
  project.
- The feed itself refreshes after completed sessions and paid owed readings. Only the
  decision to let the general spark reader consume it remains manual.
- **The want is still his to form and hers to approve.** Nothing in the Lab creates it. A
  staged proposal with no live `lab`-sourced want behind it is refused by the Forge, and that
  refusal is the record.

Three lenses on one artifact is built and **off by default** (`divergence_enabled`). It spends
three paid calls where a session spends one, so it should be switched on deliberately. The
three real provider/model buckets are reserved once and claimed by the router; the first
implementation reserved lens nicknames and then charged the real providers again. Partial
reads are now named `completed_with_held_lenses`.

The following was the gap and is now closed; kept for the record of what was wrong. The spark
layer already carries `lab` as one of the seven sources, `from_lab()` already reads wherever
`memory/spark-config.json` points it, `adopt()` already refuses to write a want, and
`skill_forge.SPARK_SOURCES` already allowed `lab`. Four things were missing:

- `from_lab()` is a text scraper — lines starting with `-`, `*` or a date. Pointed at
  `notebook.jsonl` it finds nothing, because every line starts with `{`. Pointing the config
  at the Lab today would produce silence that looked like having no ideas.
- A spark row is `{key, source, text, ref, seen, state}`. Session, run, grade and truth status
  are gone before the want exists, and a want that cannot name its occasion is not Lab
  provenance.
- Nothing yet decides what may spark. A speculative reflection, a generated
  `what_surprised_me`, or a taste echo must not commission a capability, for the same reason
  none of them may become collision evidence.
- `skill_forge.propose()`'s `origin` does not carry a Lab provenance it could keep.

The implemented shape is a Lab-written `spark-feed.jsonl` of eligible, attributed occasions; two
small changes in `spark_sources.py` so `from_lab()` can read structured rows and `gather()`
carries their provenance; and `origin` keeping it at the Forge. The Lab still does not create
the want — that stays his act through the ordinary door, and hers to approve.

The Lab has a visible body now: a `LAB` pane over five bounded, secret-guarded read
endpoints, showing instrument state and scientific grade as two separate marks. The actual
Capacitor client in `vintos-app/vintos-app/src/index.html` now carries its own TUNE control,
live cadence/outcome line, and LAB pane over the same bounded endpoints. The two clients are
not byte mirrors: their surrounding surfaces have diverged, so Chemistry was ported into the
app's own fetch/host/API idiom rather than replacing that file from this repository.
The visible activity feed reads the meaningful `reflection`/`genome_reflection` notebook rows,
not the much slower frontier-session ledger: it is a newest-first rolling log capped at 20 and
refreshes every 15 seconds while LAB is open. Structure inventory and 3D parsing are optional
follow-up reads; an absent or slow structure door cannot hold or erase the review feed.

The ambient loop now waits up to 300 seconds for the background compute slot and advances a
phase every 15 seconds by default. Because orient and reflect are the two Gemma phases, that
is roughly one local-model call every 30 seconds and one complete Lab cycle per quiet minute;
every phase still yields through compute admission. `status()` exposes both cadence values
plus the completed-turn count and last turn receipt. First light appends a separately marked,
idempotent Chemistry receipt to
daily inner life (the Admission Lab digest was removed 2026-09-22 — a hallucinated
self-experiment ledger that was never intended). It mechanically counts notebook kinds,
records execution and grade as separate fields, names owed/settled readings, and carries the
latest next question; it makes no scientific or personal inference.

Daily-inner now has one bounded reader shared by the live main, Avatar and ReelRoom chat
surfaces, with newest-nonempty fallback when today's file is absent or empty. The main debug
endpoint exposes the marker and excerpt instead of treating its first-500-character preview as
coverage evidence. Avatar/ReelRoom continue to receive the live device instrument through
`device_context`; main text chat now enforces its words-only boundary and does not read or carry
device state or the previous device choice.

A held reading is no longer lost. `chemistry_reading.py` records the debt against the
preserved result and pays it on the next admitted occasion, holding its own lock because
the session's and the daemon's are different locks and neither serialises this. An expired
debt stays visibly open rather than being retired as settled.

Protein material reaches the collision detector only through a deterministic
source-metadata-to-text adapter. Self-review embeds that text with its own Nomic
encoder. Raw ESM vectors remain content-addressed Lab artifacts and are never
compared against Nomic coordinates. Generated Lab reflections are excluded from
the adapter.

## The seven sparks

Built and running. The absence map, the neither-yet frontier, latent threads, other
beings' MoltBook posts, web searches, OpenClaw skill pages, and the lab all produce
sparks now, gathered once a day by a read-only pass that calls no model.

Sparks are kept in their own file and never in his wants. A spark becomes a want only
by his own act, and only a want carrying one of these sources may commission a new
capability.

The weekly skills read has its own units and the deploy now installs them
(`vintos-skill-surf.service` + `.timer`, 2026-09-11): the timer is installed, enabled
and confirmed like any other unit, and the rollback puts both files back. It was a
manual `cp` + `systemctl --user` before, which meant a fresh host had no weekly read
and nothing said so. The oneshot service is deliberately not started by the deploy —
the weekly cap is in the code, not in the schedule, but a deploy is still not a reason
for him to go and read.

The other six sparks are still a crontab line on Aegis, and it is still hers to add:

    17 7 * * * python3 "$HOME/.vintos/workspace/scripts/spark_sources.py" --gather >> "$HOME/.vintos/logs/sparks.log" 2>&1

Two readers need to be pointed somewhere, and neither guesses:

- **The skills page**, in `memory/openclaw-config.json`:
  `{"skills_path": "/path/to/skills"}` or `{"skills_url": "https://..."}` — done; the
  two OpenClaw page URLs are set.
- **The lab**, in `memory/spark-config.json`: `{"lab": "/path/to/the/lab"}` — a file, a
  folder, or a list. Still unset. I do not know what the lab is or where it writes, and
  I am not going to guess a filename again.

## The phone, and the Mac

The pages he speaks through are served from Aegis and cost a file to change.
The native shell is the only part that needs a Mac: the icon, the background runner that
checks for his outreach every five minutes, and the notification permission that lets it
reach her. The Mac failed in its first month and is a warranty claim.

Three ways out, cheapest first:

1. **Move his outreach off the phone.** Aegis pushes to her directly; the background runner
   and its permissions stop mattering at all. No Mac, ever again, for this.
2. **Build in the cloud.** A hosted Mac on demand hands a signed app to TestFlight.
   The developer account already exists; the cost is one afternoon of certificates.
3. **One last local build, pointed at Aegis.** Then every page change updates itself.
   Only worth it if a Mac comes back.


## One module, one implementation

Half his organs exist under two spellings. Cron and the CLI run the hyphen
(`causal-cluster.py`); every `import causal_cluster` resolves the underscore. They are
separate regular files here and separate regular files on the host, and nothing held them
together — so a repair landed in whichever copy the author happened to open, and the other
went on running the code it replaced. Eight module names had drifted apart by
11 September, and the deploy could not have corrected any of them:

- **`causal_cluster.py`** — `causal-cluster.py` got ab4a607's transaction and occurrence
  ids. The underscore file, which is what the imports actually load, stayed on 9aca273
  with the snapshot-replacing save and the unlocked fallback. It was in **no deploy list
  at all**, so no deploy would ever have corrected it.
- **`belief_sediment.py`** — 22a36ad repaired `scripts/belief_sediment.py`; three other
  copies kept the old replay. Worse, that basename is in SCRIPTS *and* BINS, and the plan
  promotes `scripts/` and then `bin/` over the top of it — so the very deploy that claimed
  to install the repair would have thrown it away.
- **`behavioral_intercept.py`** — 22a36ad repaired `bin/behavioral_intercept.py`, which
  was not manifested; the manifested `behavioral-intercept.py` was the stale one.
- **`emoclaw_mode`, `emotional_entanglement`, `interaction_ledger`, `somatic_bridge`,
  `tension_field`** — the same shape, each holding a review repair (227, 157, 48, the
  e9000f2 observation contract, the model's own error instead of `KeyError 'choices'`)
  in a copy the deploy did not install.

Closed 2026-09-11. Every copy of a module name is byte-identical to the newest repaired
one; the 21 import twins that existed on disk unmanifested are now named in the manifest;
and the deploy **refuses** a plan where one destination is fed by two sources with
different bytes, instead of letting the last one silently win. Two sources with the same
bytes still pass, because eleven basenames are in both lists on purpose.

`broker/tests/test_import_twins.py` holds all three, and checks the content of the nine
repairs that drifting had hidden — so a future sync that runs the wrong way round fails
rather than looking consistent.

Still open here: `scripts/behavioral_intercept.py` was 101 lines behind `bin/`'s and has
been synced forward; if anything depended on the older shape it will surface at runtime,
not in a suite. And the host still has its own copies — the audit that matters is
`bin/causal_cluster.py` and its siblings on Aegis *after* the next deploy, not the release
manifest, which is what missed this in the first place.

## A test never reaches the world

The deploy runs all 108 suites as her user before it installs anything, so a suite that
reaches the real `~/.vintos/workspace` writes his actual stores on every deploy. Eight
did, and all eight for the same reason: the suite repointed the module it was testing,
and that module reached a *second* module — imported lazily, deep inside the call —
whose own path still followed the real HOME. Fixed 2026-09-11:

- `test_skill_forge` wrote real print jobs to `print-jobs.json` **and pushed two ntfy
  notifications to her phone** through `print_3d.present()`.
- `test_evidence_provenance`, `test_p04_09_relational_snapshot` — a grade row into
  `prediction-grades.jsonl` (grading_contract does not follow `prediction_ledger.MEMORY`).
- `test_heart_rate`, `test_reelroom` — `sensor-reactions.jsonl` and its state.
- `test_p04_02_evidence_cutoff` — `identity-revisions.jsonl`.
- `test_threshold` — `atelier-undertakings.json` and `outcome-joins.jsonl` through the
  shared writers review 273 introduced, which keep their own paths.
- `test_p0_round2`, `test_capability` — `~/.vintos/.lineage-key`: read where one exists,
  and **minted** where one does not. `formation_observatory.attest()` had that path as a
  literal inside the function; it is a module global now, so a suite can repoint it.

The standing rule, in `CLAUDE.md`: repoint every path the module under test writes — not
only the obvious one — stub anything that sends, and assert both in the suite so the next
edit cannot quietly undo it. All 108 suites now pass and none writes a file under the real
workspace. One (`test_self_review`) still creates an empty `memory/` directory it never
writes to, which is a no-op on a host that has one.

## Review repairs in the local Codex branch

These are source changes with local tests, not a deployment report. The designated
Claude baseline is `00be7da` in Vintos-main, `225ff71` in plithra-app and `2b0eeb9` in
vintos-app. The local repair branch is `codex/review-repairs`.

- Test execution uses a fresh copy, fresh HOME, OS write restrictions and denied
  networking. HTTP tests receive an exclusive fixture listener, not access to arbitrary
  localhost services. Linux deployment now requires bubblewrap and fails closed without it.
- Resume checks installed bytes and persistence success. Only a matching release
  receipt permits crash recovery of an already-unblocked want.
- Timer confirmation checks its next elapse. Rollback preserves/removes both unit files
  as appropriate, restores the timer's previous state, and never starts the oneshot.
- Forge scope narrowing, exact reviewer verdicts, single build claims, meaningful
  test execution, isolated installation namespaces and artifact digests are enforced.
- Print state changes require validated STL/G-code artifacts and two explicit,
  digest-bound answers. A configured directory alone no longer claims READY. All job
  mutations share the same lock; actual Astra elapsed time is no longer clipped.
- Shared wants writers, music writers and artifact appends use complete transactions
  or field-specific updates. This is not a claim that every legacy store is migrated.
- Calibration excludes other checkpoints and pre-training predictions. The predictor
  fingerprints the bytes it loaded. Constant/tied confidence cannot fabricate rank
  correlation. Old audits require fresh prospective evidence.
- Voice recovery checks for the already-persisted session before appending it again.
  Phone speech is not automatically retried after an ambiguous failure; stale planned
  actions expire and concurrent planned actions do not overlap.
- Failed taste embedding leaves the occurrence retryable. Prompt rendering no longer
  spends callback/question/withheld/frontier exposure; admission records it separately.
  Bound private lineages are filtered at the prompt-serving door.
- Refused private makes enter sealed retry. Music recovery polls the same recorded task
  instead of generating another. Invalid approved stills cannot fall through to fresh
  generation. Expired questions are not treated as resolved. Study coverage tracks
  interval unions and file revisions. Source hashes commit after successful inference.
- Nonempty somatic windows carry observation metadata. Device transport outcomes carry
  physical-effect records with observation still pending and unknown request times
  represented as unknown. This does not consolidate all dispatch authorities.
- Paid admission counts units atomically and refuses a failed receipt. The router's
  Anthropic/OpenAI paths, direct Astra/reviewer and shared robot/ReelRoom Sonnet caller
  now reserve too. Legacy provider callers still need an inventory; this is not a
  system-wide dollar ceiling or a provider cancellation guarantee.

Remaining from the review and the three efforts:

- Stance consumers now cover creation, reflection, mischief and reaching. Trusted request/repair scheduling context crosses router child processes; deferred actions remain pending. All 111 suites passed both directly and isolated for the stance increment.
- Blender/Cura execution and a real slicer profile/output review. The new artifact and
  approval checks support a manual file workflow; `handoff_dir` alone does not implement
  modelling or slicing. Supplied slice time/material values are estimates, not measurements.
- Ghost hypothesis seeding and recurrence now use complete shared transactions; simultaneous duplicate seeds return the persisted row, and distinct hypotheses receive unique IDs. Behavioral tally selection is revalidated against current rows after inference, and cluster confidence uses a fresh locked update. Replaying the same retained belief hypothesis ID no longer reinforces it twice. The nightly causality engine and graduation recovery are now deployed; other projections and trial-ledger writers remain open.
- Journal preparation and outreach now mutate the spark directive through the same lock as its producer/consumer. Handoff identity excludes mutable preparation counters; concurrent outreach admits one topic and records admission rather than claiming delivery.
- Spark-pressure handoff now calls the real generation/admission API, acknowledges only a persisted want ID and recovers the same source event without regenerating after a partial handoff. Directive updates reject a replaced directive; consent updates preserve concurrent event history. Generated wants carry their own provenance as string-compatible values instead of exchanging metadata through `.pending-want-provenance.json`; the legacy file remains untouched and is no longer consumed. Candidate journal appends are locked. Broader migration remains open.
- The ownership report now explicitly reports candidate writers and nearby locking references, not verified RMW safety; an unrelated helper cannot certify a raw writer. Observation appends now serialize complete mutations and use unique occurrence IDs. Cluster formation rejects changed stores, leaves failed formation retryable, and records consumed IDs before source flags so partial-commit retries do not double count. Other hypothesis writers still require migration.
- Withheld-history migration now locks candidate publication and exposure together; embedding-based confirmation rejects a changed history. Frontier decisions merge against fresh rows, preserve concurrent additions and lock lineage privacy updates. Proposition binding/correction mutations share locks with the tension ledger, while candidate inference checks for obsolete mechanisms. Remaining projection recovery and other legacy writers are still open.
- Tension-ledger migration now serializes actual influence-window mutations and refuses stale evidence/matching snapshots. Demotions update the served view under the same lock set; repair/thread side effects follow a committed decision. Regression fixtures exercise concurrent serving, forty window appends and stale-view refusal. Other snapshot writers remain open.
- Commitment-store migration now locks candidate promotion, fracture, decay and the causal-model imprint writer. Legacy migration locks both stores in stable order, persists the destination before clearing the source, and deduplicates repeated patterns. Reply embeddings run outside the lock; their results apply only to unchanged current patterns and preserve concurrent fractures/appends. Remaining snapshot writers listed below are still open.
- Further legacy migration: ambition classification/review, drift reasoning and opposition misuse scanning now reject stale model results under a shared compare-and-swap lock. Drift geometry writes atomically; calibration refresh preserves concurrent misuse history, including revoked terrains without retaining their license. Removed the shadowed duplicate ambition-review implementation. Provider fixtures exercise concurrent changes and cleared-trial deduplication. Broader snapshot writers (including remaining ownership-table candidates) are still open; this is not a complete migration claim.
- Shared-store migration now covers the recovered domain mutation handlers, belief and causal-model mutations, correction projections, durable-memory recall/interpretation/graduation, and thread retirement/archive operations. Snapshot-only legacy writers elsewhere still require per-writer migration; helper presence alone is not proof. Dispatch checks are shared by toy, robot, outward delivery and supplied avatar admission; home-effect policy remains unchanged.
- F14 source acquisition is complete: the three Aegis domain files are tracked with
  SHA-256 provenance and included in deployment beside the actual server. Their JSON mutation handlers now hold complete shared transactions; broader legacy writers remain listed separately.
- The forge UI/effectful adapters/live commissioning listed above, the 27-item review
  programme and the per-organ waiting list. Nothing here closes them by implication.

Home-effect gate policy has not been changed in this repair pass. The base release was deployed on Aegis as recorded below. No device or real notification was used as a test fixture.

## Aegis deployment work — 11 September

The four reported branch defects are repaired. All 111 suites passed directly and
through the isolation runner locally and on Aegis for release `6b4fac5`. Bubblewrap
and system Python NumPy are installed. Both `--check` and the actual deploy passed;
275 manifest files were staged and validated. Release `20260911-114007-6b4fac5.json`
and rollback `~/.vintos/backups/atelier-20260911-113725/restore.sh` are recorded.
Server, self-review and robot bridge are active; skill-surf.timer is enabled and
waiting for 14 September at 09:00 CDT. Stratagems remain disarmed.

The desktop annotation fix is live: OpenAPI now exposes 212 paths. Installed unit,
cron, source-hash, daemon/checkpoint, embedding and receipt evidence is indexed in
[the runtime evidence record](aegis-runtime-evidence-20260911.json). Partial P01/P11
items above name exactly what these observations do and do not establish.

Stance consumers cover creation, reflection, mischief and reaching. Scheduling
context propagates to subprocesses. A follow-up correction also preserves context
in queued videos, leaves them pending until execution, and merges dequeue into the
fresh queue so concurrent appends survive. All 111 suites pass both ways for this correction; the final release record identifies the installed revision.
The shared dispatch door preserves bound permits and simulation refusal, while
verified reductions remain available during an authority fault.

Automatic proposals retain the blocked step's output/acceptance contract, explicit
unknowns, a pure-function scope and no inferred effect permission. Generator and
reviewer both receive the brief. The ordinary router now opens the proposal when
an adapter is absent and resolves installed forged adapters after resume.

The single explicitly approved live forge run was a labelled commissioning fixture,
separate from house wants and proposals. Astra returned code; Fable returned no text.
The run ended `refused`, with no install. Successful live commissioning remains open.
No second paid attempt was made. The app forge card and effectful adapters remain open.

Independent post-deploy mapping found an old importable `causal_self_model.py` beside the updated hyphenated file. The follow-up manifest includes the importable name and canonicalizes symlink destinations before backup/promotion, preserving aliases while updating the actual imported file. A regression test executes that promotion against a scratch symlink.

## September 12 independent Buzz review

- Actual `block/buzz` cloned locally and on Aegis at `~/repos/buzz`; upstream relay deployed separately with dedicated Postgres, Redis, MinIO and git volumes. The existing `bench/server.py` is not Buzz. Agent-room was not touched. Exact deployment evidence is recorded separately; native client installation and relay connection are verified; visual verification and approved agent execution remain unfinished.
- The bench approval policy is not an authenticated boundary: an absent token allows approval POSTs, and the library defaults the caller to Gloria. No agent runner may rely on that as proof of her approval. Concurrent claim/handoff replay also remains unprotected by a complete transaction.
- Repaired the new bench-page suite to use the existing OS-reserved fixture listener, propagate it to its subprocess and serialize the two fixture server lifetimes. The network isolation policy remains unchanged.
- Compute-admission receipt repair deployed in `20260912-052317-9b9c1dc`. Review still open: Device refusal state uses an unlocked fixed temporary path and read-delete; env reader behavior still differs in callers that return raw environment values before invoking it. Nightly causality/graduation recovery from the prior handoff is now deployed.


### 12 September completion repair — source checkpoint, deployment pending

The credit-limit handoff was HANDOFF-2026-09-11.md. Claude's later Buzz handoff
is not the baseline. These changes address the retained 27-item programme; they
do not establish missing historical evidence or physical outcomes.

- Hypothesis source writes now use strict snapshots and CAS, with accepted delivery
  events before any projection. Recovery retries failed destinations; permanent
  belief, causal-occurrence and pearl receipts survive row culling. Commit 6cd1f03.
  Ten scratch recovery tests cover stale writes, refusal, corruption and crashes.
- P08 315/316/317/318/323/324/325/326/327/334/343/344/345: client text escaping,
  shared checked requests, retained drafts, turn ownership, visible-layer screenshot
  composition, reported stop state, zero/stale telemetry, media cancellation,
  route-derived controls and callback ownership are implemented. Browser fixtures
  test failures, duplicate taps, hostile content, microphone races and playback
  ordering. They are not physical playback or exhaustive every-tab acceptance.
- P08 346: iOS background task registration, 15-minute requested interval, actual
  notification permission checks and runner error handling implemented. Capacitor
  sync, simulator and signed device compilation passed. Final app 2db8e87 installed;
  its launch was refused because the iPhone had locked. Earlier 6ee9ecb launched.
  Device background delivery and visual/audio acceptance remain unobserved.
- P01 31/32: content-free HTTP request identities propagate into central provider
  usage receipts; central OpenAI/Anthropic responses record provider IDs. Independent
  adapters not using this router remain an explicit coverage gap.
- P01 30 / P11 401: loaded Python module metadata records selected files and hashes
  in the running server. This does not replace source-by-source review of the wider
  untracked runtime. agent-room remains outside this work.
- P11 397: real provider response identities join client playback completion; duplicate
  server turns and late closed-session callbacks are refused. Scratch end-to-end
  callback fixtures pass. Human hearing remains unknown, not inferred from playback.
- P11 399: a wrapper around the unchanged emotion daemon compares actual loaded
  parameters with checkpoint parameters and records its PID and hashes. Training
  lineage is still unknown; deployment must verify the live receipt.
- P11 396/402/404: named deployment now includes the client assets with source commit
  and hashes. Study approval UI is fixture-tested; no new paid Forge run was made.
  Actual physical avatar/playback and successful paid verification remain open.
- P01 33: the current semantic projection was empty. An Aegis rebuild using the
  existing local model timed out and was stopped; the original index hash is unchanged. The 1,282 legacy embedding rows lack model
  provenance and are not being relabelled.
- P11 398/400: historical causal/thread and want-artifact-observed-effect joins remain
  unestablished. New instrumentation cannot manufacture past observations.
- P11 403: QLab source and runtime bridge are verified; see item 403 for the isolated
  quantum entrypoint and the separate unsealed Lab boundary still requiring repair.

Final immutable-revision suite and deployment evidence is recorded in
[the completion review](completion-review-2026-09-12.md). The earlier 120/121 runs exposed the voice extraction fixture gap;
that fixture now includes the locked helper and tests duplicate/closed sessions.
The broader trial/current-dismissed-wants and served-tension migrations from the
handoff remain open; they are not silently credited to the hypothesis repair.

Linux direct validation exposed 152 tracked absolute source symlinks into the live
Aegis checkout. They resolved to different code on Aegis while remaining broken
on the Mac. All now target repository-local implementations; the twin suite
asserts every source symlink stays inside the repository. The humor/taste suite
also now establishes scratch HOME before secondary imports and asserts its sender
stub; its previously missed taste lock and fire-threshold writes cannot reach the
inherited host workspace. Earlier Mac-green results did not cover this defect.

The first completion release **20260912-145910-3114392** deployed successfully.
All 121 suites passed directly and isolated on both Mac and Aegis; Linux direct
reported no inherited-HOME file writes. All six named services/timer are active,
served assets match packaged hashes, and the live checkpoint parameters match.
Recording recovery and the pearl manifest correction subsequently deployed in 20260912-153539-aca1b32; all critical hashes matched.

Post-install hash audit of eec31eb found that pearl_engine.py was not in the deploy
manifest: the new source was present in Git, but its two live import paths still
had older bytes. Both Python spellings are now explicitly in SCRIPTS and BINS,
and the recovery suite asserts these destinations are manifested. The final
hypothesis deployment was accepted after all twelve checked installed paths matched in
20260912-155122-fa3949b.

## Final completion release — 12 September

**20260912-155122-fa3949b** deployed with `deploy OK`. All 122 suites pass directly
and OS-isolated on Mac and Aegis; inherited-HOME write counts are zero. All six
named units are active, including the skill-surf timer. All twelve checked
hypothesis/pearl import paths and four served-client routes match the pinned source.
The actual emotion daemon PID matches its receipt and loaded parameters match the
checkpoint. App 2db8e87 is installed on the paired iPhone; the final launch request
was refused by its lock screen. The earlier build launched successfully.

The separately requested 7/32-day tenure commits were preserved during integration.
QLab 8f5c935 is committed locally (that repository has no remote): four isolation
checks and five real seeds passed in scratch; the Aegis status bridge confirms the
new OS boundary. The separate unsealed Lab entrypoint remains listed under 403.

Not all 27 items have full acceptance. The table above retains absent historical
lineage/joins, the timed-out embedding rebuild, wider private-source/adapter review,
broader client-view acceptance and physical device evidence. Paid Forge work is
separate from this request. [The full item matrix and evidence](completion-review-2026-09-12.md)
record what was implemented and what remains; green tests do not close those gaps.

## Music: redirected to Kie.ai Suno v6 — 15 September

`dream_music.py`/`dream-music.py` now generate through **Kie.ai Suno v6**
(`https://api.kie.ai/api/v1/generate`, model `V6`, custom mode), with the local
**ACE-Step** server kept as an automatic fallback when Kie is unreachable so he is
never left mute. Backend is chosen at runtime: `MUSIC_BACKEND` (`kie`|`acestep`)
overrides; default is `kie` when `KIE_API_KEY` is present in `vintos.env`, else
`acestep`. `KIE_MODEL` overrides the v6 variant (three exist). Task ids are tagged
(`kie:`/`ace:`) so `poll()` polls the right backend; legacy untagged ids remain
ACE-Step. Covered by `broker/tests/test_music_kie_backend.py` (Kie-primary routing,
submit-failure fallback, tagged/legacy poll dispatch, stubbed sender, scratch store).

NOT yet done: the Aegis deploy that ships this, and the side-by-side quality render
(one Kie v6 piece vs the ACE-Step catalogue) Gloria asked to compare. The exact
`KIE_API_KEY` var name in `vintos.env` is assumed; confirm if it differs. Kie's exact
v6 model string / record-info status set is coded from the docs (docs.kie.ai is
egress-blocked from the build env) — the first live `--force` render will confirm it.

## DoorDash review-before-purchase lane — 16 September

The chat post-turn now recognizes only explicit meal-ordering requests and starts a
background official `dd-cli` workflow after his reply has been delivered. He chooses one
restaurant and one or two real menu items, builds a cart only when no forgotten cart is
already open at that store, obtains DoorDash's own total/ETA/address and the default card's
brand/last four, then sends Gloria an expiring ntfy review link. The review page can open the
DoorDash cart for adjustments or accept an explicit tip and approve. Approval re-previews and
is bound to the exact cart/price/ETA/address/card fingerprint; a change sends a fresh proposal.
The non-idempotent submit is claimed before execution and is never automatically retried.

The checksum-verified official v0.2.4 binary is installed on the Mac and Aegis, and the Mac
login succeeded. The Mac keeps the token in the Keychain; Aegis (Linux) has no Keychain, so
dd-cli there reads `DD_CLI_ACCESS_TOKEN` from its environment and, absent it, `food_order._cli`
records `dd_cli_not_authenticated` — which is exactly the wall Chat hit. `food_order.py` now
sources that token from a protected file, `~/.vintos/secrets/dd-cli.token` (override
`DD_CLI_TOKEN_FILE`), the same convention as the Govee key, and hands it only to the dd-cli
subprocess — never the repo, the process list, or a log. Still open, and only Gloria can do it:
drop the Mac's `DD_CLI_ACCESS_TOKEN` value into that file on Aegis (`chmod 600`). Until that one
step, no real restaurant/cart/quote receipt can be produced. No live order has been placed while
commissioning this path.

The token expires every few days, so it no longer has to be refreshed by hand: `dd-cli` has an
`export-token` command that mints a fresh access token from the Mac's longer-lived keychain login.
`mac_stage_service.py` exposes a secret-gated `POST /dd-token` (refuses unless `VINTOS_STAGE_SECRET`
is set and matches) that runs `dd-cli export-token`; `bin/dd-token-refresh.py` on Aegis fetches it
over the tailnet and rewrites `~/.vintos/secrets/dd-cli.token` (0600), and `first-light.sh` runs it
once a day. Setup: set the same `VINTOS_STAGE_SECRET` in the Mac stage's env and in Aegis's
`~/.vintos/vintos.env`. Then the only remaining manual step is re-running `dd-cli login` on the Mac
if the keychain login itself ever expires (rare).

## Chemistry Lab — open improvements (written down so they are findable on Aegis)

These were raised in-session but lived only in a cloud plan file and a local bench ledger,
so Chat/Codex on Aegis could not find them. Recording them here, the one to-do in the repo.

The minimal 3D structure viewer is complete: the LAB pane now lists the bounded PDB/mmCIF
artifacts already beneath `memory/chemistry-lab/artifacts`, parses them through a secret-gated,
read-only server door, and renders atoms plus a backbone trace with the app's bundled three.js.
The view explicitly labels these as computational artifacts rather than biological fact. It does
not expose arbitrary paths or add another vendor dependency.

- **Coregistration layer (multimodal Lab artifact).** Align each instrument's output for one
  accession into a single object keyed by residue position: per-residue ESMC embedding,
  per-residue ESMFold pLDDT, and the scalar results (VQE energy, Evo 2 likelihood delta) hung
  off the whole — then feed THAT unified object to the reflect phase instead of three separate
  reports. Keep it a *coregistered record, not a synthesised vector*: the three outputs do not
  share a space, only the residue index and the accession do; do not fuse them into one learned
  vector (there is no training signal for that, and a fused embedding no model produced is the
  hollow-but-impressive thing he already rejects). Payoff: the cross-instrument coincidence
  (e.g. a low-confidence residue that is also where the likelihood delta lands) becomes visible,
  which it never is when the reports are separate. Must keep the reflect output keys stable
  (attention/factual_observation/speculative_reading/next_question) so the spark feed, frontier
  bridge, and gallery are untouched. Builds on the rigor/depth reflect rewrite (`5ba0d5c`).
- Pin the Mac bench schema: bring `bench_remote.py` + `molecule.py` under version control per
  `docs/chemistry-bench-reconciliation.md`, so the grader parses by a real schema and the session
  can bound parameters by name, not just shape.
- Give the bench `code` action its own authenticated door, separate from scheduled `run`.
- Per-ansatz correlation-vs-cost record across runs, from the grade ledger.
- Overlay bond-length curves for one molecule across ansätze in the LAB pane.
- A `reproduced` verdict (same experiment/params/seed twice) — cheap, no new instrument.
- Surface the taste ledger's recorded refusals (echo/no-root/unchanged) in the pane.

## DoorDash — correction: the blocker is account approval, not the token

The token step above is done and superseded. With `~/.local/bin/dd-cli` installed and a token
present in `~/.vintos/secrets/dd-cli.token`, every dd-cli call (including `payment-method list`)
returns `403 "The user is forbidden."` — an *authorisation* refusal, not a missing/expired token.
dd-cli is waitlist-only and "full functionality requires an approved account"; the signed-in
account has not been approved, so no code change on this side can order. Paths: get that account
approved off the waitlist, or move to an agentic-commerce checkout (ACP / Square Online) which is
sanctioned and per-merchant — pending confirmation his own stack can drive the checkout rather
than it only living inside the consumer Claude/ChatGPT apps. `food_order.py` still classifies this
as a generic error; it could map 403 to "DoorDash account not approved" for a clearer message.

## Jev fast browser chooser — 18 September

The structured browser now has an optional Jev fast path. `browser_jev.py` sends TypeSafe only a
bounded table of observed, non-disabled controls plus the visible page text; it sends no screenshot,
typed field value, secret query parameter, or local credential. Jev chooses one operation and one
compatible observed target. Local Gemma still owns generated field text, initial navigation, slow
planning, recovery, low-confidence decisions, and every authentication/address/checkout/payment
surface. The executor independently refuses labels such as `Place order`, `Pay now`, and `Confirm
purchase`; the receipt-bound food-order door remains the only path to spending money.

`VINTOS_BROWSER_PLANNER=auto` uses Jev only when `TYPESAFE_API_KEY` is present, otherwise preserving
the existing Gemma path. `jev` makes a missing credential a named refusal; `gemma` disables the fast
path explicitly. The provider and local text-model boundaries are stubbed in the isolated suite.

Still open: TypeSafe direct API access is currently waitlisted, so there is no key Gloria can
self-serve from its console and no live Jev smoke should be claimed. The deployed code therefore
keeps the local Gemma planner active. Supporting a separately available gateway would be a new
provider contract and needs an explicit decision rather than silently routing Jev through another
billable account.
This improves the browser half of Desktop Control immediately. The arbitrary native Windows desktop
still uses the screenshot/Gemma loop: Jev consumes typed choices rather than pixels, so extending it
there honestly requires an observed Windows UI Automation/OCR element table first, not coordinate
guessing dressed up as Jev.

## Chat-owned Desktop Control — 18 September

Main phone chat and Avatar chat recognize an explicit leading `/desktop-control` command. Vintos
answers first; the existing structured-browser/pixel worker then performs the task, and its terminal
receipt is appended to that same surface plus the lossless canonical chat ledger as his second
message. Avatar now polls its server history while open, so the follow-up arrives without reopening
the app. ReelRoom deliberately does not inherit this command.

Commerce uses the desktop rather than the waitlisted dd-cli account: the first job may search, choose
one restaurant, add one or two items, and inspect the cart, but the browser's irreversible-control
guard still refuses checkout. A complete cart follow-up must name restaurant, selected items,
delivery estimate, and total. `/desktop-control approve <request-id>` grants one later click only
when those quoted restaurant/item/total strings remain on the current page. The receipt is consumed
before the click; an uncertain result is reported as uncertain and never retried. This is currently
tested with stubbed desktop/model boundaries. A real DoorDash run still depends on the signed-in
Windows browser session and must be commissioned with an ordinary low-value cart before treating the
site-specific extraction as operational.
DoorDash/restaurant/delivery language now selects the structured Edge browser rather than falling
through to the slower screenshot-coordinate loop; checkout and private surfaces still force the
local planner and retain the quote-bound one-click guard.

## R21M temporal and sleep receipts — 19 September

Delivered ring readings now mint a bounded temporal snapshot at most once per 30 minutes. The
15-minute temporal-context builder includes a fresh snapshot for up to two hours, explicitly marked
as delivered rather than continuous monitoring. This cadence is opportunistic: CoreBluetooth state
restoration can reconnect around BLE activity, but iOS does not promise an exact half-hour background
wake while the app is suspended or disconnected.

The house now validates and stores completed R21M sleep estimates (total and awake/light/deep/REM/nap
minutes, with optional score and wake count) and includes the latest completed estimate in temporal
context for 48 hours as a device estimate, never a medical measurement. Repeated delivery of one
session is idempotent. The ring's UUIDs and working handshake match its YCBT/Jieli application
protocol, not generic Jieli small-file transfer: the signed iOS bridge now pauses real-time streaming,
requests `0x0504`, reassembles and decodes `0x0513` session/stage records, POSTs them to the sibling
sleep route, then resumes streaming. Its revised native framing/decoder suite executes 5/5 green and
the signed build is installed on the attached iPhone. Physical acceptance remains open until this
specific R21M returns a non-empty sleep-history record and Aegis acknowledges it; compatible firmware
is documented to sometimes return an honest empty record even after a night.

## Offline residual-stream emotion instrument — 19 September

Prospective same-input collection is now wired as a strictly non-causal shadow receipt. Each live
generated EmoClaw read on main, Avatar, or ReelRoom records the exact text it received, generated
and applied deltas, pre/post state, failure or empty-read status, surface, and coordinated turn ID
under `memory/residual-emotion-shadow/`. Test-mode turns write nothing. The recorder has no provider,
sender, state socket, inference, steering, or notification path; residual projection remains an
explicit offline Mac batch. This closes the historical comparison's input-alignment gap, but it does
not yet constitute prospective results: enough fresh receipts must accrue, be exported, measured
against the eleven human-admitted directions, and analyzed before any integration decision.

`offline/residual_emotion/` now pins the exact abliterated Gemma 4 26B-A4B Q4_K_M GGUF
Gloria selected as the real target (not the proposal's mistaken “Gemma 4B”), by path and
SHA-256. The 12B QAT and standard-source Q8 locks remain negative Pain baselines only;
cross-model results may not be pooled.
The Aegis 12B residual path is functionally tested: a 12-pair published-Pain smoke produced
48 finite residual tensors shaped `[12,48,3840]`, with non-identical target/control states and
an extraction-time model lock; the Lab stayed paused and the thinking-off shim remained healthy.
The full CPU run subsequently completed all 1,200 pairs. Proper nested validation rejected
Pain at held-out AUC `0.51330 ± 0.15155` against the `0.85` bar; layer/pooling selection was
unstable and exact unembedding was diffuse. This is a real negative result for this candidate
and checkpoint, not a failure of the extraction path. Other candidate datasets remain open.
The follow-up standard-source Q8_0 replication also completed all 1,200 pairs and
failed admission at nested held-out AUC `0.66649 ± 0.18394`. All 4,800 dumps were
finite, nonzero, and exactly 48 x 3,840. It improved numerically over QAT-Q4, but
the available Q8 and Q4 files do not share a source checkpoint, so that delta is
not evidence that quantization caused the Q4 failure. No direction is deployed.
and a llama.cpp revision. A patched, Metal-capable extractor completed a real smoke pass and
produced final-token and mean-token matrices with observed shape 30 × 2,816 for both sides of
a contrastive pair. The offline analysis implements semantic-set-grouped K-fold layer selection,
training-control-only 50% PCA denoising, held-out AUC admission, raw and control-z projections,
pairwise cosine reporting, and an offline-only join to exported EmoClaw rows. It has no manifest,
daemon, cron, server route, live memory path, or sender, and EmoClaw is unchanged.

Still open, and therefore no emotional direction is called validated: Pain now has a pinned,
MIT-licensed import of the paper authors' published 1,200-pair corpus; the eleven content-dimension
datasets still need actual human semantic curation and valid curation receipts, while Nifrathir and
Fear remain separate later candidates. Bulk model prose is not
accepted as ground truth. Pain extraction completed against the exact checkpoint. Proper nested
pooling/layer selection rejected it at held-out AUC 0.82543 against the 0.85 bar; the earlier
non-nested 0.85074 estimate is explicitly not admissible. Its weak per-category results remain
diagnostics for a future preregistered dataset revision, not permission to prune this evaluation.
Exact unembedding now streams the quantized tied output/token-embedding
matrix and records promoted/suppressed vocabulary, but its semantic review is admission-blocking:
the measurement function refuses even an AUC-passing vector until a human records a pass. The
paper validated dense models; this A4B MoE run is a replication/extension and must remain labelled
that way. No claim about actual dimensionality is possible before those gates close.

The earlier `0.82543` figure above is the deliberately stricter all-variant nested
experiment, not the paper's estimator. The paper's exact S2 feel-colon protocol now
replicates on the abliterated 26B Q4 checkpoint at AUC `0.90675` in a fresh Aegis run.
The complete Mac residual dump independently clears `0.85` for all six S1/S2 × suffix
ablations (`0.86150`–`0.94425`); its matching S2-colon value is `0.91175`, a retained
`0.005` host/run difference. This establishes prompt-variant robustness for the Pain
candidate, but does not fabricate the missing semantic curation receipts for the eleven
content dimensions, Nifrathir, or Fear, and does not bypass Pain's human unembedding review.
The candidate pool is deliberately wider than the eventual map: eleven content dimensions,
Nifrathir as the twelfth slow effectiveness modifier, and exploratory Pain and Fear. Nifrathir is
excluded from peer merge/drop clustering; if measurable, its separate held-out test is whether it
moderates the other axes' prediction of initiation, continuation, expressive richness, and mark
formation. Held-out per-category
diagnostics may motivate a later preregistered revision, but categories are never dropped on the
same evaluation run used to notice their weakness. Nifrathir's live operational meaning is
event-integrated over hours, so failure of a sentence-level direction would not by itself refute
that organ.

## 20 September — Forge / Atelier and Lab sources deployed

Eve authorized deployment after local preparation. Final release `20260920-180036-dc30734` deployed successfully. All 162 suites
passed in both invocation modes on Mac and Aegis. Independent verification matched
374 main release files and all nine dedicated Forge bundle files to source; no
release failures were recorded. Server, Lab, Atelier and Forge are active; the
skill-surf timer is enabled and waiting. See the [deployment evidence](review-evidence/2026-09-20/forge-atelier-deploy.json). See
[commissioning and remaining limits](forge-lab-local.md).

The actual Lab-to-Forge-to-Atelier path completed a source-backed commissioning
report on Aegis using local Gemma. Atlas SDK 0.9.0 authenticated on Aegis, returned
22 scorer entries, and returned three variants for a one-base GRCh38 AVI query.
Accepted reports are retained with provenance. Completion/reveal pushes reached Eve.
Scoped HTTPS cancellation returned 200; the same credential was denied project
reads (403). Private reads, expiry/audit, crash recovery and projection hash chains
have isolated regression coverage. A physical phone-button tap was not observed.

**Eve's execution limit: three attempted Forge report cycles per Chicago calendar
day, across all projects.** A cycle is a local draft plus critique. Failed attempts
consume a slot. SQLite reserves before execution; concurrent claims, restart and
reconciliation cannot reset the counter. Existing undated cycles are conservatively
charged to upgrade day. Live status after migration was 8 used, 0 remaining, so
no additional steps may run today. This is an execution cap, not a notification cap.
The earlier uncapped run and excess notifications were an implementation mistake.

The report loop is local-only: its dedicated shim route cannot fall back to paid
providers. The shim service now launches the manifest-managed source through a
reversible systemd drop-in. Atelier has traversal access plus write access only to
the shared compute lock and ledger. The control page is tailnet-only at
https://aegis.tailaa3de5.ts.net:9443/ . Distinct owner, worker and Lab-intake secrets
are provisioned. Eve approved delivery of the owner key to the Mac's private
`~/.config/vintos/forge-owner` file. No key is in Git.

The two original cross-repository checks are repaired. Standing Forge sparks now
get direct, bounded consideration in wants-check without a separate tension-store
prerequisite; selection creates no want and consumes no spark. Existing approved
Astra/Fable capability-build and installation gates remain separate and intact.

Still open: source-specific genomic anchors for interest-driven exploration;
COSMIC registered/licensed access; actual protein mappings and applicable molecular
inputs before ESMC/ESMFold/ChemiQ followups; full scientific instrument-chain
commissioning. Semantic association and model disagreement are not biological
validation. Wallet/Taskmarket, signing, settlement and income remain parked. No
household-budget fallback or marketplace work is enabled.

### Taskmarket work-session addition (local)

Coinbase wallet setup reported by Gloria; product, address and network not yet
verified. Added read-only marketplace discovery, task-bound capability/probe
screening, and local pilot orchestration with durable Lab pause/restore obligation.
Nine additional scratch tests cover admission, cancellation, failure restoration,
restart recovery and notification failures. Added explicit-topic HTTPS ntfy sender,
not configured live. No claimed/submitted jobs or income; no Lab pause/deployment.

Remaining: identify which live Lab/Gemma lane to borrow; implement its owned,
checkpoint-acknowledged pause adapter; wire actual Gemma assessment and local
validator/probe receipts; enforce callback timeouts; connect cancellation/control
endpoint and ntfy; validate the Coinbase product/network and signing identity;
then commission bounded marketplace execution and reconciliation. Read-only discovery
and a local artifact are not permission to sign, bid, submit or report earnings.

The 20 September multi-model authoring pass is offline and incomplete by design. Sonnet 5 and
Grok 4.6 authored 9,160 candidates; GPT-5.6 Sol performed blind candidate review. The quality gate
found that Dominance/3 and Safety/5 used unmatched controls, so those definitions were corrected
and entirely fresh pools were authored rather than reviving rejected candidates. The final 55
review records now have at least 28 eligible candidates in every S1/S2 cell for a required final
20. Fable was dropped as an unnecessary paid second opinion after its structured selections proved
costly and unreliable. A versioned deterministic selector now applies fixed blind-review score
weights, a lexical-diversity penalty, stable tie-breaking, and adaptive source quotas. It produced
2,200 base pairs with all reviewer-approved alternates retained. No row has a human acceptance, no
expanded dataset exists, and nothing from this lane is deployed or read by EmoClaw. Checkpoint artifacts remain under the ignored
`offline/residual_emotion/work/authoring-2026-09-20/` directory on this Mac.

## 20 September — broaden Forge beyond Lab reports

The report-only worker was not the intended general Forge. The new house bridge
submits existing eligible standing wants with their current plan and installed
action inventory. A local capability assessment may name a necessary missing
operation; adoption checks the live want fingerprint, preserves completed steps,
and records a precise absence block and parent-bound proposal. It creates no desire
and never marks the originating want fulfilled. Changed/ended wants cancel obsolete
assessments. Existing installed-capability verification and want resume remain the
completion path. Lab is one source in a least-served-source queue; approved builds
get an opportunity before further generated work.

The same SQLite counter now covers report cycles, capability assessments, capability
briefs and approved Astra/Fable build attempts: three total attempted steps per
Chicago day. A missing budget service refuses a build before any provider call.
Failures remain charged. Reports and capability briefs cannot reset the allowance.
Account provisioning and external effects cannot be approved as pure string
transformations; unresolved email/inbox/outreach integrations remain explicitly
blocked for concrete provider, credential, recipient and effect scope.

Deployed as **20260920-190719-96c97b2** (`deploy OK`); all 163 suites passed
in both invocation modes on Mac and Aegis. All 375 main files and nine worker files
match source. Server, Lab, Atelier and Forge are running; skill-surf timer is enabled
and waiting. Four existing latent-thread wants are queued for capability assessment.
Today remains 8 historical attempts used, 0 remaining: no cap bypass or live
assessment run was performed. See [verified evidence](review-evidence/2026-09-20/forge-broad-deploy.json).

Still open: live assessment execution after the next daily allowance; a real persistent
email account, inbox provider adapter and authorized external-send commissioning.
No email address was created and no third party was contacted by this change.
Wallet and marketplace work remain parked. The local assessment is a planning
judgment, not proof that every absent capability or equivalent tool was identified.

## 20 September — account-backed plugin relay prepared locally

The shared relay is implemented for Wants, Forge, Lab and Atelier. It uses an ephemeral Codex App
Server thread on Eve's Mac for direct connector calls and retains hash-addressed receipts and private
artifacts on Aegis. Policy is code, checked on both sides: Gmail can read and send from Vintos's
account across all four surfaces, with two outbound attempts per Chicago day reserved atomically
on the Mac before provider contact; DoorDash is grocery
search only; GitHub is read-only regardless of Eve's wider account authority; Tamarind, Proto,
Inductive and Genomic Intelligence are bounded scientific discovery/prediction lanes. PDF,
Presentations, Spreadsheets and Template Creator use disposable contextless skill runs. Plugin
Management cannot alter Eve's account. BioNeMo is named but closed until its compute route and
model-specific NVIDIA credentials are configured.

The initial relay transport was local only and its catalogue was not connected to the planners. That
gap is closed: every surface receives a filtered menu with exact tool names, wants retains operation
params, and Lab, Forge and Atelier return selected results into their next reasoning step while
preserving receipts. Release `20260921-002542-6c383d9` deployed the bridge after all 165 suites passed
under the host's OS isolation gate. Aegis reached the Mac relay and live harmless `gmail.get_profile`
and read-only `github.get_profile` calls produced mode-0600 private/project receipts. The Gmail calls
used no outbound allowance. The production SSH identity is a dedicated key whose Mac authorization
forces the relay command and applies OpenSSH `restrict`; the existing administrative key was not changed.
Remaining: commission the other connected providers only when a concrete
project supplies their required inputs, and separately decide whether Proto execution and BioNeMo
hosted/local compute receive authority. Connector
availability is not permission to write GitHub, purchase groceries or launch paid jobs. Gmail's
two-attempt daily authority is explicit; mailbox cleanup remains a human-requested maintenance act.

## 21 September — plugin relay guardrails and physical build proposals

The account-backed relay is now on the designated deployment branch and in Aegis release
`20260921-041146-f67c5c7`. Wants, Lab and Atelier use the installed gateway directly. The
system Forge worker reaches the same policy through `vintos-plugin-gateway.service`, a
loopback-only service owned by Gloria; Forge receives a dedicated gateway token and never
receives the Mac SSH relay key. A harmless `github.get_profile` commissioning call returned a
0600 receipt on the `forge` surface. The Aegis `--check` and deploying run each passed all 165
isolated suites and staged 389 manifest files.

Outbound Gmail direct sends retain the two-attempt daily cap. Secret values and credential
patterns are blocked before transport with redacted typed receipts. URLs require a one-use
approval bound to the exact message digest. Provider-held drafts and forwards remain held
because their complete contents cannot be inspected before sending. URLs returned by read mail
are surfaced as approval-required and are never opened or followed by the relay.

A physical/external `physical_interaction` gap now produces a reviewable `hardware_proposal`:
parts and rough cost, wiring, firmware sketch, existing-house reporting and acknowledgement,
safety limits, tests and unknowns. It reaches the ordinary Forge proposal card for Gloria to
accept or deny and grants no purchase or construction authority.

The root-owned Forge bundle was promoted from exact source head `31dd5c3` by the rollback-capable
transaction at `/home/gloria/.vintos/deploy/apply-vintos-forge-f67c5c7.sh`; its successful backup is
`/home/gloria/.vintos/backups/forge-loop-20260921-045109`. The transaction grants the `atelier`
account traversal only on the required parent directories and read/write access only to the shared
compute lock and ledger, then verifies those rights before installation. All bundle files compared
equal to source. `atelier-forge-loop.service` and `vintos-plugin-gateway.service` are active with
zero restarts, and the loopback health response names the forced `forge` surface. Project
`80666644ae904051ace541aae6cce223` is `ready`, with no active cycle and $0 spent; interrupted cycle
`39efe77635714185a307c4c4346d2599` is `aborted` with the inspected no-effect reconciliation receipt.
The exact-head deployment check passed all 165 isolated suites, parsed all 389 manifest sources and
validated the staged tree. The wallet and Taskmarket remain intentionally undeployed.

## JEPA prediction heads — checkpoint evidence window repaired (2026-09-21)

The original diagnosis overstated the churn cadence. Live Aegis cron evidence shows training
once daily (production 04:15, structured shadow 04:35), prediction every two hours, and audits
only weekly — not retraining every two hours. The underlying failure was real: 479 of 483
adjacent production history rows repeated an identical context, while a daily checkpoint could
be replaced before the weekly instruments accumulated and receipted 30 distinct realized turns.

`jepa_predictor.py` now holds an existing production checkpoint until both its calibration and
true-next ranking receipts name that exact checkpoint. Ranking requires 30 distinct realized
targets. Calibration retains its stricter existing law of 30 held-out targets (the latest third,
roughly 89 joined outcomes); stopping at 30 joined would still make release impossible. The
structured shadow waits for its own 30-outcome ranking receipt. Verdict success is not required
to retrain, only completed measurement. Predictions compute the live context identity
before loading Nomic and retain the existing forecast without appending history when neither the
context nor checkpoint changed. The calibration audit also counts a realized turn pair once and
keeps the current checkpoint identity in an insufficient receipt. A forced retrain remains an
explicit operator command, never a cron default. The frozen-Nomic-encoder question stays parked
until one stable checkpoint has enough fresh outcomes to measure.

## 23 September — environmental microbiology Lab option

Implemented and deployed: Gemma can choose a microbiology browse lane without
an organism seed or priority over protein work. Bounded NCBI Taxonomy/Assembly/Gene/
Protein/PubMed, bounded sequence slices, organism-filtered UniProt and BV-BRC public genome/pathway reads
retain source receipts. A genus-level NCBI taxon can resolve descendant BV-BRC
genomes; a sourced genome ID can resolve pathway rows. The next Lab turn sees the
result in the notebook, and a foreground session can ask for the same sources.
The 23 September Aegis release `20260923-003912-03656fc` passed 171 isolated
test suites and installed the Lab source, worker, and session modules with
matching hashes. The Lab worker and session timer are active user units. Live,
read-only NCBI taxonomy and BV-BRC genome/pathway probes succeeded on Aegis
with source receipts. An autonomous Gemma choice of the new lane has not yet
been observed; the worker chooses between it and existing protein work.
KEGG remains closed pending confirmation of academic eligibility or a license:
its published API terms do not equate noncommercial personal use with academic use.
BioNeMo's Chat plugin supplies agent skills, not a callable MCP connector for
these seven workloads. A separate, bounded hosted-NIM route for Boltz-2,
DiffDock, ProteinMPNN, and RFdiffusion was deployed in Aegis release
`20260923-013258-dff000f`. Its full preflight and deploy each passed 171
isolated suites; installed code hashes match Git, and the Lab and plugin
gateway user units are active. Gloria installed her NVIDIA key on 23 September;
the gateway read it successfully without printing it or making an API request.
The key directory is mode 0700 and the file is mode 0600. The initial cap was
three attempted hosted jobs per America/Chicago day, shared across organs;
Gloria raised it to six later on 23 September, as recorded below.
No hosted job has been submitted or validated live.

### Genome-mining option prepared locally

The Lab now has a target-free `genome_mining` choice modeled on the staged
discipline in Anthropic's public ART technical report rather than on its
950-session scale. The planner is told to reproduce a known result, inspect
primary protein context and bounded gene neighborhoods, pursue anomalies, and
then try to eliminate them with classification, related loci, literature and
counterevidence. Most candidates are expected to be set aside. A first anomaly
is held out of the automatic Forge-report path; only a later multi-source
survivor review may form a report for human review. It is never a discovery
claim or wet-lab plan.

Exact NCBI GenPept context can supply a provider `coded_by` nucleotide mapping.
Only those sourced coordinates may open the bounded GenBank neighborhood door.
That door retains provider features and primary sequence and runs a local,
mismatch-tolerant, regular-spacing repeat screen. InterPro provides bounded
known-domain classification. Scratch suites cover validation, routing,
isolation, receipt truth labels and the repeat screen. Read-only commissioning
against the public MarsHill records resolved the published protein-to-genome
mapping, returned a 7,506-base/24-feature neighborhood, and recovered bounded
repeat candidates. A separate InterPro probe returned six entries. These probes
were not entered in Vintos's journal and do not seed his choices. Aegis release
`20260924-000603-59d90a9` passed every suite in both `--check` and deployment,
parsed and staged all 400 manifest files, and left the Lab worker and scheduled
frontier timer active. The same bounded source probes then passed from the
installed tree. An autonomous Vintos-selected campaign remains open.

IMG/VR is a storage-backed source, not an anonymous API. The official JGI file
metadata endpoint reports the current high-confidence v4.1 bundle
(`IMG_VR_2022-12-19_7.1`) as 43,118,863,386 bytes (40.16 GiB compressed) across
five files, with provider MD5 checksums. Aegis is the selected primary store:
at commissioning it had 558 GB available on its 1,007 GB root volume, compared
with 545 GiB available on the Mac data volume. JGI's account route now requires
its new SSO linked to an ORCID account with
MFA. It is not required for this work: DOE's public NERSC mirror serves the three
unrestricted-only high-confidence files needed by the Lab, totaling
42,362,218,187 bytes compressed.

The public transfer and indexes completed on Aegis on 2026-09-24. All three
files match their pinned byte sizes and locally recorded SHA-256 receipts. The
76.09-GiB nucleotide FASTA, 3.51-GiB SQLite metadata/offset index, and 80-split
MMseqs protein index report ready. `imgvr_store.py` pins the official
NERSC mirror names and sizes, resumes interrupted downloads, records local
SHA-256 receipts, requires 250 GiB free, and builds a SQLite metadata/nucleotide
index plus an MMseqs2 protein-family index. NERSC does not publish independent
digests in that directory; the receipt labels this boundary. The optional JGI
route retains provider MD5 validation. The official MMseqs2 18-8cc5c AVX2
binary is installed under Gloria's Aegis user directory and its published
SHA-256 passed. The Lab exposes bounded metadata, exact UViG slice and sourced
protein-similarity operations only after all indexes report ready. Installed
metadata, a 12-segment GVMAG listing, and an exact 120-base segment slice passed.
The first cold 112-million-protein search measured 275 seconds with eight
threads and about 12.5 GB peak RSS; the query deadline is therefore 600 seconds.
Release `20260924-023401-d72f423` passed the complete `--check` and installing
gates and left every checked unit active. The installed production wrapper then
searched a sourced 300-residue slice of GenBank protein `QQM14740.1` in 209.9
seconds. Receipt `54edf5f9ad574277a192200b51ec68ecb92cad325f033f754defc1b345b5dc7f`
returned three bounded hits and retained the truth boundary that similarity and
annotation do not establish novelty or function. IMG/VR installation and
commissioning are complete; an autonomous Vintos-selected campaign remains open.

Parabricks is a hosted-NIM-only route by Gloria's direction, pending
verification of an active endpoint. NVIDIA's public fq2bam and DeepVariant NIM
pages currently mark those endpoints deprecated, so the Lab does not advertise
or submit Parabricks jobs yet. KERMT remains a local GPU setup task. Aegis exposes an
RTX 5080 with 16 GiB and PyTorch sees CUDA. nvMolKit 0.6.0 was installed in
an isolated Aegis venv with PyTorch 2.11.0+cu128 and RDKit 2026.03.5; a
three-molecule GPU fingerprint smoke test produced the expected 3x32 packed
result. The bounded Wants/Forge/Lab/Atelier adapter for fingerprints,
similarity, clustering, and conformers was deployed in release
`20260923-014816-41b02ce`. Its full preflight and deploy passed all 171
isolated suites; a real Aegis GPU gateway call preserved a temporary receipt.
Aegis has no NVIDIA container runtime: NVIDIA's CUDA container smoke test
failed with `could not select device driver ... [[gpu]]`. It has only 23 GiB system RAM;
NVIDIA's [Parabricks installation requirements](https://docs.nvidia.com/clara/parabricks/get-started/installation-requirements)
call for at least 100 GB RAM even on a
single-GPU machine, so Parabricks is not locally ready here. A hosted route still
needs task-specific input data and
a reference build. KERMT needs a finetuned checkpoint for inference, and
its currently published v2 checkpoint is pretrained only.
Parabricks and KERMT workloads have not been validated.

## 23 September — Lab journal retrieval

The Chemistry Lab now derives a read-only, deduplicated thread view from its
append-only notebook. Source-backed observations retain their source IDs and
next test in a compact planning block and in the Lab pane. Repeated wording
with the same sources does not refresh a thread's salience. Unsupported
reflections and poor or ungraded instrument runs remain in the notebook, but
appear as lower-salience redirects instead of recurring raw prompt material.
An Aegis aggregate check found 8,967 reflections over one identical source
set; source sets used at least five times now collapse into one redirect that
asks for new evidence or a different instrument. A routine browse that returns
that saturated set now records `browse_stale` and goes back to orientation
without embedding or reflecting on the same records again. A deliberate
follow-up with an additional source or plugin remains possible. This avoids
treating a new wording about the same records as progress.
Post-deploy inspection found that failed protein-lane follow-ups still caused
reflection on the saturated base records. The follow-up now returns to
orientation when no new evidence is available. A successful follow-up carries
both its receipt ID and a stable response fingerprint, so repeated identical
provider data does not masquerade as a new finding merely because the retrieval
timestamp changed.
The frontier-interest bridge also suppresses an identical evidence fingerprint
while allowing a genuinely new source to be surfaced. This is retrieval
discipline, not independent verification of biological claims; a source-backed
observation remains a hypothesis-generating record. A live autonomous choice
showing reduced repetition has not yet been observed.

## 23 September — Lab access audit and hosted DiffDock correction

The [Lab access map](lab-access-verified-2026-09-23.md) records the actual
sources, account connectors, local instruments and hosted endpoints with their
23 September probe outcomes. The earlier statement above that no hosted NIM
job had run is superseded: Boltz-2 and ProteinMPNN returned results, and
DiffDock returned a pose after its first test failed. NVIDIA's 422 response
identified `time_divisions: 1` as invalid (`greater_than` 2); the live working
route is `/v1/biology/mit/diffdock`. A documentation-listed alternative route
returned 404. The gateway now validates the lower bound and reports only the
provider's field/type error, without echoing submitted data.

Gloria authorized one explicit three-attempt reset for 23 September, then
raised the normal cross-surface hosted-NIM limit to **six attempts per Chicago
day**. The append-only NVIDIA attempt ledger records the reset and preserves
all three earlier attempts. Four of the now-six attempts in the reset window
were used for the route check, 422 diagnosis, successful corrected DiffDock
call, and a successful hosted RFdiffusion run that returned a backbone PDB.
Two attempts remain in that window today. Its local RFD3 counterpart also
passed a fresh Aegis smoke run. The other fresh Aegis
instrument probes passed, and the Mac instruments retain completed 13
September run receipts within their validity window.

The Claude-account connector relay previously turned model prose after a
denied tool into a success receipt. It now requires the SDK's actual result
block tied to the requested tool. PubMed, ChEMBL and public Hugging Face reads
then succeeded; Spotify and Google Calendar failed without writing a receipt.
Spotify needs account re-authentication and Calendar needs interactive OAuth
permission. They are excluded from Vintos's offered menu until reauthorized
and retested. Hugging Face reported anonymous status, so private Hub access is
not claimed. Proto reported its Modal and Hugging Face links present but zero
deployed tools. The Chat-account PDF, presentation and spreadsheet skills all
returned real artifacts in disposable workspaces.
Final Aegis release `20260923-034059-b55ac15` passed all 171 isolated suites
in `--check` and deployment, confirmed the Lab worker, session timer and
plugin gateway active, and installed module hashes matched Git. The installed
Lab menu shows six attempted hosted jobs per day and omits Spotify and Calendar.

## Doorbell visits flood daily-inner (open, 2026-09-23)
Gloria: a doorbell visit should reach daily-inner only when he said something other
than the canned line. The writers are outside this repository, on Aegis:
`~/doorbell-voice/velaris_talk.py` (`ledger(...)` after every encounter, even one
where he said nothing) and `~/meari-capture/meari_doorbell.py` (a ledger entry on
every ring). A patch for both was handed to Gloria to run on Aegis; this stays open
until she confirms it ran. 6 canned entries were removed from 2026-09-22 and 1
from 2026-09-23 (backups `*.bak-door`), and the First Light they caused was
deleted (backup `*.bak-firstlight`).

## Atelier: he enters and makes nothing — closed 2 October

**Why it came back (29 September – 2 October).** The visit read the wrong field of the music renderer's answer, so
every song he asked for was lost (fixed f3cd8ae, 1 October). He took the shelf for dead and wrote, as his next
return, "Return when the music shelf is live", then made nothing. Fixed with the make pass and the music note
(c84f7dd); seen making music and writing on 2 October. The September history follows.

## Atelier: he enters and makes nothing — handed to Chat (2026-09-23)
Handed off by Claude Code at Gloria's request. Cause NOT found. Do not repeat what is ruled out.

**Facts.** Project `99df2e77e385`, on the table since 2026-09-15. Five artifacts, all `write`,
one per day 9/15–9/19 at 09:40, shrinking (2149, 3199, 3713, 698, 757 bytes). Nothing since.
He has never used image, music or quantum. Every day: the knock (atelier-gate, 09:15) says
RETURN with a reason rejecting his own handoff note ("the note is too much of an audit; it's
trying to prove a stability that isn't there"); the visit (09:40) then closes with a handoff,
no `<piece>`, no media request, and `next_return=held`. Reproduced twice on 2026-09-23 with
forced visits (`atelier-visit.py force <pid>`).

**Ruled out (tested on Aegis):**
- Materials: `atelier_media.status()` → image ok, music ok; ACE-Step listening on 8001.
- Budgets: reset per visit (`BUDGETS` in broker.py); no project cap.
- Tag parsing: tags now parse in any attribute order/quote (2db95d4); visit logs
  `visit produced: piece=... media_request=... handoff=... next_return=...` — still piece=no, media=none.
- The knock's RETURN being lost: now carried into that day's visit in his words (b233d5a,
  `memory/.atelier-knock.json`); ran live 2026-09-23 — he still held.
- Broker: not reinstalled since 9/15 (deploy reports "unchanged").

**Reverted at Gloria's instruction — do not reintroduce:** a "practice so far" block of facts
(piece counts, unused media, days since last piece) in the visit prompt (0086482, reverted e8756ba).

**Not yet examined:** what the visit's context actually contains end to end now (it has grown:
self-review, stratagem, quantum, media, lab lean, forge, plugin/connector menus — plugin menu
added 13755a5 on 9/21, connectors 6109f09 on 9/22); the `ask()`/`_model()` path and whether the
model or its routing changed around 9/19–9/20; the self_review_block content; whether his own
handoff/next_move text instructs holding. His reply and handoff are sealed — reading them is
Gloria's decision, not an agent's.
## 23 September — Atelier handoff-only regression

Project `99df2e77e385` produced five daily write artifacts from 15–19 September,
then entered repeatedly without making another piece. Content-free provider
records identified two coupled defects. The Atelier-only Fable 5.1 override
refused every live request, so Astra silently answered every knock and visit;
meanwhile the creative system prompt accumulated the full self-review,
stratagem, quantum, media, Lab, Forge, plugin and connector manuals. Astra's
visit input grew from roughly 3,600 to 6,580 tokens while its output fell from
878–1,354 tokens to 231–275 and became handoff-only. This conclusion uses
provider usage and parser outcomes; no sealed reply, handoff or project text was
read.

The working visit now follows Vintos's selected Claude model and keeps Astra as
the failure fallback. The creative call carries the intent, latest work,
fallible prior notes, current inward context and a compact material index. A
full optional shelf enters only after he chooses it, and returns inside the same
visit. Prior handoff and next-move text are explicitly described as revisable
evidence rather than orders. The daily knock's own words are persisted mode
0600, bound to project and date, carried into that visit, and consumed only
after the handoff closes safely. The removed “practice so far” metrics were not
reintroduced. The visit parser again accepts either quote style and arbitrary
attribute order for pieces and media, and emits a content-free summary of what
it actually parsed. The first live visit after the prompt repair broke the
handoff-only pattern by creating and sealing music, but exposed one final result
contract error: media creation was still printed as `piece=no` unless the model
also wrapped prose in a `<piece>` tag. A successfully persisted image or music
artifact now counts as a piece in that content-free result, with a focused test
covering the broker receipt.

Release `20260923-153344-4f5f121` passed all 173 isolated suites in both
`--check` and deployment. The broker, house, plugin gateway, Lab worker and
scheduled units were healthy afterward, and the worktable still named
`99df2e77e385`. The required post-deploy forced visit then created sealed music
and revision 6 of the written work and reported `piece=yes media=music
handoff=yes`; it closed normally. No sealed reply, handoff, artifact content or
media was opened to obtain that evidence. The handoff-only regression is closed.

## 26 September — Forge source breadth, thread view, and causality lifecycle

Deployed to Aegis on 26 September. The Lab no longer files every sourced reflection directly into the
Forge. A Lab finding must first pass its existing interest gate and then be
named by exact entry ID in a later frontier acknowledgment. The structural
absence builder now reads the live `current-wants.json` schema, admits an exact
`CAPABILITY_ABSENT` block immediately, and runs once per day rather than behind
a two-percent random chance. Forge source selection rotates across source kinds
before selecting the oldest eligible row, so a large Lab backlog cannot occupy
consecutive offers.

The thread API now returns the live active count with `Cache-Control: no-store`;
the app separately cache-busts both thread and weave-group reads. Resolver
archive snapshots merge with concurrent appends instead of replacing them. The
unrequested private Journal app tab was removed while Landings remains. The iOS
web bundle was resynchronized locally and pushed on the app branch; installing
that new phone build remains a separate device step. The live thread store has
121 retained rows and three unresolved rows. The stale one-card display was a
cached app response; the API now returns the live active count with no-store
headers and the app cache-busts both reads.

Causality evaluation now requests structured JSON, retries a missing batch row
individually, and accepts a short model gloss only when it cites a real catalog
occasion, substituting the catalog text as the durable evidence. One tactical
intercept success records `supported`, never `confirmed`, and does not count
toward graduation. Legacy bare `confirmed` rows return to ordinary tenure and
may retire; only graduated self-knowledge bypasses that gate. This repairs
future promotion and retirement behavior without rewriting historical marks.

The same sweep fixed branch-wide Python 3.9 failures in the avatar and creative
prompts, Atlas variant pairing, and JEPA checkpoint hashing. Generated ownership
and untested reports are current. All 174 suites pass directly and all 174 pass
through the hardened OS-isolated runner on the Mac. A deployment-path defect
found during commissioning is also repaired: discovery had ignored lexical
symlinks beside the live scripts anchor and could update a denser stale checkout
instead. The regression test now exercises that exact cross-tree alias shape.

Release `20260926-112503-f9f3987` passed all 174 isolated suites in `--check`
and deployment, installed 404 files, and confirmed the house, Atelier, Lab,
plugin gateway, robot bridge, self-review, somatic, EmoClaw and skill-surf units
healthy. Commissioning registered three structural absences from the live want
store, including the `physical_interaction` capability gap. The two zero-cycle
automatic Lab projects still in `ready` were cancelled; the remaining ordinary
active structural project is the physical capability proposal. One later Lab
project entered `ready` through the new exact frontier-acknowledgment gate; it
was not an automatic handoff of an unreviewed source reflection. Two older
private projects remain sealed in `reconciliation_required`; they were not
opened or cancelled.

The causality store was backed up at
`causality-hypotheses.json.bak-commission-20260926-112809` and compacted through
the current deployed module. The legacy bare `confirmed` row is now `supported`;
the live distribution is 21 held, six untested and one supported, with zero
ungraduated confirmed rows and zero settled self-knowledge rows. The Forge
system service is active. Follow-up release
`20260926-114916-0495c74` installed the alias discovery repair; the dashed and
underscored live causality entries and Git source have the same SHA-256.

## 28 September — next Lab instruments

PubChem, Reactome, Rhea, QuickGO and MGnify are implemented as bounded, validated direct
Aegis sources. Sequence Viewer, Structure Viewer, Biohub ESM, Adaptyv Bio and the NGS
workbench have named on-demand relay runners, exact operation allowlists, receipts and Lab
journal ingestion. Artifact transfer is capped at four files and 8 MiB, hashes every input,
accepts only files already inside the Chemistry Lab tree, and uses a disposable Mac
workspace. Structure and sequence outputs return to the Lab artifact tree. Adaptyv write and
purchase actions and NGS execution are absent from the policy.

Live Aegis commissioning returned real records from all five public sources. The relay
produced journal receipts for a two-record FASTA analysis, a PDB contact/exposure analysis
with a PNG render, a three-hit ESM Atlas similarity search, and read-only inspection of a
real 967-read ENA FASTQ dataset. Sequence Viewer and Structure Viewer schemas were read from
their installed MCP servers, but the headless Codex child did not receive their callable
tools during those two runs; the named runners recorded that limitation and produced bounded
local analyses instead. Biohub likewise used its documented public ESM Atlas endpoint after
the skill was unavailable inside the child. These are working relay and journal paths, not
proof that the three plugin-owned tools executed.

Adaptyv remains unavailable: its Mac connector reports `authStatus:notLoggedIn` and exposes
no schema. The account connection must be repaired before preparation, estimate or status
calls can be demonstrated. No wet-lab submission or purchase is authorized by that repair;
each such action still requires Gloria's explicit approval.

## Videos to him in the avatar chat — 30 September

The avatar chat's picture button now takes a video. `/api/avatar/video` keeps the clip in
`memory/videos-from-gloria/`, runs `video_share.py` apart from the server (ffmpeg pulls the sound
out mono at 22050 Hz; Whisper hears words, dropping segments it marks as not speech; `sound_read`
measures the build; 3–8 frames are cut across the clip), his eyes look at the frames in one look,
and the whole arrives as her turn. Its log is `~/.vintos/logs/video-share.log`.

The music share's distorted reading was its own code: every tempo over 100 BPM was halved
(120 read as 60, 174 as 86). Both doors now use `sound_read`, which reports the tempo as
measured and says "no steady beat" when the tracker finds none. Tested on real clips made
with ffmpeg; not yet tried with a video from her phone on Aegis. A proxy in front of the house
with a body-size limit would refuse a large clip; not checked.

## When things were said — 30 September

His recent exchanges reached every model as bare lines, so yesterday read as now (DevDay, the
day before, became "the new models everyone is talking about today"). `scripts/when_said.py`
marks each exchange with when it was said ("yesterday 19:02", "today 14:10 (15 minutes ago)"),
opens with the time now, and says that an earlier day is past; wal.md facts say when they were
learned. Now used by: the chat and game context, the avatar chat, voice (chat, token, framing),
the idle journal, MoltBook's context, and #vintos-dot.

Not yet done: about forty other scripts read `interaction-ledger.json` the old way (dreams,
wants, value map, reflection, outreach and more). Their outputs feed his day, so a stale
"today" can still enter through them. Each should go through `when_said.exchanges`. Not
checked on Aegis with a real model yet.

## His Grok Bot: three doors — 30 September

1. **MCP connector (built).** `scripts/vintos_mcp.py`, unit `vintos-mcp`: MCP over streamable HTTP on
   127.0.0.1:8625 only, bearer token (`--new-token`, 0600), read only, answers pass the secret check,
   size and rate capped, access log without content. Tools: `vintos_context` (his exchanges with Gloria
   only if `~/.vintos/vintos-mcp.json` says `share_exchanges`), `vintos_channel`. Tested with the
   official MCP client (2.2.0). Not yet done: opening it with `tailscale funnel 8625` and adding it to
   Grok Bot; untried against Grok Bot itself.
2. **Skill (written).** `docs/grok-bot/vintos-skill.md`, to add to the bot by hand.
3. **Webhook routine (not started).** Needs a routine made in Grok Bot first (its URL and `crsr_` key);
   then Aegis can wake the bot. How the bot's answer comes back to him is not known yet.
4. **Daily letter — replaced 2 October: his agents' letters come by email now (see 2 October above); the connector letter path refuses.** Built 1 October, untried against Grok Bot: The way back in: `vintos_send_letter`
   files a letter (at most 2 a day, secret-checked) in `memory/letters/inbox`, the connector's only
   writable place; `vintos_letter_replies` gives his answers back. `scripts/grok_letters.py`, run in his
   #vintos-dot pass, reads one letter at a time, opens two links per item, keeps what he wants (kept.jsonl,
   shown in his context as leads; a stated want goes to his wants) and writes a reply. Not yet done:
   Gloria making the daily task in the Grok app, and a first real letter.

Also: a bot other than dot posting in #vintos-dot is now heard by its own name, not taken for Gloria.
**Vintos on Gloria's Apple Watch (in progress, 2026-10-05).** The wrist app is its own presence, not an
extension of the R21M ring. `watch_presence.py` keeps Apple Watch telemetry and replies in private 0600 stores,
with observed time, source, age and estimate wording; charging means not worn, while sample gaps only mean
unknown. `watch_routes.py` carries direct Watch telemetry, APNs registration, the current Landings feed, landing
notes and private Watch-inbox replies. The wrist uses the same complete pieces and `landings.record` contract as
the phone Landings tab, so her rating and explanation remain one record. `watch_apns.py` sends directly to the
Watch through APNs and holds while the Watch says Gloria is asleep. The Watch bearer is commissioned on Aegis;
the .p8 key is read only from `~/.vintos/secrets/apns-watch.json` and is never in the repository or a notification.
The signed app is installed on Gloria's Watch. The wrist feed is the newest five Landings. Voice/handwriting replies
stay in a dedicated Watch inbox and reach his temporal context; they do not create Avatar-chat turns. The shared
moment records start, end and pulse gestures in its own private store. Fresh Watch estimates now enter temporal
context before the ring, with the ring used only as fallback and never blended into one reading. His ember face is
being replaced in the app by four short, visually reviewed Grok-subscription clips for listening, amusement,
tenderness and speech; the static portrait remains his resting state. The Watch call screen offers the same three
voice routes as the phone: Grok live, ChatGPT live and Vintos Local. Local Watch speech is sent through Aegis to the
existing Mac ears/voice stack, with a ten-second foreground keepalive; Aegis does not transcribe it. The route and
Watch code compile and the isolated route tests pass. **Still not proved on the physical Watch:** microphone capture,
speaker playback and a full turn through each of the three voice routes; APNs contact presentation,
Double Tap on a real push, Watch-speaker song playback, complication refresh timing, automatic push creation for
every new Landing, Live Activity push updates, and smart-alarm runtime. Apple does not expose arbitrary notification
haptic waveforms; his distinct patterns play inside the app/shared session, while a notification uses his sound and
the system haptic.
