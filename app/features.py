"""Optional application capabilities, disabled until the installer enables them."""
from flask import current_app, request, render_template

AI_ENDPOINTS = {
    'clinical.ai_panel', 'clinical.ai_assist', 'charts.datasource_analyse',
    'doctor.transcripts', 'doctor.chats',
    # GPCCMP: targets, protocols and decisions work without AI; only the draft needs it.
    'gpccmp.plan_draft_start', 'gpccmp.draft_page', 'gpccmp.draft_status', 'gpccmp.draft_again',
}
AI_BLUEPRINTS = {'voice', 'chatbot', 'pipeline_run', 'prompt_manager'}


def register_features(app):
    @app.before_request
    def optional_feature_gate():
        if (request.blueprint in AI_BLUEPRINTS or request.endpoint in AI_ENDPOINTS or (request.endpoint or '').startswith('clinical.ai_')) and not current_app.config['AI_ENABLED']:
            return render_template('errors/feature_disabled.html', feature='AI and voice features'), 404
