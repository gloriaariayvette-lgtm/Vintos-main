"""Content-free cycle checkpoints. Model text and provider exception text never enter diagnostics."""
from contextvars import ContextVar
import hashlib
import json

CURRENT = ContextVar("forge_cycle_trace", default=None)
REASONS = {'capability_already_installed': 'capability already installed',
 'capability_brief_requires_explicit_component_and_acceptance_lists': 'capability brief requires '
                                                                      'explicit component and '
                                                                      'acceptance lists',
 'capability_brief_requires_title_and_limitations': 'capability brief requires title and '
                                                    'limitations',
 'empty_capability_brief': 'empty capability brief',
 'explicit_effect_scope_required': 'explicit effect scope required',
 'explicit_gap_decision_required': 'explicit gap decision required',
 'hardware_cost_invalid': 'hardware cost invalid',
 'hardware_part_is_incomplete': 'hardware part is incomplete',
 'hardware_part_text_required': 'hardware part text required',
 'hardware_proposal_is_incomplete': 'hardware proposal is incomplete',
 'hardware_proposal_must_be_an_object': 'hardware proposal must be an object',
 'hardware_proposal_requires_a_parts_list': 'hardware proposal requires a parts list',
 'hardware_proposal_requires_a_reporting_path': 'hardware proposal requires a reporting path',
 'hardware_proposal_requires_concrete_text': 'hardware proposal requires concrete text',
 'hardware_proposal_requires_explicit_lists': 'hardware proposal requires explicit lists',
 'hardware_quantity_invalid': 'hardware quantity invalid',
 'hardware_total_invalid': 'hardware total invalid',
 'incomplete_assessment': 'incomplete assessment',
 'invalid_capability': 'invalid capability',
 'model_response_too_large': 'model response too large',
 'review_requires_explicit_completion_and_reasons': 'review requires explicit completion and '
                                                    'reasons',
 'unsubstantiated_gap': 'unsubstantiated gap'}
REASONS.update({
 "genomic_arguments": "Genomic source acquisition arguments do not match the declared tool schema.",
 "genomic_identity": "Genomic acquisition must preserve the identifier and species supplied in the request.",
 "genomic_result": "Connector receipt lacks a complete, integrity-matched reference-sequence handle; the request is not fulfilled.",
 "gateway_configuration": "Forge connector URL or protected credential is missing or invalid; repair local configuration before dispatch.",
 "report_sections": "Report is missing required sections.",
 "connector_timeout": "Connector timed out after dispatch; inspect its receipt before retrying.",
 "report_types": "Report title must be nonempty text and sections must be text or lists of text.",
 "invalid_json": "Local model returned invalid JSON.",
 "plugin_shape": "Tool request requires plugin, tool, object arguments and a bounded purpose.",
 "plugin_unavailable": "Requested tool is not enabled for Forge.",
 "plugin_receipt": "Connector did not return a verifiable receipt; inspect the gateway before retrying.",
 "capability_unresolved": "No existing read tool was selected. A concrete implementation and acceptance test are still required.",
 "capability_scope": "Capability verification only permits existing read tools; implementation or consequential work needs its own approved workflow.",
 "unexpected": "Unexpected adapter failure; inspect the named execution phase.",
 "interrupted": "Worker interrupted; inspect the checkpoint before retrying.",
})
class ValidationFailure(ValueError):
    def __init__(self, code, missing=()):
        self.missing = [k for k in missing if k in ("title", "sourced_observations", "hypotheses", "conflicting_evidence", "limitations", "next_tests")]
        self.code = code if code in REASONS else "unexpected"
        super().__init__(REASONS[self.code] + (" Missing: " + ", ".join(self.missing) if self.missing else ""))

class Trace:
    def __init__(self, save, instrumented=False):
        self.save = save
        self.phase = "builder"
        self.external = "none" if instrumented else "unknown"
        self.repair = 0
        self.history = []
    def checkpoint(self, phase, external=None):
        self.phase = phase
        if external is not None: self.external = external
        self.save(self.snapshot())
    def snapshot(self):
        return {"phase":self.phase, "external":self.external, "repair_attempts":self.repair,
                "history":self.history[-8:]}
    def failure(self, exc):
        code = exc.code if isinstance(exc, ValidationFailure) else ("interrupted" if not isinstance(exc, Exception) else ("connector_timeout" if isinstance(exc, TimeoutError) and self.external == "unknown" else "unexpected"))
        return {**self.snapshot(), "code":code, "reason":str(exc) if isinstance(exc, ValidationFailure) else REASONS[code],
                "category":"validation" if isinstance(exc, ValidationFailure) else ("interruption" if not isinstance(exc, Exception) else "adapter")}
def checkpoint(phase, external=None):
    trace = CURRENT.get()
    if trace: trace.checkpoint(phase, external)
def evidence(value):
    # Fingerprint, never raw output, keys, URLs, payloads, credentials or exception messages.
    encoded = json.dumps(value, sort_keys=True, default=lambda _: "<non-json>").encode()
    trace = CURRENT.get()
    if trace:
        trace.history.append({"response_sha256":hashlib.sha256(encoded).hexdigest(), "bytes":len(encoded)})
        trace.save(trace.snapshot())
