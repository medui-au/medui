"""Which requests count as a task in the usage record (plans/usage_reporting_plan.md §1).

Only endpoints listed here are recorded. Everything else — the day sheet's
self-refresh, a chart's thirteen data loads, scribe syncs, SMS previews, polls,
static files — is left out by design, so the record counts what people meant
to do. Adding a feature to the record is one line here.

AI runs and scribe sessions are recorded where they happen (the pipeline engine
and the voice routes), not here, so they are not listed.
"""

# endpoint -> (task, area). A tuple key (endpoint, method) narrows by method.
TASKS: dict = {
    # ── Clinical: viewing ────────────────────────────────────────────────────
    'clinical.search_results':          ('patient.search', 'clinical'),
    'clinical.patient':                 ('chart.open', 'clinical'),
    'clinical.progress_notes':          ('notes.view', 'clinical'),
    'clinical.patient_charts':          ('graphs.view', 'clinical'),
    'clinical.pathatom_dashboard':      ('pathology.dashboard', 'clinical'),
    'clinical.patient_json_dashboard':  ('patient_json.view', 'clinical'),
    'clinical.ai_panel':                ('ai_panel.open', 'clinical'),
    'viewer.letters_viewer':            ('viewer.letters', 'clinical'),
    'viewer.pathology_viewer':          ('viewer.pathology', 'clinical'),
    'viewer.scans_viewer':              ('viewer.scans', 'clinical'),
    'viewer.letter_content':            ('document.view', 'clinical'),
    'viewer.path_content':              ('document.view', 'clinical'),
    'viewer.scan_content':              ('document.view', 'clinical'),
    'inbox.index':                      ('inbox.open', 'clinical'),
    'inbox.report_content':             ('inbox.report_view', 'clinical'),
    'inbox.outliers':                   ('inbox.outliers', 'clinical'),
    'schedule.index':                   ('schedule.open', 'clinical'),
    'schedule.daysheet':                ('daysheet.open', 'clinical'),
    'clinical.med_mapping_approve':     ('medmap.approve', 'clinical'),
    'clinical.results_rollup_generate': ('results_rollup.generate', 'clinical'),
    'gpccmp.patient_targets':           ('targets.view', 'clinical'),
    'gpccmp.patient_targets_save':      ('targets.set', 'clinical'),
    'gpccmp.plan_decisions':            ('gpccmp.decisions_view', 'clinical'),
    'gpccmp.plan_decisions_save':       ('gpccmp.decisions_save', 'clinical'),
    'gpccmp.plan_draft_start':          ('gpccmp.draft', 'clinical'),
    'gpccmp.draft_again':               ('gpccmp.redraft', 'clinical'),

    # ── Exports to Best Practice ─────────────────────────────────────────────
    'clinical.ai_export_pit':           ('export.pit', 'export'),
    'voice.scribe_export_pit':          ('export.pit', 'export'),
    'careplan.export_bp':               ('export.pit', 'export'),
    'clinical_comms.api_export_pit':    ('export.pit', 'export'),
    'doc_library.pit_export':           ('export.pit', 'export'),

    # ── Communication and documents ──────────────────────────────────────────
    'clinical_comms.patient_comms':     ('messages.open', 'communication'),
    'clinical_comms.api_send':          ('message.send', 'communication'),
    'clinical_comms.api_draft':         ('message.draft', 'communication'),
    'clinical_comms.api_retry':         ('message.retry', 'communication'),
    'clinical_comms.api_revoke':        ('message.revoke', 'communication'),
    'clinical_comms.api_templates_create': ('template.change', 'communication'),
    'clinical_comms.api_templates_update': ('template.change', 'communication'),
    'clinical_comms.api_templates_delete': ('template.change', 'communication'),
    'doc_library.index':                ('library.open', 'communication'),
    'doc_library.search':               ('library.search', 'communication'),
    'doc_library.save_new':             ('library.create', 'communication'),
    'doc_library.save_as':              ('library.create', 'communication'),
    'doc_library.save_existing':        ('library.edit', 'communication'),
    'doc_library.delete':               ('library.delete', 'communication'),
    'chatbot.index':                    ('chatbot.open', 'communication'),
    'chatbot.generic_index':            ('chatbot.open', 'communication'),
    'chatbot.complete':                 ('chatbot.session_complete', 'communication'),
    # A general-chat message sent without the AI erasure step (ADR-098), after the
    # privacy warning: recorded so the practice can see how often it happens.
    'chatbot.send_message_generic_direct': ('chatbot.message_no_erasure', 'communication'),
    'chatbot.create_download':          ('chatbot.file', 'communication'),
    'voice.scribe':                     ('scribe.open', 'clinical'),
    'voice.quick_scribe':               ('quick_scribe.open', 'clinical'),

    # ── Practice management and governance ───────────────────────────────────
    'doctor.billings':                  ('report.billings', 'practice'),
    'doctor.billing_analysis':          ('report.billing_analysis', 'practice'),
    'doctor.quality':                   ('report.quality', 'practice'),
    'doctor.quality_report':            ('report.quality_print', 'practice'),
    'doctor.progress_notes':            ('report.progress_notes', 'practice'),
    'doctor.transcripts':               ('report.transcripts', 'practice'),
    'doctor.chats':                     ('report.chats', 'practice'),
    'doctor.comms':                     ('report.comms', 'practice'),
    'doctor.usage':                     ('report.usage', 'practice'),   # exports recorded by the route
    'my_settings.usage':                ('report.my_usage', 'practice'),
    'charts.scatter':                   ('charts.view', 'practice'),
    'charts.browse':                    ('charts.view', 'practice'),
    'charts.datasource_view':           ('charts.view', 'practice'),
    'governance.complaints_create':     ('governance.complaint_create', 'governance'),
    'governance.complaints_acknowledge': ('governance.complaint_step', 'governance'),
    'governance.complaints_transition': ('governance.complaint_step', 'governance'),
    'governance.complaints_disclosure': ('governance.complaint_step', 'governance'),
    'governance.complaints_close':      ('governance.complaint_step', 'governance'),
    'governance.complaints_void':       ('governance.complaint_step', 'governance'),
    'governance.complaints_save':       ('governance.complaint_edit', 'governance'),
    'governance.ae_create':             ('governance.adverse_event_create', 'governance'),
    'governance.ae_triage':             ('governance.adverse_event_step', 'governance'),
    'governance.ae_transition':         ('governance.adverse_event_step', 'governance'),
    'governance.ae_rca':                ('governance.adverse_event_step', 'governance'),
    'governance.ae_disclosure':         ('governance.adverse_event_step', 'governance'),
    'governance.ae_notify':             ('governance.adverse_event_step', 'governance'),
    'governance.ae_close':              ('governance.adverse_event_step', 'governance'),
    'governance.ae_void':               ('governance.adverse_event_step', 'governance'),
    'governance.ae_save':               ('governance.adverse_event_edit', 'governance'),
    'governance.register_index':        ('governance.register_view', 'governance'),
    'governance.register_report':       ('governance.register_report', 'governance'),
    'governance.permissions_grant':     ('governance.permission_change', 'governance'),
    'governance.permissions_revoke':    ('governance.permission_change', 'governance'),

    # ── Sign-in ──────────────────────────────────────────────────────────────
    ('auth.login_post', 'POST'):        ('auth.sign_in', 'administration'),
    'auth.logout':                      ('auth.sign_out', 'administration'),
}

# Any change made in these areas is recorded as one administration task, with
# the endpoint named in the detail — prompts, pipelines, providers, settings,
# users, mapping tables, maintenance.
ADMIN_BLUEPRINTS = frozenset({'setup', 'admin', 'prompt_manager', 'pipeline_run'})
ADMIN_METHODS = frozenset({'POST', 'PUT', 'DELETE'})
# pipeline_run also serves the run itself; that is recorded by the engine.
_NOT_ADMIN = frozenset({'pipeline_run.run_start'})


def task_for(endpoint: str | None, method: str) -> tuple[str, str] | None:
    """(task, area) for a request, or None if it is not a task."""
    if not endpoint:
        return None
    hit = TASKS.get((endpoint, method)) or TASKS.get(endpoint)
    if hit:
        return hit
    blueprint = endpoint.split('.', 1)[0]
    if (blueprint in ADMIN_BLUEPRINTS and method in ADMIN_METHODS
            and endpoint not in _NOT_ADMIN):
        return ('admin.change', 'administration')
    return None
