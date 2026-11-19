"""PipelineEngine — orchestrates pipeline runs in a background thread.

Usage:
    run_id = PipelineEngine.run(pipeline_id, patient_id, user_id, input_data, model_is_local)
    # Then stream: GET /pipeline/run/<run_id>/stream  (SSE)

SSE event format:
    data: {"type": "step_start"|"step_done"|"error"|"complete", "step": N, "message": "..."}

Thread safety:
    - One queue per run_id stored in _RUN_QUEUES (module-level dict)
    - Engine pushes events; SSE endpoint drains them
    - Queue is cleaned up after the SSE stream closes (sentinel None)
"""

import json
import re
import queue
import threading
import time
import uuid
from datetime import datetime, timezone

from flask import current_app

_RUN_QUEUES: dict[str, queue.Queue] = {}
_SENTINEL = None


class PipelineEngine:

    @staticmethod
    def run(
        pipeline_id: int,
        patient_id: int | None,
        user_id: int,
        input_data: dict,
        model_is_local: bool,
        app=None,
        token_key: str | None = None,
        review: dict | None = None,
        transcript_by: int | None = None,
    ) -> str:
        """Start a pipeline run in a background thread. Returns run_id.

        token_key: optional override for the TokenVault HMAC key, defaulting to
        run_id. Lets a caller (e.g. a multi-turn chatbot) hold redaction tokens
        stable across several runs sharing one session, without reusing run_id
        itself — run_id must stay unique per run (it's PipelineRun.run_uuid).

        review: {'capable', 'always', 'user_id'} from a page that can show the
        pre-send review (ADR-090). Set by the server, never by the client.

        transcript_by: the user who recorded the consultation, when the input is a
        scribe transcript. Their own first names are then redacted from it in any
        case (ADR-133). Set by the scribe route, never by the client.
        """
        run_id = str(uuid.uuid4())
        q: queue.Queue = queue.Queue()
        _RUN_QUEUES[run_id] = q

        # The requesting workstation, for the usage record (runs in a thread).
        from flask import has_request_context, request
        workstation = request.remote_addr if has_request_context() else None

        # Capture the app instance for the background thread
        if app is None:
            app = current_app._get_current_object()

        thread = threading.Thread(
            target=PipelineEngine._run_thread,
            args=(app, run_id, pipeline_id, patient_id, user_id, input_data, model_is_local, q,
                  token_key, workstation, review, transcript_by),
            daemon=True,
            name=f'pipeline-{run_id[:8]}',
        )
        thread.start()
        return run_id

    @staticmethod
    def get_queue(run_id: str) -> queue.Queue | None:
        return _RUN_QUEUES.get(run_id)

    @staticmethod
    def cleanup(run_id: str) -> None:
        _RUN_QUEUES.pop(run_id, None)

    # ── Background thread ─────────────────────────────────────────────────────

    @staticmethod
    def _run_thread(app, run_id, pipeline_id, patient_id, user_id,
                    input_data, model_is_local, q, token_key=None, workstation=None, review=None,
                    transcript_by=None):
        with app.app_context():
            try:
                PipelineEngine._execute(
                    run_id, pipeline_id, patient_id, user_id, input_data, model_is_local, q,
                    token_key, workstation=workstation, review=review,
                    transcript_by=transcript_by)
            except Exception as exc:
                app.logger.error('PipelineEngine unhandled error run=%s: %s', run_id, exc)
                _push(q, 'error', message=str(exc))
            finally:
                q.put(_SENTINEL)

    @staticmethod
    def _execute(run_id, pipeline_id, patient_id, user_id, input_data, model_is_local, q,
                 token_key=None, workstation=None, review=None, transcript_by=None):
        from app.extensions import db
        from app.models.pipeline import Pipeline, PipelineRun, RunStatus, RedactionPolicy
        from app.utils.token_vault import TokenVault
        from app.services.pipeline.review import ReviewCancelled

        # ── Load pipeline ─────────────────────────────────────────────────────
        pipeline = db.session.get(Pipeline, pipeline_id)
        if not pipeline:
            raise ValueError(f'Pipeline {pipeline_id} not found')
        if pipeline.is_archived:
            raise ValueError('This pipeline is archived. Unarchive it to run it.')

        steps = list(pipeline.steps)

        # ── Derive model_is_local from pipeline config ────────────────────────
        # Client assertion is unreliable (most callers default to False).
        # Scan inference steps; if any configured model resolves to a local
        # provider, treat the run as local regardless of what the client sent.
        model_is_local = _derive_model_is_local(steps, model_is_local, input_data)

        # ── Create PipelineRun row ────────────────────────────────────────────
        run = PipelineRun(
            pipeline_id=pipeline_id,
            patient_id=patient_id,
            initiated_by_id=user_id,
            status=RunStatus.running,
            redaction_policy=pipeline.redaction_policy,
            model_is_local=model_is_local,
            run_uuid=run_id,
        )
        db.session.add(run)
        db.session.commit()
        run_db_id = run.id

        # ── Build WorkflowContext ─────────────────────────────────────────────
        from app.services.pipeline.context import WorkflowContext

        context = WorkflowContext(
            run_id=run_id,
            patient_id=patient_id,
            redaction_policy=pipeline.redaction_policy.value,
            model_is_local=model_is_local,
            input=input_data or {},
            metadata={'pipeline_id': pipeline_id, 'run_db_id': run_db_id,
                      'pipeline_name': pipeline.name, 'workstation': workstation,
                      'classifier': pipeline.classifier,
                      'review': review or {}, 'transcript_by': transcript_by},
        )

        vault = TokenVault(token_key or run_id)
        step_snapshots: list[str] = []

        try:
            _redact_hcp_in_input(context, vault)
        except PermissionError as exc:
            _push(q, 'step_error', step=0, node='input redaction', status='error',
                  message=f'SECURITY BLOCK: {exc}', error=str(exc))
            PipelineEngine._finalise_run(run_db_id, RunStatus.failed, context,
                                         step_snapshots, error=str(exc))
            return

        _push(q, 'start', message=f'Pipeline "{pipeline.name}" started ({len(steps)} steps)',
              total_steps=len(steps))

        # ── Execute steps ─────────────────────────────────────────────────────
        for i, step in enumerate(steps):
            config = json.loads(step.config_json or '{}')
            node = _build_node(step.node_type, vault)
            label = step.label or step.node_type

            _push(q, 'step_start', step=i, node=label,
                  message=f'Step {i + 1}: {label}')

            t0 = time.monotonic()
            try:
                context = node.execute(context, config)
            except ReviewCancelled as exc:
                dur = int((time.monotonic() - t0) * 1000)
                _push(q, 'cancelled', step=i, node=label, duration_ms=dur,
                      message=f'{exc} — nothing was sent to the AI.')
                PipelineEngine._finalise_run(
                    run_db_id, RunStatus.cancelled, context, step_snapshots, error=str(exc))
                return
            except PermissionError as exc:
                dur = int((time.monotonic() - t0) * 1000)
                _push(q, 'step_error', step=i, node=label, status='error',
                      duration_ms=dur, message=f'SECURITY BLOCK: {exc}',
                      error=str(exc))
                PipelineEngine._finalise_run(
                    run_db_id, RunStatus.failed, context, step_snapshots,
                    error=str(exc))
                return
            except Exception as exc:
                dur = int((time.monotonic() - t0) * 1000)
                current_app.logger.error(
                    'PipelineEngine step=%d node=%s run=%s error=%s',
                    i, step.node_type, run_id, exc, exc_info=True)
                _push(q, 'step_error', step=i, node=label, status='error',
                      duration_ms=dur, message=f'{label} failed: {exc}',
                      error=str(exc))
                PipelineEngine._finalise_run(
                    run_db_id, RunStatus.failed, context, step_snapshots,
                    error=str(exc))
                return

            dur = int((time.monotonic() - t0) * 1000)
            step_snapshots.append(context.as_json())
            _push(q, 'step_done', step=i, node=label, status='ok',
                  duration_ms=dur, message=f'Step {i + 1} complete')

        # ── Finalise ──────────────────────────────────────────────────────────
        PipelineEngine._finalise_run(
            run_db_id, RunStatus.completed, context, step_snapshots)

        # Extract pre-redaction prompt from the snapshot just before InferenceNode
        pre_redaction_prompt = ''
        for idx, step in enumerate(steps):
            if step.node_type == 'inference' and idx > 0 and idx - 1 < len(step_snapshots):
                try:
                    pre_snap = json.loads(step_snapshots[idx - 1])
                    pre_redaction_prompt = pre_snap.get('ai_state', {}).get('current_prompt', '')
                except Exception:
                    pass
                break

        _push(q, 'complete', message='Run completed',
              output=context.results.get('final_output', ''),
              # Administrators only: a level-4 user may open the debug tab, so
              # the verdict is withheld at source rather than hidden in the UI.
              privacy_check=(context.results.get('privacy_check')
                             if _initiator_is_admin(user_id) else None),
              is_redacted=context.is_redacted,
              is_hcp_redacted=context.is_hcp_redacted,
              model_is_local=model_is_local,
              run_db_id=run_db_id,
              # Which scope instruction applied and whether the reply was
              # flagged out of scope (ADR-087); shown to every user.
              scope=context.results.get('scope'),
              # What happened at the pre-send review, if it paused (ADR-090).
              review=context.results.get('review'),
              # The pre-send check's result for the Sent to AI tab, for every user:
              # positions and types in the prompt they can already see (ADR-115).
              sent_check=_sent_check(context.results.get('precheck')),
              ai_debug={
                  'system_prompt':        context.ai_state.get('system_prompt', ''),
                  'pre_redaction_prompt': pre_redaction_prompt,
                  'current_prompt':       context.ai_state.get('current_prompt', ''),
                  'ai_responses':         context.results.get('ai_responses', []),
                  # Extra request parameters sent with the request (ADR-119).
                  'request_params':       context.ai_state.get('request_params'),
              })

    @staticmethod
    def _finalise_run(run_db_id, status, context, step_snapshots, error=None):
        from app.extensions import db
        from app.models.pipeline import PipelineRun, RunStatus

        run = db.session.get(PipelineRun, run_db_id)
        if not run:
            current_app.logger.error('_finalise_run: PipelineRun %d not found', run_db_id)
            return

        run.status = status
        run.finished_at = datetime.now(timezone.utc)
        run.is_redacted = context.is_redacted
        run.is_hcp_redacted = context.is_hcp_redacted
        run.context_json = context.as_json()
        run.step_snapshots_json = json.dumps(step_snapshots)
        run.output_json = json.dumps(context.results)
        if error:
            run.error_message = error[:2000]

        db.session.commit()

        # The permanent usage record (plans/usage_reporting_plan.md) — best-effort.
        from app.services import usage_service
        usage_service.record_pipeline_run(run_db_id, workstation=context.metadata.get('workstation'))


# ── Helpers ───────────────────────────────────────────────────────────────────

def extract_debug_info(run) -> dict:
    """Reconstruct the same {system_prompt, pre_redaction_prompt, current_prompt,
    ai_responses} shape the 'complete' SSE event carries live, from an already-
    persisted PipelineRun — for displaying debug detail after the live stream is
    gone (e.g. historical chat transcript turns)."""
    from app.extensions import db
    from app.models.pipeline import Pipeline

    try:
        step_snapshots = json.loads(run.step_snapshots_json or '[]')
        output = json.loads(run.output_json or '{}')
    except (ValueError, TypeError):
        return {}

    pipeline = db.session.get(Pipeline, run.pipeline_id) if run.pipeline_id else None
    steps = list(pipeline.steps) if pipeline else []

    pre_redaction_prompt = ''
    for idx, step in enumerate(steps):
        if step.node_type == 'inference' and idx > 0 and idx - 1 < len(step_snapshots):
            try:
                pre_snap = json.loads(step_snapshots[idx - 1])
                pre_redaction_prompt = pre_snap.get('ai_state', {}).get('current_prompt', '')
            except (ValueError, TypeError):
                pass
            break

    last_snap = {}
    if step_snapshots:
        try:
            last_snap = json.loads(step_snapshots[-1])
        except (ValueError, TypeError):
            pass
    ai_state = last_snap.get('ai_state', {})

    return {
        'system_prompt':        ai_state.get('system_prompt', ''),
        'pre_redaction_prompt': pre_redaction_prompt,
        'current_prompt':       ai_state.get('current_prompt', ''),
        'ai_responses':         output.get('ai_responses', []),
        # None when the pre-send check didn't run or failed, or the run predates it:
        # the UI must show that as "not checked", never as clean.
        'privacy_check':        output.get('privacy_check'),
        'scope':                output.get('scope'),
    }


def _sent_check(precheck) -> dict | None:
    """The check's verdict without anything but positions and types (ADR-115)."""
    if not isinstance(precheck, dict) or 'error' in precheck or 'hits' not in precheck:
        return None
    return {'top_tier': precheck.get('top_tier'), 'detector_version': precheck.get('detector_version'),
            'patient_identifiers': precheck.get('patient_identifiers'),
            'hits': [{k: h.get(k) for k in ('tier', 'type', 'start', 'end')}
                     for h in precheck.get('hits') or [] if isinstance(h, dict)]}


def _initiator_is_admin(user_id) -> bool:
    """True when the user who started the run may see the privacy verdict."""
    if not user_id:
        return False
    try:
        from app.extensions import db
        from app.models.user import User
        user = db.session.get(User, user_id)
        return bool(user and user.is_admin)
    except Exception as exc:
        current_app.logger.warning('could not resolve run initiator %s: %s', user_id, exc)
        return False


def _redact_hcp_in_input(context, vault) -> None:
    """Strip the patient's identifiers, then practitioner names, from caller-supplied input under redact_all.

    Input text — the scribe's raw transcript, the AI panel's typed question —
    never passes through DataAssemblyNode, so the HCP pass never saw it.
    InferenceNode redacts the assembled prompt with the patient pass only,
    because running HCP matching over admin-authored template text produces
    false positives where a common word collides with a provider surname.

    Redacting the input *values* here, before any template is rendered, gets
    the coverage without that risk: template text is never touched. Added
    2026-09-20 after an audit found spoken practitioner names reaching a cloud
    provider in scribe transcripts (ADR-019).

    Does not set context.is_hcp_redacted — DataAssemblyNode remains the sole
    authority on that flag (ADR-005).
    """
    from app.models.pipeline import RedactionPolicy
    from app.services.pipeline.context import runs_general_redaction

    if RedactionPolicy(context.redaction_policy) != RedactionPolicy.redact_all:
        return
    # A run with no patient gets this pass only on the generic chatbot
    # (ADR-053), against the whole practice address book.
    if not context.input or not (context.patient_id or runs_general_redaction(context)):
        return

    strings = {k: v for k, v in context.input.items()
               if isinstance(v, str) and v.strip() and not _is_control_value(v)}
    if not strings:
        return

    from app.services.hcp_redaction_service import HCPRedactionService

    try:
        hcp_map = HCPRedactionService.build_hcp_map(context.patient_id)
    except Exception as exc:
        # Fail closed: input that could not be HCP-redacted must not proceed to
        # a cloud provider under redact_all.
        raise PermissionError(
            'SECURITY BLOCK: practitioner names could not be loaded, so caller '
            'input could not be redacted. Nothing was sent. Use a Local '
            f'pipeline or retry. ({exc})'
        ) from exc

    if not hcp_map:
        raise PermissionError(
            'SECURITY BLOCK: the practitioner contact list came back empty, so '
            'caller input could not be HCP-redacted. Nothing was sent.'
        )

    # The patient's own identifiers first (ADR-052): a name in a transcript
    # that is both the patient's and an address-book doctor's is the patient's.
    # InferenceNode runs this pass again over the whole prompt; doing it here
    # too just means it wins the label.
    from app.services.redaction_service import RedactionService
    identifiers = RedactionService.get_identifiers(context.patient_id) if context.patient_id else []
    patterns = RedactionService.get_identifier_patterns(context.patient_id) if identifiers else None

    # A scribe transcript: the recording clinician's own first names, in any case,
    # last (ADR-133). Speech-to-text often writes "thanks sam" in lower case.
    clinician_names = []
    if context.metadata.get('transcript_by'):
        from app.services import practitioner_names
        clinician_names = practitioner_names.clinician_first_names(context.metadata['transcript_by'])

    from bps_redaction.escapes import mask, unmask           # ADR-116
    for key, value in strings.items():
        value = mask(value)
        value = RedactionService.redact_practice_name(value, vault)        # ADR-121
        if identifiers:
            value = RedactionService.redact(value, identifiers, vault, patterns=patterns)
        value = HCPRedactionService.redact_hcp(
            value, hcp_map, vault, organisations_as_written=not context.patient_id)
        if clinician_names:
            value = RedactionService.redact_clinician_first_names(value, clinician_names, vault)
        context.input[key] = unmask(value)

    context.log('PipelineEngine',
                f'HCP-redacted {len(strings)} input field(s) against '
                f'{len(hcp_map)} contacts before prompt assembly')


def _is_control_value(value: str) -> bool:
    """True for short enum-like inputs ('normal', 'issues_list', '42').

    Those steer the pipeline rather than carrying clinical text, and a contact
    surname colliding with one would change behaviour rather than protect
    anyone. Anything with a space, punctuation, or real length is treated as
    text and redacted.
    """
    # Lower case only: 'Smith' as an input value is a name, 'issues_list' is a
    # setting. Redaction alters a value only when it matches a contact anyway,
    # so the narrower exemption costs nothing.
    return len(value) <= 24 and bool(re.fullmatch(r'[a-z0-9_.-]+', value))


def _derive_model_is_local(steps, client_value: bool, input_data: dict | None = None) -> bool:
    """Return True if any inference step's configured model uses a local provider.

    Checks context.input['model_id_override'] first for each inference step — it
    takes priority over step config in InferenceNode's own resolution chain
    (inference.py), so a caller-supplied override (e.g. a chatbot session's model
    picker) must be considered here too, or a run using an override to a local
    model would be mis-derived as cloud, which is user-visible (wrong cloud/local
    badge) and, for a stricter redaction_policy, would wrongly block a legitimate
    local-only run at the security pre-check.

    Falls back to client_value when no model can be resolved at all, preserving
    the designer test-panel checkbox for unconfigured pipelines.
    """
    from app.models.ai_provider import AIModel
    from app.models.prompt import UserPrompt
    from app.models.system_setting import SystemSetting

    override_id = (input_data or {}).get('model_id_override')

    # The prompt step's model — its own setting, else the user prompt's default —
    # is what InferenceNode falls back to when the inference step names none.
    # Missing it recorded runs of pipelines such as the PII screening pipeline,
    # which rely on the prompt's local default, as cloud.
    prompt_model_id = None
    for step in steps:
        if step.node_type == 'prompt_assembly':
            try:
                pcfg = json.loads(step.config_json or '{}')
            except ValueError:
                pcfg = {}
            prompt_model_id = pcfg.get('model_id')
            if not prompt_model_id and pcfg.get('user_prompt_id'):
                up = UserPrompt.query.get(pcfg['user_prompt_id'])
                prompt_model_id = up.default_model_id if up else None
            break

    for step in steps:
        if step.node_type != 'inference':
            continue
        try:
            cfg = json.loads(step.config_json or '{}')
        except ValueError:
            cfg = {}
        # Same order as InferenceNode: override, step, prompt, system default.
        model_id = (override_id or cfg.get('model_id') or prompt_model_id
                    or SystemSetting.get(cfg.get('default_setting_key', 'default_model_id')))
        if not model_id:
            continue
        model = AIModel.query.get(int(model_id))
        if model and model.provider and model.provider.is_local:
            return True

    return client_value


def _push(q: queue.Queue, event_type: str, step: int = -1, **kwargs) -> None:
    q.put({'type': event_type, 'step': step, **kwargs})


def _build_node(node_type: str, vault):
    from app.services.pipeline.nodes.data_assembly import DataAssemblyNode
    from app.services.pipeline.nodes.prompt_assembly import PromptAssemblyNode
    from app.services.pipeline.nodes.inference import InferenceNode
    from app.services.pipeline.nodes.deredaction import DeRedactionNode

    registry = {
        'data_assembly':   lambda: DataAssemblyNode(vault=vault),
        'prompt_assembly': PromptAssemblyNode,
        'inference':       lambda: InferenceNode(vault=vault),
        'deredaction':     DeRedactionNode,
    }
    factory = registry.get(node_type)
    if not factory:
        raise ValueError(f'Unknown node_type: {node_type!r}. '
                         f'Available: {sorted(registry)}')
    return factory()
