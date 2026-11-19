"""DataAssemblyNode — sole authority on context.is_redacted and context.is_hcp_redacted.

config keys:
  bundle_name: str | None   — name of DataBundle (default 'deid_context')
  blocks: list[str] | None  — override: specific block names instead of a bundle
  user_id: int | None       — passed through to PatientJsonService for scribe blocks
"""

import json

from flask import current_app

from app.models.pipeline import RedactionPolicy
from app.services.pipeline.context import WorkflowContext
from app.services.pipeline.node import PipelineNode


class DataAssemblyNode(PipelineNode):
    node_type = 'data_assembly'

    def __init__(self, vault=None):
        # vault is injected by the engine so it can merge token_map afterwards
        self._vault = vault

    def execute(self, context: WorkflowContext, config: dict) -> WorkflowContext:
        patient_id = context.patient_id
        policy = RedactionPolicy(context.redaction_policy)
        user_id = config.get('user_id')

        if patient_id is None:
            context.log('DataAssemblyNode', 'No patient_id; skipping data fetch')
            return context

        # ── Fetch data ────────────────────────────────────────────────────────
        from app.services.patient_json_service import PatientJsonService

        if not current_app.config.get('BPSDB_URI'):
            context.log('DataAssemblyNode', 'No BPSDB_URI configured; data empty')
            return context

        svc = PatientJsonService()  # auto-creates BPSDB session from config

        blocks_override = config.get('blocks')
        if blocks_override:
            import datetime as _dt
            raw_data: list[dict] = [{"Today's Date": _dt.datetime.now().strftime('%Y-%m-%d')}]
            for block in blocks_override:
                try:
                    val = svc.get_atomic_block(block, patient_id,
                                               deidentify=False, user_id=user_id)
                    raw_data.append({block: val})
                except Exception as exc:
                    current_app.logger.warning('DataAssemblyNode block=%s error=%s', block, exc)
        else:
            bundle_name = config.get('bundle_name', 'deid_context')
            raw_data = svc.get_bundle(bundle_name, patient_id, deidentify=False)

        context.log('DataAssemblyNode', f'Fetched {len(raw_data)} data blocks')

        # ── Apply redaction ───────────────────────────────────────────────────
        # A literal \\n, \\t or \\r in the data counts as a word boundary while the
        # passes run; the escapes are put back after (ADR-116).
        from bps_redaction.escapes import mask, unmask
        if policy != RedactionPolicy.redact_none:
            raw_data = mask(raw_data)

        if policy == RedactionPolicy.redact_all:
            from app.services.redaction_service import RedactionService
            from app.services.hcp_redaction_service import HCPRedactionService

            identifiers = RedactionService.get_identifiers(patient_id)
            # The patient's BP record number rides on every data row and the
            # model never needs it (ADR-031).
            redacted = RedactionService.drop_record_numbers(raw_data)
            # Share links and private-network links first, whole — before a
            # name inside one becomes a token and splits it (ADR-043).
            redacted = RedactionService.redact_links(redacted)
            # Another service's identifier by its label — UR, accession
            # number — before the number-shaped passes see it (ADR-076).
            redacted = RedactionService.redact_identifier_labels(redacted)
            # The practice's own name, before a town in it is taken as a patient's
            # suburb or a contact's surname (ADR-121).
            redacted = RedactionService.redact_practice_name(redacted, self._vault)
            redacted = RedactionService.redact(
                redacted, identifiers, self._vault,
                patterns=RedactionService.get_identifier_patterns(patient_id))

            hcp_map = HCPRedactionService.build_hcp_map(patient_id)
            redacted = HCPRedactionService.redact_hcp(redacted, hcp_map, self._vault)

            # The practice's own sites: address, phone, fax, email. Distinct
            # tokens ([Redacted Practice: PR-…]) so a reader can tell whose
            # identifier was removed.
            practice = RedactionService.get_practice_identifiers()
            if practice:
                redacted = RedactionService.redact(redacted, practice, self._vault,
                                                   mint=self._vault.mint_practice)

            # The patient's street name left without its number — only now, so a
            # full address is already a reversible token and a practice on the
            # same street keeps its own (ADR-033).
            # With the practice's suburb and postcode, in order (ADR-066, ADR-067).
            redacted = RedactionService.redact_street_names(redacted, patient_id, self._vault)

            # Anyone else's address — a clinician's rooms, a pathology site — and
            # the patient's former ones (ADR-035).
            redacted = RedactionService.redact_other_addresses(redacted)

            # Anyone else's date of birth, by its label (ADR-047).
            redacted = RedactionService.redact_other_dobs(redacted)

            # Email addresses and phone numbers left over after the patient's
            # and the practice's own: someone else's — a relative, a carer,
            # another clinician's rooms.
            redacted = RedactionService.redact_unlinked_contacts(redacted, self._vault)

            # Recurring strings on the admin always-redact list — a curated list
            # is more specific than the titled-name shape, so it goes first and a
            # listed person keeps the label given to them (ADR-030).
            redacted = RedactionService.redact_always_list(redacted, self._vault)

            # Whoever sits in the recipient slot of BP's letter lines — a
            # patient's shortened name, a relative, an outside specialist (ADR-032).
            redacted = RedactionService.redact_letter_recipients(redacted, self._vault)

            # A person named as a document's Author — an outside clinician the
            # address book does not hold (ADR-038).
            redacted = RedactionService.redact_author_slots(redacted, self._vault)

            # Anyone titled whom the passes above did not identify — a
            # misspelled contact, or a practitioner from another practice.
            redacted = RedactionService.redact_titled_names(redacted, self._vault)

            # Last: the shortened names most patients with this name go by
            # (ADR-048). After the Author and titled-name passes, so "Dr Tilly
            # Smith" is taken whole rather than leaving "Smith" (ADR-056).
            redacted = RedactionService.redact_practice_nicknames(redacted, patient_id, self._vault)

            # Last of all: the practice's common first names, and a surname after
            # one — carers and relatives no record names (ADR-058).
            redacted = RedactionService.redact_common_first_names(redacted, self._vault)

            # Only claim redaction if identifiers actually loaded ([] on BPSDB failure)
            context.is_redacted = bool(identifiers)
            context.is_hcp_redacted = True
            context.token_map = self._vault.get_reverse_map()
            context.log('DataAssemblyNode',
                        f'redact_all: {len(identifiers)} patient identifiers, '
                        f'{len(hcp_map)} HCP contacts redacted')
            context.data = {'blocks': unmask(redacted)}

        elif policy == RedactionPolicy.redact_pii_only:
            from app.services.redaction_service import RedactionService

            identifiers = RedactionService.get_identifiers(patient_id)
            redacted = RedactionService.redact(
                RedactionService.drop_record_numbers(raw_data), identifiers, self._vault,
                patterns=RedactionService.get_identifier_patterns(patient_id))
            redacted = RedactionService.redact_street_names(redacted, patient_id)  # ADR-033

            context.is_redacted = bool(identifiers)
            context.is_hcp_redacted = False
            context.token_map = self._vault.get_reverse_map()
            context.log('DataAssemblyNode',
                        f'redact_pii_only: {len(identifiers)} patient identifiers redacted')
            context.data = {'blocks': unmask(redacted)}

        else:  # redact_none
            context.is_redacted = False
            context.is_hcp_redacted = False
            context.log('DataAssemblyNode', 'redact_none: data assembled without redaction')
            context.data = {'blocks': raw_data}

        # Expose individual blocks by name for {{data.block_name}} template refs.
        # Handles both the bundle path (label keys) and blocks_override path
        # (block name keys).  Builds the label→name map once per call.
        _expose_named_blocks(context.data)

        return context


def _expose_named_blocks(data: dict) -> None:
    """Populate data[block_name] for every block in data['blocks'].

    Allows {{data.atomic_rollup}}, {{data.demographics}}, etc. in prompt
    templates alongside the existing {{data.blocks}} aggregate reference.
    """
    from app.services.patient_json_service import BLOCK_LABELS, BLOCK_META

    block_names = set(BLOCK_META.keys())
    label_to_name = {label: name for name, label in BLOCK_LABELS.items()}

    for block_dict in data.get('blocks', []):
        if not isinstance(block_dict, dict):
            continue
        for key, value in block_dict.items():
            if key in block_names:
                data[key] = value                      # blocks_override path
            elif key in label_to_name:
                data[label_to_name[key]] = value       # bundle path
