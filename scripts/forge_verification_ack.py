"""Read-only canonical Lab evidence resolver. No provider calls, credentials or filesystem grants."""
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from forge_loop import Refused
from forge_lab_handback import ownership

MAX_FILE = 4 * 1024 * 1024
MAX_RECEIPTS = 8 * 1024 * 1024
HEX = re.compile(r"[a-f0-9]{64}")
ID = re.compile(r"[a-f0-9]{32}")
SPECIES = {"human":9606, "homo sapiens":9606, "homo_sapiens":9606,
           "mouse":10090, "mus musculus":10090, "mus_musculus":10090}
FIELDS = {"project_id","cycle_id","ownership_sha256","original_request_sha256",
          "evidence_receipt_ids","verdict"}


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,allow_nan=False).encode()).hexdigest()


def request_digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def envelope(body):
    if not isinstance(body,dict) or set(body) != FIELDS:
        raise Refused("exact verification acknowledgement envelope required")
    if any(not isinstance(body[k],str) or not ID.fullmatch(body[k]) for k in ("project_id","cycle_id")):
        raise Refused("verification project and cycle required")
    if any(not isinstance(body[k],str) or not HEX.fullmatch(body[k]) for k in ("ownership_sha256","original_request_sha256")):
        raise Refused("verification ownership and request digests required")
    ids = body["evidence_receipt_ids"]
    if (not isinstance(ids,list) or not 1 <= len(ids) <= 8 or
        not all(isinstance(value,str) and HEX.fullmatch(value) for value in ids) or len(set(ids)) != len(ids)):
        raise Refused("bounded verification receipt identifiers required")
    if body["verdict"] not in ("verified_present","verified_absent"):
        raise Refused("partial or identity-only acquisition cannot fulfill the request")
    return body


def validate_evidence(body, row, current, receipts):
    """Validate canonical ownership and the deterministic public-reference evidence contract."""
    envelope(body)
    if (row.get("project_id") != body["project_id"] or row.get("cycle_id") != body["cycle_id"] or
        row.get("ownership_sha256") != body["ownership_sha256"] or
        ownership(current) != body["ownership_sha256"] or current.get("state") != "accepted" or
        current.get("project_id") != body["project_id"] or
        str(current.get("question",""))[:2000] != row.get("original_request") or
        request_digest(row["original_request"]) != body["original_request_sha256"]):
        raise Refused("verification ownership is stale")
    verification = row.get("verification") or {}
    if (verification.get("state") != body["verdict"] or
        verification.get("ownership_sha256") != body["ownership_sha256"] or
        verification.get("original_request_fulfilled") is not True or
        sorted(verification.get("evidence_receipt_ids",[])) != sorted(body["evidence_receipt_ids"])):
        raise Refused("canonical verification is incomplete or mismatched")
    artifact = row.get("artifact") or {}
    handback = artifact.get("lab_handback") or {}
    accepted = row.get("accepted_receipt") or {}
    if (handback.get("cycle_id") != body["cycle_id"] or
        handback.get("original_request") != row["original_request"] or
        accepted.get("cycle_id") != body["cycle_id"] or type(accepted.get("charged_cents")) is not int or
        accepted["charged_cents"] != 0):
        raise Refused("verification is not bound to the accepted handback")
    query = artifact.get("capability_resolution",{}).get("request",{})
    args = query.get("arguments",{})
    target, species = args.get("gene"), args.get("species")
    taxon = SPECIES.get(species.lower()) if isinstance(species,str) else None
    if (query.get("plugin") != "genomic_intelligence" or
        query.get("tool") != "genomic_intelligence.fetch_ensembl_sequence" or
        not isinstance(target,str) or not target or taxon is None):
        raise Refused("only exact named-gene verification is commissioned")
    original = row["original_request"].split("\nSource packet (untrusted observations):",1)[0]
    commissioned = original.removeprefix("The Lab needs an instrument it does not have:").strip()
    # Exact bounded action: extra clauses such as "and build..." must never be completed by a locus lookup.
    named = rf"(?:{re.escape(species)}\s+{re.escape(target)}|{re.escape(target)}\s+(?:in\s+)?{re.escape(species)})"
    if not re.fullmatch(rf"verify\s+(?:that\s+)?{named}\s+(?:exists|existence|locus)[.!?]?", commissioned, re.I):
        raise Refused("verification does not answer the original requested action")
    expected_query = {key:body[key] for key in ("project_id","cycle_id","ownership_sha256","original_request_sha256")}
    expected_query.update(action="verify_gene_locus",target=target,species=species,taxon_id=taxon)
    normalized_evidence = []
    for rid in body["evidence_receipt_ids"]:
        receipt = receipts.get(rid)
        if not isinstance(receipt,dict) or receipt.get("receipt_id") != rid:
            raise Refused("canonical verification receipt unavailable")
        unsigned = {key:value for key,value in receipt.items() if key != "receipt_id"}
        if digest(unsigned) != rid or digest(receipt.get("records")) != receipt.get("response_sha256"):
            raise Refused("canonical verification receipt integrity mismatch")
        if (receipt.get("source") != "gene_locus_verification" or receipt.get("query") != expected_query):
            raise Refused("verification receipt belongs to a different request")
        data = receipt.get("records")
        if not isinstance(data,dict):
            raise Refused("structured reference verification required")
        if (data.get("action") != "verify_gene_locus" or data.get("requested_target") != target or
            data.get("taxon_id") != taxon or type(data.get("taxon_id")) is not int or
            data.get("query_completed") is not True):
            raise Refused("reference query identity or completion mismatch")
        reference = data.get("reference") or {}
        if (not isinstance(reference,dict) or reference.get("provider") not in ("ensembl","ncbi_gene","hgnc") or
            not isinstance(reference.get("release"),str) or
            not re.fullmatch("[A-Za-z0-9_. -]{1,80}",reference["release"])):
            raise Refused("named authoritative reference and release required")
        matches = data.get("matches")
        if body["verdict"] == "verified_absent":
            if data.get("verdict") != "not_found_in_reference" or matches != []:
                raise Refused("absence requires a completed exact reference lookup")
        else:
            if data.get("verdict") != "present" or not isinstance(matches,list) or len(matches) != 1:
                raise Refused("unambiguous authoritative locus required")
            match = matches[0]
            if (not isinstance(match,dict) or match.get("symbol") != target or
                type(match.get("taxon_id")) is not int or match["taxon_id"] != taxon):
                raise Refused("exact gene symbol and species required")
            if any(not isinstance(match.get(key),str) or not re.fullmatch("[A-Za-z0-9_.:-]{1,100}",match[key])
                   for key in ("gene_id","assembly","chromosome")):
                raise Refused("authoritative gene and assembly identifiers required")
            coordinate = match.get("coordinate_system")
            lower = 0 if coordinate == "0-based-half-open" else 1 if coordinate == "1-based-inclusive" else None
            if (lower is None or type(match.get("start")) is not int or type(match.get("end")) is not int or
                not lower <= match["start"] < match["end"]):
                raise Refused("verified locus coordinates required")
        normalized_evidence.append({"receipt_id":rid,"requested_target":target,"taxon_id":taxon,
            "verdict":data["verdict"],"reference":{"provider":reference["provider"],"release":reference["release"]},
            "matches":[{key:match[key] for key in ("symbol","taxon_id","gene_id","assembly","chromosome",
                       "coordinate_system","start","end")} for match in matches]})
    proof = {**body, "evidence_receipt_ids":sorted(body["evidence_receipt_ids"]),
             "original_request":row["original_request"], "target":target,"species":species,"taxon_id":taxon,
             "artifact_sha256":digest(artifact),"evidence":normalized_evidence}
    proof["proof_sha256"] = digest(proof)
    return proof


class CanonicalLabEvidence:
    """Resolve fixed filenames under an explicitly configured, already-readable Lab root."""
    def __init__(self, root):
        self.root = Path(root)
        if self.root.is_symlink(): raise ValueError("canonical Lab root cannot be a symlink")
        self.root = self.root.resolve()

    def _open(self, name):
        fd = os.open(self.root/name, os.O_RDONLY | os.O_NOFOLLOW)
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != self.root.stat().st_uid or info.st_mode & stat.S_IWOTH):
            os.close(fd)
            raise Refused("canonical evidence file ownership refused")
        return os.fdopen(fd,"rb")

    def _json(self, name):
        with self._open(name) as stream: raw = stream.read(MAX_FILE+1)
        if len(raw) > MAX_FILE: raise Refused("canonical verification store exceeds bound")
        return json.loads(raw)

    @contextmanager
    def resolve(self, body):
        envelope(body)
        try:
            with self._open(".lock") as lock:
                # Keep the shared Lab lock through the Forge commit; never create a lock or wait indefinitely.
                fcntl.flock(lock.fileno(),fcntl.LOCK_SH | fcntl.LOCK_NB)
                rows = self._json("forge-capability-handbacks.json")
                outbox = self._json("forge-report-outbox.json")
                row = rows.get(body["cycle_id"])
                if not isinstance(row,dict): raise Refused("canonical handback unavailable")
                current = outbox.get(row.get("outbox_key"))
                if not isinstance(current,dict): raise Refused("canonical outbox ownership unavailable")
                wanted = set(body["evidence_receipt_ids"]); receipts = {}
                with self._open("source-receipts.jsonl") as stream:
                    size = os.fstat(stream.fileno()).st_size
                    start = max(0,size-MAX_RECEIPTS);stream.seek(start)
                    if start: stream.readline()
                    raw = stream.read(MAX_RECEIPTS+1)
                if len(raw) > MAX_RECEIPTS: raise Refused("verification receipt window exceeds bound")
                for line in raw.splitlines():
                    try: receipt = json.loads(line)
                    except ValueError: continue
                    if isinstance(receipt,dict) and receipt.get("receipt_id") in wanted:
                        prior = receipts.get(receipt["receipt_id"])
                        if prior is not None and prior != receipt:
                            raise Refused("conflicting canonical verification receipts")
                        receipts[receipt["receipt_id"]] = receipt
                yield validate_evidence(body,row,current,receipts)
        except Refused:
            raise
        except (OSError,ValueError,KeyError,TypeError,AttributeError):
            raise Refused("canonical verification evidence unavailable or busy") from None
