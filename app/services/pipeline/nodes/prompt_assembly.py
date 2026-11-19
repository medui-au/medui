"""PromptAssemblyNode — resolves and renders the user prompt for inference.

Resolution chain for system prompt:
  1. config['system_prompt_name']  (step-level override)
  2. user_prompt.system_prompt_name  (user prompt default)
  3. SystemPrompt with is_default=True  (global fallback)

Template variables supported in prompt_text:
  {{data.<key>}}     — from context.data
  {{input.<key>}}    — from context.input  (e.g. {{input.user_prompt}} for AI Panel typed text)
  {{results.<key>}}  — from context.results
  {{metadata.<key>}} — from context.metadata

Note: if the template does NOT include {{input.user_prompt}} but the caller
supplied one (e.g. via the AI Panel textarea), it is appended to the rendered
prompt automatically so the user's query is never silently dropped.

Exception — an edited template (Mode C): the AI Panel pre-fills its textarea
with this template, so what arrives as user_prompt is often the template
itself, possibly edited. It then *replaces* the stored template instead of
being appended to it. Appending it rendered the instructions and the whole
data bundle twice — 185 of 1,311 runs in the 30 days to 2026-09-26.

config keys:
  user_prompt_id: int     — required
  system_prompt_name: str — optional step-level override
  scope_key: str          — optional scope instruction for this step (ADR-087), or 'none'
  model_id: int | None    — optional; overrides user_prompt.default_model_id
"""

import json
import re

from flask import current_app

from app.services.pipeline.context import WorkflowContext
from app.services.pipeline.node import PipelineNode

_VAR_RE = re.compile(r'\{\{(\w+)\.(\w+)\}\}')


def _is_edited_template(user_input: str, template: str) -> bool:
    """True when user_prompt is this template (possibly edited), not a question.

    Either it carries template tokens ({{data.blocks}} …) — which only the
    pre-filled template does — or it opens with the template's own text.
    """
    if _VAR_RE.search(user_input):
        return True
    head = ' '.join(template.split())[:60]
    return len(head) >= 20 and ' '.join(user_input.split()).startswith(head)


def resolve_system_prompt(config: dict, up):
    """The SystemPrompt a prompt_assembly step sends, or None.

    Step override → the user prompt's own → the default (see module docstring).
    A named prompt that is missing, inactive or empty falls back to the default.
    Shared with the AI assistant's "Instructions given to the AI" strip, so the
    user sees exactly what a run would send.
    """
    from app.models.prompt import SystemPrompt

    sp_name = (config.get('system_prompt_name') or '').strip() or \
              (up.system_prompt_name or '').strip()
    if sp_name:
        sp = SystemPrompt.query.filter_by(name=sp_name, is_active=True).first()
        if sp and sp.prompt_text:
            return sp
        if not sp:
            current_app.logger.warning(
                'PromptAssemblyNode: system prompt %r not found; falling back to default', sp_name)
    sp_default = SystemPrompt.query.filter_by(is_default=True, is_active=True).first()
    return sp_default if sp_default and sp_default.prompt_text else None


def assemble_system_prompt(config: dict, up) -> tuple[str, str | None, dict]:
    """(system prompt as sent, '<name> v<version>' or None, scope record).

    The resolved system prompt with its scope instruction in front (ADR-087).
    Shared by PromptAssemblyNode and the AI assistant's instructions strip.
    """
    from app.services import scope_service
    sp = resolve_system_prompt(config, up)
    text, scope = scope_service.build_system_prompt(sp.prompt_text if sp else '', config, sp)
    return text, (f'{sp.name} v{sp.version}' if sp else None), scope


_CHECK_MODES = ('off', 'record', 'warn', 'block')


def scope_check_mode(config: dict) -> str:
    """Practice mode (Setup → AI scope), raised — never lowered — by the step's own."""
    from app.models.system_setting import SystemSetting
    practice = SystemSetting.get('scope.check_mode', 'record')
    practice = practice if practice in _CHECK_MODES else 'record'
    step = (config.get('scope_check_mode') or '').strip()
    if step in _CHECK_MODES and _CHECK_MODES.index(step) > _CHECK_MODES.index(practice):
        return step
    return practice


def _record_scope_check(context: WorkflowContext, config: dict, user_input: str, template: str) -> None:
    """Store the scope check's verdict on the run. Recording only for now:
    warn and block are recorded the same way until the pre-send review exists.
    A failure is logged and never stops the run."""
    from app.services.checker import scope as scope_check
    try:
        mode = scope_check_mode(config)
        if mode == 'off':
            return
        typed = scope_check.typed_text(user_input, template,
                                       bool(user_input) and _is_edited_template(user_input, template))
        verdict = scope_check.record(typed, mode)
    except Exception as exc:  # recording only: must never stop a run
        current_app.logger.warning('scope check failed: %s', type(exc).__name__)
        context.results['scope_check'] = {'error': type(exc).__name__}
        return
    context.results['scope_check'] = verdict
    if verdict['flagged']:
        context.log('PromptAssemblyNode',
                    'scope check: ' + ', '.join(sorted({h['pattern'] for h in verdict['hits']})))


class PromptAssemblyNode(PipelineNode):
    node_type = 'prompt_assembly'

    def execute(self, context: WorkflowContext, config: dict) -> WorkflowContext:
        prompt_id = config.get('user_prompt_id')
        if not prompt_id:
            raise ValueError('PromptAssemblyNode: user_prompt_id is required in config')

        from app.models.prompt import UserPrompt

        up = UserPrompt.query.get(prompt_id)
        if not up or not up.is_active:
            raise ValueError(f'UserPrompt {prompt_id} not found or inactive')

        # ── Resolve system prompt ─────────────────────────────────────────────
        system_prompt_text, system_prompt_version, scope = assemble_system_prompt(config, up)

        # ── Render template variables ─────────────────────────────────────────
        namespaces = {
            'data':     context.data,
            'input':    context.input,
            'results':  context.results,
            'metadata': context.metadata,
        }

        def _replace(m: re.Match) -> str:
            ns, key = m.group(1), m.group(2)
            val = namespaces.get(ns, {})
            if isinstance(val, dict):
                return str(val.get(key, m.group(0)))
            return m.group(0)

        user_input = (context.input.get('user_prompt') or '').strip()

        if user_input and _is_edited_template(user_input, up.prompt_text):
            # Mode C: the textarea held this template (edited or not), so it
            # stands in for the stored one. Rendered once; a self-reference
            # to {{input.user_prompt}} renders empty rather than as a copy.
            def _replace_edited(m: re.Match) -> str:
                if (m.group(1), m.group(2)) == ('input', 'user_prompt'):
                    return ''
                return _replace(m)
            rendered_prompt = _VAR_RE.sub(_replace_edited, user_input)
        else:
            rendered_prompt = _VAR_RE.sub(_replace, up.prompt_text)

            # ── Guarantee user_prompt reaches the LLM ────────────────────────
            # If the template already referenced {{input.user_prompt}} it has
            # been substituted above. If it did NOT (e.g. a generic
            # data-context prompt), append the user's typed query so it is
            # never silently dropped.
            if user_input and '{{input.user_prompt}}' not in up.prompt_text:
                rendered_prompt = rendered_prompt + '\n\n' + user_input

            # Second pass: resolve any template tokens that arrived via
            # user_prompt.
            rendered_prompt = _VAR_RE.sub(_replace, rendered_prompt)

        # ── Scope check on the user's own words (ADR-089) ─────────────────────
        # The Library sends its typed request as user_instruction (ADR-093).
        typed_request = user_input or (context.input.get('user_instruction') or '').strip()
        _record_scope_check(context, config, typed_request, up.prompt_text)

        # ── Write ai_state ────────────────────────────────────────────────────
        model_id = config.get('model_id') or up.default_model_id
        temperature = config.get('temperature', up.temperature)
        max_tokens = config.get('max_tokens', up.max_tokens)

        context.ai_state = {
            'current_prompt':    rendered_prompt,
            'system_prompt':     system_prompt_text,
            'system_prompt_version': system_prompt_version,
            'scope':             scope,
            'user_prompt_id':    prompt_id,
            'user_prompt_name':  up.name,
            'model_id':          model_id,
            'temperature':       temperature,
            'max_tokens':        max_tokens,
        }

        context.log('PromptAssemblyNode',
                    f'Assembled prompt from UserPrompt#{prompt_id} ({up.name}); '
                    f'system={system_prompt_version or "(none)"}; '
                    f'scope={scope.get("key", "off") if scope.get("enabled") else "off"}'
                    f'{" v" + str(scope["version"]) if scope.get("applied") else ""}; '
                    f'model_id={model_id}')

        return context
