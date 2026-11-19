"""WorkflowContext — the single mutable state object passed between pipeline nodes.

Pydantic v2 BaseModel so it serialises to/from JSON cleanly for DB storage.
TokenVault is NOT stored here — the engine holds it and merges the reverse map
into context.token_map after each redaction step so the DeRedactionNode can
restore original text without needing the vault itself.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.models.pipeline import RedactionPolicy


class WorkflowContext(BaseModel):
    model_config = {'use_enum_values': True}

    run_id: str
    patient_id: int | None = None
    redaction_policy: str = RedactionPolicy.redact_all.value
    model_is_local: bool = False

    # Set only by DataAssemblyNode
    is_redacted: bool = False
    is_hcp_redacted: bool = False

    metadata: dict = Field(default_factory=dict)
    input: dict = Field(default_factory=dict)
    data: dict = Field(default_factory=dict)

    # current_prompt, system_prompt, model_id, temperature, max_tokens
    ai_state: dict = Field(default_factory=dict)

    # ai_responses: list[str], final_output: str
    results: dict = Field(default_factory=lambda: {'ai_responses': [], 'final_output': ''})

    audit_trail: list = Field(default_factory=list)

    # token → original; populated by engine from vault.get_reverse_map() after redaction
    token_map: dict = Field(default_factory=dict)

    def log(self, node: str, message: str) -> None:
        self.audit_trail.append({'node': node, 'message': message})

    def as_json(self) -> str:
        return self.model_dump_json()

    @classmethod
    def from_json(cls, raw: str) -> WorkflowContext:
        return cls.model_validate_json(raw)


# Pipelines whose runs carry no patient yet still get the redaction passes that
# need no patient record (ADR-053): the generic chatbot. Its question has been
# through a local AI erasure step, but nothing deterministic stood behind that
# before the cloud call. The Library joined in ADR-093: it never has a patient,
# so these passes are all the redaction its prompts get.
GENERAL_REDACTION_CLASSIFIERS = frozenset({'chatbot_generic', 'lib'})


def runs_general_redaction(context: WorkflowContext) -> bool:
    """True for a redact_all run with no patient on a pipeline listed above."""
    classifier = str(context.metadata.get('classifier') or '').strip().strip('[]').lower()
    return (not context.patient_id
            and context.redaction_policy == RedactionPolicy.redact_all.value
            and classifier in GENERAL_REDACTION_CLASSIFIERS)
