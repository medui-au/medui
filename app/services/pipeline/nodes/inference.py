"""InferenceNode — calls the AI provider with the assembled prompt.

Security pre-check is non-bypassable: if redaction_policy is not redact_all
and the resolved provider is_cloud, the run is blocked with PermissionError.
Under redact_all, a patient-linked cloud run is also blocked if the patient's
identifiers could not be loaded (nothing to redact against).

config keys:
  model_id: int | None  — overrides context.ai_state['model_id']
  provider_id: int | None — pin to a specific provider (optional)
  default_setting_key: str — SystemSetting key to fall back to when no model_id
    resolves from override/config/ai_state (default 'default_model_id')
  keep_alive: str | int | None — Ollama-specific VRAM residence hint (e.g.
    "30m", or -1 for indefinite), forwarded to the provider if it supports
    it. No effect on providers that don't (Anthropic, non-Ollama
    OpenAI-compatible backends).
  request_params: dict | None — extra request parameters for this step, replacing
    the model's own (Setup → Models) key by key; a key set to null removes the
    model's value (ADR-119). Not a privacy setting.
"""

import time

from flask import current_app

from app.models.pipeline import RedactionPolicy
from app.services.pipeline.context import WorkflowContext, runs_general_redaction
from app.services.pipeline.node import PipelineNode


class InferenceNode(PipelineNode):
    node_type = 'inference'

    def __init__(self, vault=None):
        self._vault = vault

    def execute(self, context: WorkflowContext, config: dict) -> WorkflowContext:
        ai_state = context.ai_state
        if not ai_state.get('current_prompt'):
            raise ValueError('InferenceNode: context.ai_state.current_prompt is empty; '
                             'PromptAssemblyNode must run first')

        model_id = (context.input.get('model_id_override') or
                    config.get('model_id') or
                    ai_state.get('model_id'))
        if not model_id:
            from app.models.system_setting import SystemSetting
            # default_setting_key lets a step point its fallback at a different
            # SystemSetting than the generic one (e.g. chatbot pipelines use
            # 'default_chatbot_model_id' instead of 'default_model_id').
            model_id = SystemSetting.get(config.get('default_setting_key', 'default_model_id'))
        if not model_id:
            raise ValueError(
                'InferenceNode: no model selected. Set a default model in Setup → AI Providers, '
                'or assign one to the prompt or pipeline step.'
            )

        # ── Resolve model + provider ──────────────────────────────────────────
        from app.models.ai_provider import AIModel, AIProviderConfig
        from app.services.ai_providers.factory import get_provider

        model = AIModel.query.get(model_id)
        if not model or not model.is_enabled:
            raise ValueError(f'Model {model_id} not found or disabled')

        provider_cfg: AIProviderConfig = model.provider
        if not provider_cfg or not provider_cfg.is_enabled:
            raise ValueError(f'Provider for model {model_id} not found or disabled')

        provider = get_provider(provider_cfg, model.model_id)
        extra_params = _request_params(model, config)

        # ── Security pre-check (non-bypassable) ───────────────────────────────
        _security_pre_check(context, provider)

        # ── Prompt redaction ──────────────────────────────────────────────────
        # Redact current_prompt using the same vault as DataAssemblyNode so
        # user-typed input and any externally injected blocks (e.g. atomic
        # rollup) are covered by the app's own RedactionService before the
        # prompt reaches any provider.  System prompt is intentionally skipped —
        # it is admin-authored and short identifiers risk false positives.
        # A run with no patient (the generic chatbot) gets the passes that need
        # no patient record (ADR-053).
        policy = RedactionPolicy(context.redaction_policy)
        if self._vault and policy != RedactionPolicy.redact_none and (
                context.patient_id or runs_general_redaction(context)):
            _redact_prompt(context, self._vault)

        # ── Pre-send privacy check ────────────────────────────────────────────
        # The checker runs on the prompt exactly as it will be sent; the verdict is
        # stored with the run (positions and types, never text), shown on the privacy
        # card and on the Sent to AI tab. A failure never stops the run.
        if provider.is_cloud:
            _record_precheck(context, ai_state['current_prompt'])

        # ── Pre-send review (ADR-090) ─────────────────────────────────────────
        # On a page that can show it: pause for the user's setting, or always
        # on a blocking hit (tier 0/1), and send only what passes a fresh check.
        review_meta = context.metadata.get('review') or {}
        if provider.is_cloud and review_meta.get('capable'):
            from app.services.pipeline import review
            if review_meta.get('always') or review.is_blocking(context.results.get('precheck')):
                review.run_review(context, ai_state, always=bool(review_meta.get('always')))

        # ── Inference ─────────────────────────────────────────────────────────
        if extra_params:
            ai_state['request_params'] = extra_params
        t0 = time.monotonic()
        result = provider.generate(
            prompt=ai_state['current_prompt'],
            system_prompt=ai_state.get('system_prompt') or None,
            temperature=ai_state.get('temperature'),
            max_tokens=ai_state.get('max_tokens'),
            keep_alive=config.get('keep_alive'),
            request_params=extra_params or None,
        )
        latency_ms = int((time.monotonic() - t0) * 1000)

        # ── Scope flag (ADR-087) ──────────────────────────────────────────────
        # A reply that starts with the out-of-scope token is flagged: the token
        # comes out of the text and the flag goes on the run for the panels.
        content = result.content
        scope = dict(ai_state.get('scope') or {})
        if scope.get('applied'):
            from app.services import scope_service
            content, scope['model_flagged'] = scope_service.detect_flag(content)
            content, scope['legality'] = scope_service.detect_legality(content)
            if scope['model_flagged']:
                context.log('InferenceNode', f"scope: reply flagged out of scope ({scope.get('key')})")
        if scope:
            context.results['scope'] = scope

        response_entry = {
            'model_used':         result.model_used,
            'provider':           provider_cfg.name,
            'provider_is_local':  bool(provider_cfg.is_local),
            'content':            content,
            'tokens_input':       result.tokens_input,
            'tokens_output':      result.tokens_output,
            'cached_tokens':      result.cached_tokens,
            'cache_write_tokens': result.cache_write_tokens,
            'cost':               result.cost,
            'latency_ms':         latency_ms,
            'reasoning_chars':    result.reasoning_chars,
            'reasoning_tokens':   result.reasoning_tokens,
        }

        context.results.setdefault('ai_responses', []).append(response_entry)
        context.results['final_output'] = content

        # The privacy card shows the pre-send check (app/services/checker/). Absent means
        # the check didn't run or failed: shown as "not checked", never as clean.
        from app.services import privacy_check_service
        if not provider.is_cloud:
            context.results['privacy_check'] = {'skipped': 'local model'}
        else:
            card = privacy_check_service.card_from_precheck(context.results.get('precheck'))
            if card:
                context.results['privacy_check'] = card

        # A screening pipeline's answer is a list of suspected identifiers: the card shows
        # them, located in the prompt.
        if config.get('screening'):
            context.results['privacy_check'] = {'screening': {
                'matches': privacy_check_service.screening_matches(content or '', ai_state['current_prompt'])}}

        context.log('InferenceNode',
                    f'model={result.model_used} tokens={result.tokens_input}→{result.tokens_output} '
                    f'latency={latency_ms}ms')

        return context


def _record_precheck(context: WorkflowContext, prompt: str) -> None:
    from app.services.checker.scan import scan
    try:
        verdict = scan(prompt, context.patient_id)
    except Exception as exc:  # recording only: the check must never stop a run
        current_app.logger.warning('pre-send check failed: %s', type(exc).__name__)
        verdict = {'error': type(exc).__name__}
    context.results.setdefault('prechecks', []).append(verdict)
    context.results['precheck'] = verdict
    if 'error' not in verdict:
        context.log('InferenceNode',
                    f"pre-send check: top_tier={verdict['top_tier']} hits={len(verdict['hits'])} "
                    f"{verdict['scanned_ms']}ms")


def _security_pre_check(context: WorkflowContext, provider) -> None:
    """Block cloud inference when data has not been fully redacted.

    This check is the privacy wall defined in ADR-007. It cannot be bypassed
    from config — it reads context state set only by DataAssemblyNode.
    """
    policy = RedactionPolicy(context.redaction_policy)
    if policy == RedactionPolicy.redact_all:
        # Cloud is permitted only if there is something to redact against.
        # get_identifiers returns [] without raising when BPSDB is unreachable
        # or the patient isn't found — fail closed rather than send unredacted.
        if provider.is_cloud and context.patient_id:
            from app.services.redaction_service import RedactionService
            if not RedactionService.get_identifiers(context.patient_id):
                raise PermissionError(
                    'SECURITY BLOCK: redaction unavailable — patient identifiers could not be '
                    'loaded (patient database unreachable?). Nothing was sent to the cloud. '
                    'Use a Local pipeline or retry.'
                )
        return  # cloud providers permitted when data is fully redacted

    if not context.model_is_local:
        raise PermissionError(
            f'SECURITY BLOCK: redaction_policy={policy.value} requires a local provider, '
            'but model_is_local=False was sent from the client'
        )

    if provider.is_cloud:
        raise PermissionError(
            f'SECURITY BLOCK: redaction_policy={policy.value} requires a local provider, '
            f'but resolved provider ({provider.__class__.__name__}) is_cloud=True. '
            'Check provider configuration.'
        )


def _redact_prompt(context: WorkflowContext, vault) -> None:
    """Redact patient PII from the assembled prompt (user-typed free text coverage).

    Only the PII pass runs here. HCP redaction is intentionally skipped:
    DataAssemblyNode already HCP-redacted the patient data blocks before they
    were injected into the template, and applying HCP matching to the full
    prompt causes false positives where common words in admin-authored template
    text collide with provider surnames (same reason system_prompt is skipped).
    """
    from app.services.redaction_service import RedactionService

    original = context.ai_state.get('current_prompt', '')
    if not original:
        return

    # With no patient (ADR-053) the patient's own passes are skipped and only
    # the general ones run: there is no record to match against.
    patient_id = context.patient_id
    identifiers = RedactionService.get_identifiers(patient_id) if patient_id else []
    patterns = RedactionService.get_identifier_patterns(patient_id) if patient_id else None
    # A literal \\n, \\t or \\r — data blocks are written into the prompt as Python
    # text — counts as a word boundary while the passes run (ADR-116).
    from bps_redaction.escapes import mask, unmask
    # Backstop for the record number: DataAssemblyNode drops it from the rows,
    # but a block injected into the prompt another way would still carry it.
    redacted = RedactionService.drop_record_numbers(mask(original))
    # Share links and private-network links, whole, before any name in them
    # is tokenised (ADR-043).
    redacted = RedactionService.redact_links(redacted)
    # A number labelled as another service's identifier — UR, accession
    # number — before the number-shaped passes see it (ADR-076).
    redacted = RedactionService.redact_identifier_labels(redacted)
    # The practice's own name, admin text included: the token says what it is, so
    # "you are assisting at [Redacted UsualPractice: …]" still reads (ADR-121).
    redacted = RedactionService.redact_practice_name(redacted, vault)
    redacted = (RedactionService.redact(redacted, identifiers, vault, patterns=patterns)
                if identifiers else redacted)

    # Practice sites too. Unlike HCP surnames these are specific strings, so
    # running them over the whole prompt carries no false-positive risk — and
    # where a template legitimately carries the practice footer, de-redaction
    # restores it before the clinician sees the answer.
    practice = RedactionService.get_practice_identifiers()
    if practice:
        redacted = RedactionService.redact(redacted, practice, vault,
                                           mint=vault.mint_practice)

    # The patient's street name without its number (ADR-033), and the practice's
    # suburb with its postcode after the patient's own (ADR-066, ADR-067).
    if patient_id:
        redacted = RedactionService.redact_street_names(redacted, patient_id, vault)
    else:
        redacted = RedactionService.redact_practice_localities(redacted, vault)

    # Anyone else's address, and the patient's former ones (ADR-035).
    redacted = RedactionService.redact_other_addresses(redacted)

    # Anyone else's date of birth, by its label (ADR-047).
    redacted = RedactionService.redact_other_dobs(redacted)

    # Anyone else's email address or phone number, including in text the user
    # typed or pasted. Admin-authored template text is covered too; anything
    # there that the output needs is restored by de-redaction.
    redacted = RedactionService.redact_unlinked_contacts(redacted, vault)

    # Recurring strings on the admin always-redact list, before the titled-name
    # shape: a listed person keeps the label given to them (ADR-030).
    redacted = RedactionService.redact_always_list(redacted, vault)

    # The recipient slot of BP's letter lines (ADR-032).
    redacted = RedactionService.redact_letter_recipients(redacted, vault)

    redacted = RedactionService.redact_titled_names(redacted, vault)

    # The patient's likely shortened names, from the practice's table (ADR-048);
    # after the titled-name pass, so a titled name is taken whole (ADR-056).
    if patient_id:
        redacted = RedactionService.redact_practice_nicknames(redacted, patient_id, vault)

    # Last: the practice's common first names, and a surname after one — carers
    # and relatives no record names (ADR-058).
    redacted = unmask(RedactionService.redact_common_first_names(redacted, vault))

    context.ai_state['current_prompt'] = redacted
    context.token_map = vault.get_reverse_map()

    current_app.logger.debug(
        'InferenceNode._redact_prompt: patient=%s policy=%s prompt_len=%d→%d',
        context.patient_id, context.redaction_policy, len(original), len(redacted),
    )


def _request_params(model, config: dict) -> dict:
    """The model's extra request parameters with this step's override applied (ADR-119).
    A step value that no longer passes the rules is left out, with a warning."""
    from app.services import request_params
    step = config.get('request_params')
    try:
        step = request_params.check(step, allow_null=True)
    except ValueError as exc:
        current_app.logger.warning('Inference step request_params ignored: %s', exc)
        step = None
    return request_params.merged(request_params.load(model.request_params), step)
