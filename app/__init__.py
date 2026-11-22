from flask import Flask, jsonify
from .config import config_map, DevelopmentConfig
from .extensions import db, migrate, csrf, login_manager


def create_app(config_name: str = 'production') -> Flask:
    app = Flask(__name__, instance_relative_config=False)

    if config_name not in config_map:
        raise ValueError(f'Unknown configuration: {config_name}')
    cfg = config_map[config_name]
    app.config.from_object(cfg)
    cfg.validate()

    _init_extensions(app)
    from .services import practice_time
    practice_time.init_app(app)            # the practice's timezone is local time (ADR-101)
    _register_blueprints(app)
    _register_commands(app)
    _register_filters(app)
    _register_context_processors(app)
    from app.features import register_features
    register_features(app)
    _register_privacy_gate(app)
    _register_usage_recording(app)
    _register_error_handlers(app)
    _register_health(app)
    _start_bp_login_check(app)

    return app


def _start_bp_login_check(app: Flask) -> None:
    # Is the Best Practice login read-only? Checked once after startup, logged (ADR-139).
    # Not for tests or `flask` commands.
    import os
    if app.testing or os.environ.get('FLASK_RUN_FROM_CLI') or not app.config.get('BPSDB_URI'):
        return
    from .services import bp_login_service
    bp_login_service.check_in_background(app)


def _init_extensions(app: Flask) -> None:
    db.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)
    login_manager.init_app(app)
    # Import models so their tables are registered with db.metadata before migrations run
    with app.app_context():
        import app.models  # noqa: F401


def _register_blueprints(app: Flask) -> None:
    from app.blueprints.main import bp as main_bp
    from app.blueprints.auth import bp as auth_bp
    from app.blueprints.admin import bp as admin_bp
    from app.blueprints.clinical import bp as clinical_bp
    from app.blueprints.doctor import bp as doctor_bp
    from app.blueprints.voice import bp as voice_bp
    from app.blueprints.pipeline_run import bp as pipeline_run_bp
    from app.blueprints.prompt_manager import bp as prompt_manager_bp
    from app.blueprints.viewer import bp as viewer_bp
    from app.blueprints.chatbot import bp as chatbot_bp
    from app.blueprints.inbox import bp as inbox_bp
    from app.blueprints.schedule import bp as schedule_bp
    from app.blueprints.clinical_comms import bp as clinical_comms_bp
    from app.blueprints.doc_library import bp as doc_library_bp
    from app.blueprints.setup import bp as setup_bp
    from app.blueprints.patient_api import bp as patient_api_bp
    from app.blueprints.practice_api import bp as practice_api_bp
    from app.blueprints.governance import bp as governance_bp
    from app.blueprints.charts import bp as charts_bp
    from app.blueprints.my_settings import bp as my_settings_bp
    from app.blueprints.help import bp as help_bp
    from app.blueprints.careplan import bp as careplan_bp
    from app.blueprints.protocols import bp as protocols_bp
    from app.blueprints.gpccmp import bp as gpccmp_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(help_bp, url_prefix='/help')
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(clinical_bp, url_prefix='/clinical')
    app.register_blueprint(doctor_bp, url_prefix='/doctor')
    app.register_blueprint(voice_bp, url_prefix='/voice')
    app.register_blueprint(pipeline_run_bp, url_prefix='/pipeline')
    app.register_blueprint(prompt_manager_bp, url_prefix='/admin/prompts')
    app.register_blueprint(viewer_bp, url_prefix='/clinical/viewer')
    app.register_blueprint(chatbot_bp, url_prefix='/clinical/chatbot')
    app.register_blueprint(inbox_bp, url_prefix='/inbox')
    app.register_blueprint(schedule_bp, url_prefix='/schedule')
    app.register_blueprint(clinical_comms_bp, url_prefix='/clinical/comms')
    app.register_blueprint(doc_library_bp, url_prefix='/library')
    app.register_blueprint(setup_bp, url_prefix='/setup')
    app.register_blueprint(patient_api_bp, url_prefix='/api')
    app.register_blueprint(practice_api_bp, url_prefix='/api/practice')
    app.register_blueprint(governance_bp, url_prefix='/governance')
    app.register_blueprint(charts_bp, url_prefix='/charts')
    app.register_blueprint(my_settings_bp, url_prefix='/me')
    app.register_blueprint(careplan_bp, url_prefix='/careplan')
    app.register_blueprint(protocols_bp, url_prefix='/admin/protocols')
    app.register_blueprint(gpccmp_bp, url_prefix='/gpccmp')


def _register_commands(app: Flask) -> None:
    from app.commands.seed import seed_cli
    from app.commands.data import data_cli
    app.cli.add_command(seed_cli)
    app.cli.add_command(data_cli)
    from app.commands.usage import usage_cli
    app.cli.add_command(usage_cli)
    from app.commands.install import install_cli
    app.cli.add_command(install_cli)
    from app.commands.help import help_cli
    app.cli.add_command(help_cli)
    from app.commands.protocol import protocol_cli
    app.cli.add_command(protocol_cli)
    from app.commands.gpccmp import gpccmp_cli
    app.cli.add_command(gpccmp_cli)


def _register_filters(app: Flask) -> None:
    from markupsafe import Markup
    import markdown as md_lib
    import re
    from datetime import datetime as _dt, timezone as _tz
    from zoneinfo import ZoneInfo

    @app.template_filter('markdown')
    def markdown_filter(text: str) -> Markup:
        return Markup(md_lib.markdown(text or '', extensions=['tables', 'fenced_code']))

    @app.template_filter('clinical_date')
    def clinical_date_filter(value) -> str:
        if not value:
            return '—'
        try:
            return value.strftime('%-d/%-m/%y')
        except AttributeError:
            s = str(value).strip()
            if not s:
                return '—'
            for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%d/%m/%y'):
                try:
                    return _dt.strptime(s[:10], fmt).strftime('%-d/%-m/%y')
                except ValueError:
                    continue
            return s

    @app.template_filter('short_date')
    def short_date_filter(value) -> str:
        if not value:
            return '—'
        try:
            return value.strftime('%d/%m/%Y')
        except Exception:
            return str(value)

    @app.template_filter('month_year')
    def month_year_filter(value) -> str:
        if not value:
            return ''
        try:
            return value.strftime('%-m/%y')
        except AttributeError:
            try:
                dt = _dt.strptime(str(value)[:10], '%Y-%m-%d')
                return dt.strftime('%-m/%y')
            except Exception:
                return str(value)

    @app.template_filter('weight_display')
    def weight_display_filter(value) -> str:
        if value is None:
            return ''
        try:
            f = float(value)
            return str(int(f)) if f == int(f) else f'{f:.1f}'
        except (ValueError, TypeError):
            return str(value)

    @app.template_filter('reformat_appt_date')
    def reformat_appt_date_filter(value) -> str:
        if not value or len(str(value)) < 16:
            return str(value) if value else ''
        try:
            dt = _dt.strptime(str(value)[:16], '%Y-%m-%d %H:%M')
            return dt.strftime('%-d/%-m/%y %H:%M') + str(value)[16:]
        except ValueError:
            return str(value)

    @app.template_filter('localdt')
    def localdt_filter(value, fmt: str = '%d/%m/%Y %H:%M') -> str:
        """Convert a UTC-stored datetime to local practice time for display."""
        if not value:
            return '—'
        try:
            from flask import current_app as _ca
            tz = ZoneInfo(_ca.config.get('PRACTICE_TIMEZONE', 'Australia/Brisbane'))
            dt = value if value.tzinfo else value.replace(tzinfo=_tz.utc)
            return dt.astimezone(tz).strftime(fmt)
        except Exception:
            return value.strftime(fmt)

    @app.template_filter('filesize')
    def filesize_filter(value) -> str:
        try:
            n = int(value)
        except (TypeError, ValueError):
            return ''
        if n < 1024:
            return f'{n}B'
        if n < 1024 * 1024:
            return f'{round(n / 1024)}KB'
        return f'{n / (1024 * 1024):.1f}MB'

    @app.template_filter('strip_tags')
    def strip_tags_filter(value) -> str:
        if not value:
            return ''
        s = str(value)
        s = re.sub(r'\{\\[^}]*\}', '', s)        # RTF groups
        s = re.sub(r'\\[a-z]+\-?\d*\s?', '', s)  # RTF control words
        s = re.sub(r'[{}]', '', s)                # remaining RTF braces
        s = re.sub(r'<[^>]+>', '', s)             # HTML tags
        s = re.sub(r'\s+', ' ', s)
        return s.strip()


_TOPNAV_PIPELINE_CACHE: dict    = {'value': None, 'expires': 0.0}
_TOPNAV_DATASOURCE_CACHE: dict  = {'value': None, 'expires': 0.0}


def _get_topnav_pipelines() -> list:
    import time as _time
    now = _time.monotonic()
    if now < _TOPNAV_PIPELINE_CACHE['expires']:
        return _TOPNAV_PIPELINE_CACHE['value']
    try:
        from app.models.pipeline import Pipeline, PipelineStatus
        from sqlalchemy import func, or_
        rows = (Pipeline.query
                .filter(
                    Pipeline.show_in_topnav == True,  # noqa: E712
                    Pipeline.status == PipelineStatus.active,
                )
                .order_by(Pipeline.name)
                .all())
        result = [{'id': p.id, 'name': p.name} for p in rows]
    except Exception:
        result = []
    _TOPNAV_PIPELINE_CACHE['value'] = result
    _TOPNAV_PIPELINE_CACHE['expires'] = now + 300
    return result


def _get_topnav_datasources() -> list:
    import time as _time
    now = _time.monotonic()
    if now < _TOPNAV_DATASOURCE_CACHE['expires']:
        return _TOPNAV_DATASOURCE_CACHE['value']
    try:
        from app.models.data_source import DataSource
        rows = (DataSource.query
                .filter_by(is_active=True, show_in_topnav=True)
                .order_by(DataSource.display_name)
                .all())
        result = [{'id': r.id, 'key': r.key, 'display_name': r.display_name,
                   'source_type': r.source_type} for r in rows]
    except Exception:
        result = []
    _TOPNAV_DATASOURCE_CACHE['value'] = result
    _TOPNAV_DATASOURCE_CACHE['expires'] = now + 300
    return result


def _register_context_processors(app: Flask) -> None:
    # `{% if u is doctor %}`: a BP user with a provider or prescriber number (ADR-128).
    from app.services.doctor_profile_service import is_doctor
    app.jinja_env.tests['doctor'] = is_doctor

    @app.context_processor
    def inject_globals():
        from .models import SystemSetting
        practice_name = SystemSetting.get('general.practice_name', '') or ''
        from .version import __version__
        return {
            'app_name':              app.config.get('APP_NAME', 'MedUI'),
            'app_version':           __version__,
            'practice_name':         practice_name,
            'topnav_pipelines':      _get_topnav_pipelines(),
            'topnav_datasources':    _get_topnav_datasources(),
            'ai_notice_text':        _ai_notice_text,
            'ai_notice_for':         _ai_notice_for,
            'help':                  _help_button,
            'criterion_review_enabled': _criterion_review_enabled,
            'privacy_review_enabled': _privacy_review_enabled,
            'bp_login_warning':      _bp_login_warning,
        }

    def _bp_login_warning():
        # For administrators: the last check found the BP login can write (ADR-139).
        # Reads the cache only; never a database call while a page renders.
        from flask_login import current_user
        from .services import bp_login_service
        if not (current_user.is_authenticated and current_user.is_admin):
            return None
        result = bp_login_service.cached()
        return result if result and result.status == bp_login_service.CAN_WRITE else None

    def _privacy_review_enabled() -> bool:
        # Admin → Privacy Review, switched in Setup → Maintenance (ADR-120).
        from .services import privacy_review_service
        return privacy_review_service.enabled()

    def _criterion_review_enabled() -> bool:
        # Doctor Data → Criterion Review, switched in Setup → General → Patient Record (ADR-109).
        from .services import criterion_review_service
        return criterion_review_service.enabled()

    def _help_button(ref: str):
        # A [?] that opens one help section in the side panel (ADR-102). Nothing for a
        # role that can't see the topic; a red marker if the section doesn't exist
        # (flask help check lists those too).
        from markupsafe import Markup, escape
        from flask_login import current_user
        from .services import help_service as hs
        topic, section = hs.find(ref)
        if not topic or not section:
            return Markup(f'<span class="help-btn help-btn-missing" title="No help section {escape(ref)}">?!</span>')
        if not current_user.is_authenticated or not hs.can_see(topic, current_user):
            return Markup('')
        label = escape(f'Help: {section.title}')
        return Markup(f'<button type="button" class="help-btn" data-help="{escape(ref)}" '
                      f'title="{label}" aria-label="{label}">?</button>')

    def _ai_notice_for(pipeline_id, page_default):
        # The notice key a workflow chose on its inference step, else the page's (ADR-088).
        from .services import scope_service
        return scope_service.pipeline_notice_key(pipeline_id, page_default)

    def _ai_notice_text(key):
        # Called only by pages that show an AI notice (components/ai_draft_notice.html).
        from .services import scope_service
        return scope_service.notice_text(key)


def _register_privacy_gate(app: Flask) -> None:
    """Enforce staff-record privacy on every route that exposes a patient_id."""
    from flask import request
    from flask_login import current_user

    @app.before_request
    def _patient_privacy_gate():
        if not getattr(current_user, 'is_authenticated', False):
            return
        view_args = request.view_args or {}
        patient_id = view_args.get('patient_id')
        if not patient_id:
            return
        from app.services.privacy_service import check_patient_access
        check_patient_access(int(patient_id))


def _register_usage_recording(app: Flask) -> None:
    """Record tasks in the permanent usage record (plans/usage_reporting_plan.md).

    Only endpoints listed in usage_tasks count; background calls, polling and
    static files are skipped by design. Recording never affects the response.
    """
    import time
    from flask import g, request
    from flask_login import current_user

    @app.before_request
    def _usage_start():
        g._usage_t0 = time.monotonic()
        # Captured now: signing out clears the user before the request ends.
        g._usage_uid = current_user.id if getattr(current_user, 'is_authenticated', False) else None

    @app.after_request
    def _usage_record(response):
        from app.services.usage_tasks import task_for
        hit = task_for(request.endpoint, request.method)
        if not hit:
            return response
        uid = g.get('_usage_uid') or (current_user.id if getattr(
            current_user, 'is_authenticated', False) else None)
        if not uid:
            return response                    # e.g. a failed sign-in
        task, area = hit
        if task == 'auth.sign_in' and response.status_code >= 400:
            return response
        from app.services import usage_service
        started = g.get('_usage_t0')
        usage_service.record_task(
            task, area, user_id=uid,
            patient_linked=bool((request.view_args or {}).get('patient_id')),
            outcome='ok' if response.status_code < 400 else (
                'blocked' if response.status_code == 403 else 'error'),
            duration_ms=int((time.monotonic() - started) * 1000) if started else None,
            workstation=request.remote_addr,
            detail={'endpoint': request.endpoint} if task == 'admin.change' else None)
        return response


def _register_error_handlers(app: Flask) -> None:
    from flask import render_template

    @app.errorhandler(403)
    def forbidden(exc):
        privacy = getattr(exc, 'description', '') == 'privacy_protected'
        return render_template('errors/403.html', privacy=privacy), 403


def _register_health(app: Flask) -> None:
    @app.get('/health')
    def health():
        from .version import __version__
        return jsonify({'status': 'ok', 'app': app.config.get('APP_NAME'), 'version': __version__})
