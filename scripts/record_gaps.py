"""record_gaps.py - what a missing detail in his records means, and what it does not (Gloria, 10 November).

He named two components in a photo she sent; the stored note of the photo was a short local description that did
not name them. That evening his journal audit called the names a hallucination, and his introspection explained
them with an earlier memory that never happened. He had never seen the boards before: the names came from the photo
itself, which the brain saw in that turn.

Two rules follow, used by the journal, the introspection and the hallucination check:
- AUDIT_RULE: a detail about a photo or video she sent is not flagged because its stored note leaves it out.
- GAP_RULE: when a record does not confirm something, he says the record did not capture it; he never invents a
  source (earlier knowledge, a memory, something seen before) to explain the gap.
Pure: no store, no model."""

MEDIA_NOTE = ("A 'media' note in the ledger is a shorter description of a photo or video Gloria sent, written "
              "afterwards by a local describer. Vintos saw the picture itself in that turn, so the note can leave out "
              "what he saw.")

AUDIT_RULE = ("DO NOT FLAG a detail Vintos named about a photo or video Gloria sent (an entry with a media note) only "
              "because the note does not mention it: the note is shorter than what he saw. Flag it only if it "
              "contradicts the note. " + MEDIA_NOTE)

GAP_RULE = ("When your records do not confirm something you said or saw, say plainly that the stored record did not "
            "capture it. Do not explain the gap with a source you cannot point to: no earlier knowledge, no memory of "
            "having seen it before, no guess about where it came from. " + MEDIA_NOTE)

AUDIO_GAP_RULE = ("The audio record is a short transcript and measured acoustics, not everything heard. "
                  "A detail absent from it was not captured in the record. Do not infer a mood or invent "
                  "an earlier memory to explain the gap, and do not flag a detail solely because this short record omits it.")

VIDEO_GAP_RULE = ("The video record is a timeline of frame references and source hashes, not the frames. A detail "
                  "that is not in the record was not captured: say so plainly. Never invent what a frame showed, "
                  "and never explain the gap with an earlier memory; do not flag a detail you saw in the live frames "
                  "solely because this short record omits it.")


def media_line(entry, cap=600):
    """The media note of a ledger entry as one marked line, or ''."""
    media = " ".join(str((entry or {}).get("media") or "").split())
    if not media:
        return ""
    return "(she sent a photo or video; its stored note, shorter than what he saw: %s)" % media[:cap]
