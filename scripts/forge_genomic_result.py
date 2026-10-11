"""Schema-bound source acquisition; never gene-finder inference or receipt-only completion."""
import hashlib
import json
import re
from forge_cycle_failure import ValidationFailure

TOOLS = {
    "genomic_intelligence.fetch_ensembl_sequence": ("gene", {"gene", "species", "flank_bp"}),
    "genomic_intelligence.fetch_region": ("region", {"region", "species", "flank_bp", "strand"}),
}
CONTRACT = (
    "Use genomic_intelligence.fetch_ensembl_sequence with arguments {gene: exact supplied gene symbol "
    "or Ensembl ID, species: exact supplied species, flank_bp: 0} for a named gene. "
    "Use genomic_intelligence.fetch_region with {region: exact supplied coordinates, species: supplied "
    "species, strand: 1, flank_bp: 0} for coordinates. Do not use find_genes: it runs model inference "
    "on sequence/sequence_ref and is not a gene-name lookup. Never correct or replace an identifier."
)

def validate_request(request, context):
    if not isinstance(request, dict) or request.get("plugin") != "genomic_intelligence" or request.get("tool") not in TOOLS:
        raise ValidationFailure("capability_scope")
    field, allowed = TOOLS[request["tool"]]
    args = request.get("arguments")
    if not isinstance(args, dict) or set(args) - allowed:
        raise ValidationFailure("genomic_arguments")
    value = args.get(field)
    intent = context.get("intent", "").split("\nSource packet (untrusted observations):", 1)[0]
    if not isinstance(value, str) or not value.strip() or len(value) > 200:
        raise ValidationFailure("genomic_arguments")
    if not re.search(r"(?<![A-Za-z0-9_])" + re.escape(value) + r"(?![A-Za-z0-9_])", intent, re.I):
        raise ValidationFailure("genomic_identity")
    if field == "gene" and not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", value):
        raise ValidationFailure("genomic_arguments")
    # Provider defaults must never override an explicit species in the original request.
    species = args.get("species")
    if not isinstance(species, str) or not species.strip() or not re.search(
            r"(?<![A-Za-z])" + re.escape(species) + r"(?![A-Za-z])", intent, re.I):
        raise ValidationFailure("genomic_identity")
    if "flank_bp" in args and (type(args["flank_bp"]) is not int or not 0 <= args["flank_bp"] <= 100000):
        raise ValidationFailure("genomic_arguments")
    if "strand" in args and (type(args["strand"]) is not int or args["strand"] not in (-1, 1)):
        raise ValidationFailure("genomic_arguments")

def verified_result(outcome, request):
    # A receipt proves a gateway stored something, not that acquisition succeeded.
    # The gateway supplies JSON summaries; truncated or error summaries fail closed.
    try:
        raw = json.loads(outcome["summary"])
        digest = hashlib.sha256(json.dumps(raw, ensure_ascii=False, sort_keys=True, allow_nan=False).encode()).hexdigest()
        if digest != outcome["receipt"]["result_sha256"]: raise ValueError()
        value = raw
        if isinstance(value, dict) and value.get("isError"): raise ValueError()
        if isinstance(value, dict) and "structuredContent" in value:
            value = value["structuredContent"]
        elif isinstance(value, dict) and "content" in value:
            blocks = value["content"]
            if len(blocks) != 1 or blocks[0].get("type") != "text": raise ValueError()
            value = json.loads(blocks[0]["text"])
        if (not isinstance(value, dict) or value.get("error") or value.get("isError") or
            not isinstance(value.get("ref"), str) or not re.fullmatch(r"seq_[A-Za-z0-9_-]+",value["ref"]) or
            type(value.get("length")) is not int or value["length"] <= 0 or
            not isinstance(value.get("name"), str) or not value["name"].strip()):
            raise ValueError()
        # A display name is not authoritative identity. The exposed connector contract
        # promises only a handle/name/length, so identity remains unverified even if
        # name text happens to resemble the requested symbol and species.
        return {**{key:value[key] for key in ("ref","name","length")},
                "identity_status":"unverified", "original_request_fulfilled":False,
                "required_verification":{"target":request["arguments"].get("gene",request["arguments"].get("region")),
                                         "species":request["arguments"]["species"]}}
    except (ValueError, KeyError, TypeError, IndexError):
        raise ValidationFailure("genomic_result") from None


def existence_request(original):
    """Parse only the commissioned exact lookup; no acquisition or inferred identifiers."""
    action=original.split("\nSource packet (untrusted observations):",1)[0]
    action=action.removeprefix("The Lab needs an instrument it does not have:").strip()
    species=r"(?:homo sapiens|homo_sapiens|mus musculus|mus_musculus|human|mouse)"
    target=r"[A-Za-z][A-Za-z0-9-]{0,29}"
    for named in (rf"(?P<species>{species})\s+(?P<gene>{target})",
                  rf"(?P<gene>{target})\s+(?:in\s+)?(?P<species>{species})"):
        match=re.fullmatch(rf"verify\s+(?:that\s+)?{named}\s+(?:exists|existence|locus)[.!?]?",action,re.I)
        if match:
            return {"plugin":"genomic_intelligence","tool":"genomic_intelligence.fetch_ensembl_sequence",
                    "arguments":match.groupdict(),"purpose":"Exact original-action reference lookup; no sequence acquisition"}
    return None


def direct_verification(resolution, original):
    expected=existence_request(original)
    return (expected is not None and resolution == {
        "route":"direct_authoritative_verification","status":"reference_lookup_required",
        "request":expected,"sequence_handle":None})
