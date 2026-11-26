from flask import current_app, render_template, request, jsonify
from flask_login import login_required, current_user
from . import bp
from app.extensions import db


@bp.app_template_global('models_endpoint_hint')
def _models_endpoint_hint(base_url):
    """Setup → AI Providers: the Models URL placeholder for a provider (ADR-191)."""
    from app.services import ai_provider_service
    return ai_provider_service.models_endpoint_hint(base_url)


def _require_admin(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            from flask import abort
            abort(403)
        return f(*args, **kwargs)
    return decorated


def _compute_tab_statuses() -> dict:
    from app.models.system_setting import SystemSetting
    from app.models.ai_provider import AIProviderConfig, AIModel
    from app.models.external_service import ExternalServiceConfig
    from app.models.user import User

    s = {k: 'incomplete' for k in
         ('general', 'database', 'providers', 'models', 'tasks',
          'external', 'datasources', 'users', 'ai_scope', 'user_defaults', 'messaging', 'maintenance')}
    s['user_defaults'] = 'complete'  # registry defaults apply until the practice changes them
    try:
        from app.services import scope_service
        s['ai_scope'] = 'complete' if scope_service.is_enabled() else 'warning'
    except Exception:
        s['ai_scope'] = 'warning'

    try:
        name = SystemSetting.get('general.practice_name', '')
        s['general'] = 'complete' if name and name not in ('', 'MedUI Gen5 Clinic') else 'incomplete'
    except Exception:
        pass

    try:
        from flask import current_app
        import pyodbc
        conn_str = current_app.config.get('BPSDB_URI')
        if conn_str:
            pyodbc.connect(conn_str, timeout=3).close()
            s['database'] = 'complete'
            # Amber while the last check found the login can write (ADR-139; cache only).
            from app.services import bp_login_service
            last = bp_login_service.cached()
            if last and last.status == bp_login_service.CAN_WRITE:
                s['database'] = 'warning'
        # else stays 'incomplete'
    except Exception:
        from flask import current_app
        s['database'] = 'warning' if current_app.config.get('BPSDB_URI') else 'incomplete'

    try:
        s['providers'] = ('complete'
                          if AIProviderConfig.query.filter_by(is_enabled=True).count()
                          else 'incomplete')
    except Exception:
        pass

    try:
        total = AIModel.query.count()
        rec = AIModel.query.filter_by(is_enabled=True, is_recommended=True).count()
        s['models'] = 'complete' if rec else ('warning' if total else 'incomplete')
    except Exception:
        pass

    try:
        from app.models.system_setting import SystemSetting
        asr_ok = bool(SystemSetting.get('active_asr_model_id'))
        assist_ok = AIModel.query.filter_by(show_in_ai_assist=True, is_enabled=True).count() > 0
        s['tasks'] = 'complete' if (asr_ok and assist_ok) else ('warning' if (asr_ok or assist_ok) else 'incomplete')
    except Exception:
        pass

    try:
        # medui_os: the installation's own LiteParse counts without a saved entry.
        from app.services import ocr_service
        s['external'] = 'complete' if ocr_service.is_configured() else 'warning'
    except Exception:
        s['external'] = 'warning'

    try:
        from app.models.data_source import DataSource
        s['datasources'] = ('complete'
                            if DataSource.query.filter_by(is_active=True).count()
                            else 'warning')
    except Exception:
        s['datasources'] = 'warning'

    try:
        ok = (User.query.filter_by(is_active=True, is_local_admin=True).count() or
              User.query.filter(User.is_active.is_(True),
                                User.security_level >= 9).count())
        s['users'] = 'complete' if ok else 'warning'
    except Exception:
        pass

    try:
        from app.services import email_service, sms_service
        email_ok = email_service.is_configured()
        sms_ok   = sms_service.is_configured()
        s['messaging'] = ('complete'  if email_ok and sms_ok else
                          'warning'   if email_ok or  sms_ok else
                          'incomplete')
    except Exception:
        pass

    # Retention windows have defaults and purging is the administrator's choice, so there is
    # nothing left to set up (ADR-188 removed the automatic cleanup switch no code ever read).
    s['maintenance'] = 'complete'

    return s


# ── Main page ─────────────────────────────────────────────────────────────────

@bp.get('/')
@login_required
@_require_admin
def index():
    # ?tab=database opens the Database tab (where a login without Best Practice lands);
    # any other value opens General.
    if request.args.get('tab') == 'database':
        return render_template('setup/setup.html', active_tab='database',
                               tab_statuses=_compute_tab_statuses(), **_database_tab_data())
    return render_template(
        'setup/setup.html',
        active_tab='general',
        tab_statuses=_compute_tab_statuses(),
        **_general_tab_data(),
    )


# ── HTMX tab routes ────────────────────────────────────────────────────────────

@bp.get('/tab/general')
@login_required
@_require_admin
def tab_general():
    return render_template('setup/partials/tab_general.html', **_general_tab_data())


def _general_tab_data(**extra) -> dict:
    from datetime import datetime
    from flask import current_app
    from app.models.system_setting import SystemSetting
    from app.services import practice_time
    zone_set = (SystemSetting.get(practice_time.SETTING_KEY, '') or '').strip()
    return {
        'practice_name':  SystemSetting.get('general.practice_name', ''),
        'practice_phone': SystemSetting.get('general.practice_phone', ''),
        'scribe_key_set': bool(current_app.config.get('SCRIBE_ENCRYPTION_KEY')),
        # Practice timezone (ADR-101): what's set here, the installation's, and the result.
        'tz_choices': practice_time.CHOICES,
        'tz_set': zone_set,
        'tz_installation': practice_time.installation_zone(),
        'tz_current': current_app.config.get('PRACTICE_TIMEZONE'),
        'tz_now': datetime.now().strftime('%a %-d %b %Y, %H:%M'),
        # The HbA1c and eGFR results badges are each user's own setting (ADR-166), not here.
        'criterion_review': SystemSetting.get('clinical.criterion_review', True),             # ADR-109
        **extra,
    }


@bp.post('/general/save')
@login_required
@_require_admin
def general_save():
    from app.models.system_setting import SystemSetting
    name = request.form.get('general.practice_name', '').strip()
    phone = request.form.get('general.practice_phone', '').strip()
    if name:
        SystemSetting.set('general.practice_name', name)
    if phone is not None:
        SystemSetting.set('general.practice_phone', phone)
    # Practice timezone (ADR-101): a listed zone, another zone typed in, or blank for the
    # installation's. Applied to this process at once; other front-ends within a minute.
    from flask import current_app
    from app.services import practice_time
    choice = request.form.get('tz_choice', '').strip()
    typed = request.form.get('tz_other', '').strip() if choice == 'other' else choice
    zone = practice_time.normalise(typed) if typed else ''
    if typed and not zone:
        return render_template('setup/partials/tab_general.html', **_general_tab_data(
            flash_msg=f'"{typed}" isn\'t a timezone name. Use a place such as Australia/Melbourne.',
            flash_error=True))
    SystemSetting.set(practice_time.SETTING_KEY, zone,
                      description='Practice timezone; blank = the installation\'s (ADR-101)')
    practice_time.refresh(current_app._get_current_object(), force=True)
    return render_template('setup/partials/tab_general.html',
                           **_general_tab_data(flash_msg='Settings saved.'))


@bp.post('/general/patient-record/save')
@login_required
@_require_admin
def general_patient_record_save():
    from app.models.system_setting import SystemSetting
    from app.services import criterion_review_service
    SystemSetting.set(criterion_review_service.SETTING_KEY, 'criterion_review' in request.form,
                      description='Doctor Data: Criterion Review page and menu item (ADR-109)')
    return render_template('setup/partials/tab_general.html',
                           **_general_tab_data(record_msg='Saved.'))


@bp.post('/general/generate-scribe-key')
@login_required
@_require_admin
def general_generate_scribe_key():
    from cryptography.fernet import Fernet
    key = Fernet.generate_key().decode()
    return jsonify({'key': key})


@bp.get('/tab/database')
@login_required
@_require_admin
def tab_database():
    return render_template('setup/partials/tab_database.html', **_database_tab_data())


def _database_tab_data() -> dict:
    from flask import current_app
    conn_str = current_app.config.get('BPSDB_URI')
    status, message = 'incomplete', 'BPSDB not configured.'
    if conn_str:
        try:
            import pyodbc
            pyodbc.connect(conn_str, timeout=5).close()
            status, message = 'complete', 'Connection successful.'
        except Exception as exc:
            status, message = 'warning', str(exc)
    login = None
    if status == 'complete':
        from app.services import bp_login_service
        login = bp_login_service.check(force=True)     # fresh each time the tab opens (ADR-139)
    return dict(
        db_status=status,
        db_message=message,
        bpsdb_configured=bool(conn_str),
        login=login,
    )


@bp.get('/tab/providers')
@login_required
@_require_admin
def tab_providers():
    from app.services import ai_provider_service as svc
    from app.models.ai_provider import AIModel
    from app.models.system_setting import SystemSetting
    inference_models = AIModel.query.filter_by(is_enabled=True, is_asr=False).join(AIModel.provider).all()
    local_models     = [m for m in inference_models if m.provider.is_local]
    return render_template('setup/partials/provider_list.html',
                           providers=svc.get_all_providers(),
                           presets=svc.get_all_presets(),
                           inference_models=inference_models,
                           local_models=local_models,
                           default_model_id=SystemSetting.get('default_model_id'),
                           default_local_model_id=SystemSetting.get('default_local_model_id'),
                           default_chatbot_model_id=SystemSetting.get('default_chatbot_model_id'),
                           default_chatbot_local_model_id=SystemSetting.get('default_chatbot_local_model_id'))


@bp.post('/ai/defaults')
@login_required
@_require_admin
def ai_save_defaults():
    from app.models.ai_provider import AIModel
    from app.models.system_setting import SystemSetting

    def _save_model_pref(key: str, form_key: str, local_only: bool = False) -> None:
        raw = request.form.get(form_key, '').strip()
        if not raw:
            SystemSetting.set(key, None)
            return
        model_id = int(raw)
        q = AIModel.query.filter_by(id=model_id, is_enabled=True, is_asr=False)
        if local_only:
            from app.models.ai_provider import AIProviderConfig
            q = q.join(AIModel.provider).filter(AIProviderConfig.is_local.is_(True))
        if not q.first():
            return
        SystemSetting.set(key, model_id)

    _save_model_pref('default_model_id',       'default_model_id')
    _save_model_pref('default_local_model_id',  'default_local_model_id', local_only=True)
    _save_model_pref('default_chatbot_model_id',       'default_chatbot_model_id')
    _save_model_pref('default_chatbot_local_model_id', 'default_chatbot_local_model_id', local_only=True)
    db.session.commit()
    return _render_provider_list(flash='Default models saved.')


@bp.get('/tab/models')
@login_required
@_require_admin
def tab_models():
    from app.services import ai_provider_service as svc
    providers = svc.get_all_providers()
    models_by_provider = {p.id: svc.get_models_for_provider(p.id) for p in providers}
    return render_template('setup/partials/model_list.html',
                           providers=providers,
                           models_by_provider=models_by_provider)


@bp.get('/tab/tasks')
@login_required
@_require_admin
def tab_tasks():
    from app.models.ai_provider import AIModel
    from app.models.system_setting import SystemSetting
    asr_models    = AIModel.query.filter_by(is_asr=True, is_enabled=True).order_by(AIModel.display_name).all()
    assist_models = AIModel.query.filter_by(is_asr=False, is_enabled=True).order_by(AIModel.display_name).all()
    active_asr_id = SystemSetting.get('active_asr_model_id')
    return render_template(
        'setup/partials/tab_tasks.html',
        asr_models=asr_models,
        assist_models=assist_models,
        active_asr_id=int(active_asr_id) if active_asr_id else None,
    )


@bp.post('/tasks/set-asr-model')
@login_required
@_require_admin
def tasks_set_asr_model():
    from app.models.ai_provider import AIModel
    from app.models.system_setting import SystemSetting
    model_id = request.form.get('asr_model_id', '').strip()
    if model_id:
        model = AIModel.query.filter_by(id=int(model_id), is_asr=True, is_enabled=True).first()
        if not model:
            return jsonify({'error': 'Model not found or not an ASR model'}), 400
        SystemSetting.set('active_asr_model_id', int(model_id),
                          description='Active ASR model for voice transcription')
    else:
        SystemSetting.set('active_asr_model_id', None,
                          description='Active ASR model for voice transcription')
    return tab_tasks()


@bp.post('/tasks/toggle-ai-assist/<int:model_id>')
@login_required
@_require_admin
def tasks_toggle_ai_assist(model_id: int):
    from app.models.ai_provider import AIModel
    model = AIModel.query.get_or_404(model_id)
    if model.is_asr:
        return jsonify({'error': 'Cannot add ASR models to AI assist'}), 400
    model.show_in_ai_assist = not model.show_in_ai_assist
    db.session.commit()
    return tab_tasks()


@bp.post('/tasks/toggle-chatbot/<int:model_id>')
@login_required
@_require_admin
def tasks_toggle_chatbot(model_id: int):
    from app.models.ai_provider import AIModel
    model = AIModel.query.get_or_404(model_id)
    if model.is_asr:
        return jsonify({'error': 'Cannot add ASR models to chatbot'}), 400
    model.show_in_chatbot = not model.show_in_chatbot
    db.session.commit()
    return tab_tasks()


@bp.get('/tab/external')
@login_required
@_require_admin
def tab_external():
    from app.models.external_service import ExternalServiceConfig
    services = ExternalServiceConfig.query.all()
    return render_template('setup/partials/external_services.html', services=services)


@bp.get('/tab/datasources')
@login_required
@_require_admin
def tab_datasources():
    return _render_datasources()


def _render_datasources():
    from app.models.data_source import DataSource
    sources = DataSource.query.order_by(DataSource.source_type, DataSource.display_name).all()
    return render_template('setup/partials/tab_datasources.html', sources=sources)


@bp.post('/datasources/add')
@login_required
@_require_admin
def datasource_add():
    from app.models.data_source import DataSource
    key               = request.form.get('key',               '').strip()
    display_name      = request.form.get('display_name',      '').strip()
    location          = request.form.get('location',          '').strip()
    location_type     = request.form.get('location_type',     'http_url').strip()
    source_type       = request.form.get('source_type',       '').strip()
    description       = request.form.get('description',       '').strip() or None
    chart_config_json = request.form.get('chart_config_json', '').strip() or None
    if not all([key, display_name, location, source_type]):
        return '<div class="alert alert-danger">Key, Display Name, Location and Source Type are required.</div>', 400
    if DataSource.query.filter_by(key=key).first():
        return '<div class="alert alert-danger">A data source with that key already exists.</div>', 400
    ds = DataSource(key=key, display_name=display_name, location=location,
                    location_type=location_type, source_type=source_type,
                    description=description, chart_config_json=chart_config_json)
    db.session.add(ds)
    db.session.commit()
    return _render_datasources()


@bp.post('/datasources/<int:source_id>/delete')
@login_required
@_require_admin
def datasource_delete(source_id: int):
    from app.models.data_source import DataSource
    ds = DataSource.query.get_or_404(source_id)
    db.session.delete(ds)
    db.session.commit()
    return _render_datasources()


@bp.post('/datasources/<int:source_id>/toggle')
@login_required
@_require_admin
def datasource_toggle(source_id: int):
    from app.models.data_source import DataSource
    ds = DataSource.query.get_or_404(source_id)
    ds.is_active = not ds.is_active
    db.session.commit()
    return _render_datasources()


@bp.post('/datasources/<int:source_id>/pin')
@login_required
@_require_admin
def datasource_pin(source_id: int):
    from app.models.data_source import DataSource
    ds = DataSource.query.get_or_404(source_id)
    ds.show_in_topnav = not ds.show_in_topnav
    db.session.commit()
    return _render_datasources()


@bp.post('/datasources/<int:source_id>/update')
@login_required
@_require_admin
def datasource_update(source_id: int):
    from app.models.data_source import DataSource
    ds = DataSource.query.get_or_404(source_id)
    ds.display_name      = request.form.get('display_name', '').strip() or ds.display_name
    ds.source_type       = request.form.get('source_type',  '').strip() or ds.source_type
    ds.location_type     = request.form.get('location_type','').strip() or ds.location_type
    location             = request.form.get('location',     '').strip()
    if location:
        ds.location      = location
    ds.description       = request.form.get('description',  '').strip() or None
    ds.chart_config_json = request.form.get('chart_config_json', '').strip() or None
    db.session.commit()
    return _render_datasources()


@bp.get('/tab/users')
@login_required
@_require_admin
def tab_users():
    from app.models.user import User
    users = User.query.order_by(User.username).all()
    return render_template('setup/partials/tab_users.html', users=users)


@bp.get('/users/<int:user_id>/details-card')
@login_required
@_require_admin
def user_details_card(user_id):
    """A doctor's details from Best Practice, for an admin on Setup → Users (ADR-128)."""
    from flask import abort
    from app.models.user import User
    from app.services.doctor_profile_service import get_card, is_doctor
    user = db.session.get(User, user_id)
    if user is None or not is_doctor(user):
        abort(404)
    return render_template('my_settings/_details_card.html', card=get_card(user),
                           person=user, lookup=True)


@bp.get('/tab/ai-scope')
@login_required
@_require_admin
def tab_ai_scope():
    return _render_ai_scope()


def _render_ai_scope(**extra):
    from collections import Counter
    from app.models.system_setting import SystemSetting
    from app.models.prompt import SystemPrompt
    from app.services import scope_service
    prompts = SystemPrompt.query.filter_by(is_active=True).order_by(SystemPrompt.name).all()
    usage = Counter(p.scope_key or '' for p in prompts)
    return render_template('setup/partials/tab_ai_scope.html',
                           enabled=scope_service.is_enabled(),
                           default_key=scope_service.practice_default_key(),
                           wordings=scope_service.wordings(),
                           choices=scope_service.choices(),
                           prompts=prompts, usage=usage,
                           flag_instruction=scope_service.GUARDRAIL_INSTRUCTIONS,
                           notices=scope_service.wordings('notice'),
                           notices_enabled=scope_service.notices_enabled(),
                           check_mode=SystemSetting.get('scope.check_mode', 'record'),
                           generic_without_erasure=SystemSetting.get('chatbot.generic_without_erasure', 'warn'),
                           **extra)


@bp.post('/ai-scope/save')
@login_required
@_require_admin
def ai_scope_save():
    from app.services import scope_service
    try:
        scope_service.save_practice(request.form.get('enabled') == 'true',
                                    request.form.get('default_key', 'record'))
        from app.models.system_setting import SystemSetting
        SystemSetting.set(scope_service.NOTICES_ENABLED_KEY, request.form.get('notices_enabled') == 'true',
                          description='On-screen notices above AI output (ADR-082/088)')
        mode = request.form.get('check_mode', 'record')
        SystemSetting.set('scope.check_mode', mode if mode in ('off', 'record') else 'record',
                          description='Request check on what users type (ADR-089)')
        generic = request.form.get('generic_without_erasure', 'warn')
        SystemSetting.set('chatbot.generic_without_erasure', generic if generic in ('warn', 'off') else 'warn',
                          description='General chatbot without the PII Erasure workflow (ADR-098)')
    except ValueError as exc:
        return _render_ai_scope(flash_msg=str(exc), flash_ok=False)
    return _render_ai_scope(flash_msg='AI scope settings saved.', flash_ok=True)


@bp.post('/ai-scope/wording/<key>/save')
@login_required
@_require_admin
def ai_scope_wording_save(key):
    from app.services import scope_service
    kind = 'notice' if request.form.get('kind') == 'notice' else 'instruction'
    try:
        w = scope_service.edit_wording(key, request.form.get('label', ''),
                                       request.form.get('text', ''), current_user.id, kind=kind)
    except ValueError as exc:
        return _render_ai_scope(flash_msg=str(exc), flash_ok=False)
    return _render_ai_scope(flash_msg=f'Wording "{w.key}" saved as v{w.version}.', flash_ok=True)


@bp.get('/tab/user-defaults')
@login_required
@_require_admin
def tab_user_defaults():
    return _render_user_defaults()


def _render_user_defaults(**extra):
    from app.services import user_settings_service as user_settings
    return render_template('setup/partials/tab_user_defaults.html',
                           rows=user_settings.practice_rows(), **extra)


@bp.post('/user-defaults/save')
@login_required
@_require_admin
def user_defaults_save():
    from app.services import user_settings_service as user_settings
    errors = []
    for row in user_settings.practice_rows():
        pref = row['pref']
        if pref.kind == 'bool':
            default = request.form.get(f'default.{pref.key}', 'false')
        else:
            default = request.form.get(f'default.{pref.key}', row['default'])
        locked = request.form.get(f'may_change.{pref.key}') != 'true'
        try:
            user_settings.save_practice_entry(pref.key, default, locked)
        except ValueError as exc:
            errors.append(f'{pref.label}: {exc}')
    return _render_user_defaults(flash_msg='; '.join(errors) or 'User defaults saved.',
                                 flash_ok=not errors)


@bp.get('/tab/messaging')
@login_required
@_require_admin
def tab_messaging():
    return render_template('setup/partials/tab_messaging.html',
                           tab_data=_messaging_tab_data())


@bp.get('/tab/maintenance')
@login_required
@_require_admin
def tab_maintenance():
    return render_template('setup/partials/tab_maintenance.html',
                           **_maintenance_tab_data(), **_purge_counts())


def _maintenance_tab_data(**extra) -> dict:
    from app.models.system_setting import SystemSetting
    return {
        'retention_transcripts': SystemSetting.get('data.retention.transcripts', 30),
        'retention_messages':    SystemSetting.get('data.retention.messages', 90),
        'retention_chats':       SystemSetting.get('data.retention.chats', 90),
        'retention_runs':        SystemSetting.get('data.retention.pipeline_runs', 180),
        'hide_staff_records':    SystemSetting.get('privacy.hide_staff_records', False),
        'privacy_review_page':   SystemSetting.get('privacy.review_page', False),
        **extra,
    }


def _render_maintenance_tab(**extra):
    return render_template('setup/partials/tab_maintenance.html',
                           **_maintenance_tab_data(**extra))


def _purge_counts() -> dict:
    """What a purge would delete now under the retention windows (ADR-188)."""
    from app.services import retention_service
    n = retention_service.eligible()
    return {
        'purge_transcripts': n['transcripts'],
        'purge_messages':    n['messages'],
        'purge_chats':       n['chats'],
        'purge_runs':        n['runs'],
        'purge_runs_kept':   n['runs_kept'],
        'purge_total':       n['total'],
    }


@bp.post('/maintenance/save')
@login_required
@_require_admin
def maintenance_save():
    from app.models.system_setting import SystemSetting

    def _int(key, default):
        val = request.form.get(key, '').strip()
        try:
            return max(1, int(val))
        except ValueError:
            return default

    # Each section of the tab saves only its own settings (ADR-190); a post without a section
    # saves both, as before.
    section = request.form.get('section', '')
    if section in ('', 'retention'):
        SystemSetting.set('data.retention.transcripts',   _int('retention_transcripts', 30))
        SystemSetting.set('data.retention.messages',       _int('retention_messages', 90))
        SystemSetting.set('data.retention.chats',          _int('retention_chats', 90))
        SystemSetting.set('data.retention.pipeline_runs',  _int('retention_runs', 180))
    if section in ('', 'privacy'):
        SystemSetting.set('privacy.hide_staff_records', 'hide_staff_records' in request.form)
        SystemSetting.set('privacy.review_page', 'privacy_review_page' in request.form,
                          description='Admin → Privacy Review page (ADR-120)')
    msg = {'retention': 'Retention saved.', 'privacy': 'Privacy settings saved.'}.get(section,
                                                                                 'Settings saved.')
    return _render_maintenance_tab(flash_msg=msg, flash_ok=True, **_purge_counts())


@bp.post('/maintenance/purge')
@login_required
@_require_admin
def maintenance_purge():
    from flask import current_app
    from app.services import retention_service
    n = retention_service.purge()
    current_app.logger.info(
        'maintenance_purge: deleted %d transcripts, %d messages, %d chats, %d runs; '
        'kept %d referenced runs',
        n['transcripts'], n['messages'], n['chats'], n['runs'], n['runs_kept'],
    )
    kept = (f" {n['runs_kept']} older AI run record(s) kept, because a chat, care plan, message "
            f"or other record still refers to them." if n['runs_kept'] else '')
    return _render_maintenance_tab(
        flash_msg=f"Purge complete — {n['total']} row(s) deleted "
                  f"({n['transcripts']} transcripts, {n['messages']} messages, {n['chats']} chats, "
                  f"{n['runs']} pipeline runs).{kept}",
        flash_ok=True,
        **_purge_counts(),
    )


@bp.get('/maintenance/preview')
@login_required
@_require_admin
def maintenance_preview():
    return _render_maintenance_tab(**_purge_counts())


# ── Provider CRUD ──────────────────────────────────────────────────────────────

@bp.post('/providers/add-preset')
@login_required
@_require_admin
def provider_add_preset():
    from app.services import ai_provider_service as svc
    preset_key = request.form.get('preset_key', '')
    overrides = {
        'name':     request.form.get('name', '').strip() or None,
        'base_url': request.form.get('base_url', '').strip() or None,
        'api_key':  request.form.get('api_key', '').strip() or None,
        'is_local': request.form.get('is_local') == '1',
        'notes':    request.form.get('notes', '').strip() or None,
    }
    try:
        svc.create_from_preset(preset_key, overrides)
    except svc.ProviderError as exc:
        return _render_provider_list(provider_error=str(exc))
    except Exception as exc:
        db.session.rollback()
        current_app.logger.error('Adding a provider failed: %s', exc)
        return _render_provider_list(provider_error=f'The provider could not be added: {exc}')
    return _render_provider_list()


@bp.post('/providers/add-custom')
@login_required
@_require_admin
def provider_add_custom():
    from app.services import ai_provider_service as svc
    data = {
        'name':                    request.form.get('name', '').strip(),
        'provider_key':            request.form.get('provider_key', '').strip(),
        'provider_type':           request.form.get('provider_type', 'openai_compatible'),
        'base_url':                request.form.get('base_url', '').strip(),
        'is_local':                request.form.get('is_local') == '1',
        'api_key':                 request.form.get('api_key', '').strip() or None,
        'notes':                   request.form.get('notes', '').strip() or None,
        'supports_model_fetching': request.form.get('supports_model_fetching') == '1',
    }
    try:
        svc.create_custom(data)
    except svc.ProviderError as exc:
        return _render_provider_list(provider_error=str(exc))
    except Exception as exc:
        db.session.rollback()
        current_app.logger.error('Adding a provider failed: %s', exc)
        return _render_provider_list(provider_error=f'The provider could not be added: {exc}')
    return _render_provider_list()


@bp.post('/providers/<int:provider_id>/update')
@login_required
@_require_admin
def provider_update(provider_id: int):
    from app.services import ai_provider_service as svc
    data = {
        'name':                    request.form.get('name', '').strip(),
        'base_url':                request.form.get('base_url', '').strip(),
        'provider_type':           request.form.get('provider_type', 'openai_compatible'),
        'models_endpoint':         request.form.get('models_endpoint', '').strip(),
        'is_local':                request.form.get('is_local') == '1',
        'supports_model_fetching': request.form.get('supports_model_fetching') == '1',
        'notes':                   request.form.get('notes', '').strip() or None,
    }
    api_key = request.form.get('api_key', '').strip()
    if api_key:
        data['api_key'] = api_key
    try:
        svc.update_provider(provider_id, data)
    except Exception as exc:
        return f'<div class="alert alert-danger">{exc}</div>', 400
    return _render_provider_list()


@bp.post('/providers/<int:provider_id>/toggle')
@login_required
@_require_admin
def provider_toggle(provider_id: int):
    from app.models.ai_provider import AIProviderConfig
    cfg = db.session.get(AIProviderConfig, provider_id)
    if not cfg:
        return jsonify({'error': 'Not found'}), 404
    cfg.is_enabled = not cfg.is_enabled
    db.session.commit()
    return jsonify({'enabled': cfg.is_enabled})


@bp.post('/providers/<int:provider_id>/delete')
@login_required
@_require_admin
def provider_delete(provider_id: int):
    from app.services import ai_provider_service as svc
    svc.delete_provider(provider_id)
    return _render_provider_list()


@bp.post('/providers/<int:provider_id>/test')
@login_required
@_require_admin
def provider_test(provider_id: int):
    from app.services import ai_provider_service as svc
    result = svc.test_connection(provider_id)
    ok = result['status'] == 'ok'
    colour = 'var(--success)' if ok else 'var(--danger)'
    icon = '✓' if ok else '✗'
    return (f'<span style="color:{colour}; font-size:0.75rem;">'
            f'{icon} {result.get("message","")} ({result.get("latency_ms",0)}ms)</span>')


@bp.post('/providers/<int:provider_id>/fetch-models')
@login_required
@_require_admin
def provider_fetch_models(provider_id: int):
    from app.services import ai_provider_service as svc
    result = svc.fetch_models(provider_id)
    if result.get('error'):
        return f'<span style="color:var(--danger); font-size:0.75rem;">✗ {result["error"]}</span>'
    return (f'<span style="color:var(--success); font-size:0.75rem;">'
            f'✓ {result["added"]} added, {result["updated"]} updated</span>')


# ── Model management ───────────────────────────────────────────────────────────

@bp.post('/providers/<int:provider_id>/models/disable-all')
@login_required
@_require_admin
def provider_models_disable_all(provider_id: int):
    from app.services import ai_provider_service as svc
    svc.disable_all_models(provider_id)
    return _render_model_list()


@bp.post('/providers/<int:provider_id>/models/delete-disabled')
@login_required
@_require_admin
def provider_models_delete_disabled(provider_id: int):
    from app.services import ai_provider_service as svc
    result = svc.delete_disabled_models(provider_id)
    flash = None
    if result['skipped']:
        names = '; '.join(
            f"{s['model'].display_name} (used by {', '.join(s['blockers'])})"
            for s in result['skipped']
        )
        flash = {
            'level': 'warning',
            'text': (f"Deleted {result['deleted_count']} disabled model(s). "
                     f"{len(result['skipped'])} skipped — still in use: {names}"),
        }
    elif result['deleted_count']:
        flash = {'level': 'success', 'text': f"Deleted {result['deleted_count']} disabled model(s)."}
    return _render_model_list(flash=flash)


@bp.post('/models/<int:model_id>/delete')
@login_required
@_require_admin
def model_delete(model_id: int):
    from app.services import ai_provider_service as svc
    result = svc.delete_model(model_id)
    flash = None
    if not result['deleted'] and result['blockers']:
        flash = {'level': 'warning', 'text': f"Cannot delete — still in use: {', '.join(result['blockers'])}"}
    return _render_model_list(flash=flash)


@bp.post('/models/add')
@login_required
@_require_admin
def model_add():
    from app.services import ai_provider_service as svc
    data = {
        'provider_id':    request.form.get('provider_id', ''),
        'model_id':       request.form.get('model_id', '').strip(),
        'display_name':   request.form.get('display_name', '').strip() or None,
        'task_tier':      request.form.get('task_tier', '').strip() or None,
        'context_length': request.form.get('context_length', '').strip() or None,
    }
    try:
        svc.add_manual_model(data)
    except Exception as exc:
        return f'<p style="color:var(--danger);font-size:0.8rem;padding:0.5rem 0">{exc}</p>', 400
    return _render_model_list()


@bp.post('/models/<int:model_id>/toggle')
@login_required
@_require_admin
def model_toggle(model_id: int):
    from app.services import ai_provider_service as svc
    m = svc.toggle_model(model_id)
    return jsonify({'enabled': m.is_enabled})


@bp.post('/models/<int:model_id>/asr')
@login_required
@_require_admin
def model_set_asr(model_id: int):
    from app.services import ai_provider_service as svc
    m = svc.set_model_asr(model_id, request.form.get('is_asr') == '1')
    return jsonify({'is_asr': m.is_asr})


@bp.post('/models/<int:model_id>/tier')
@login_required
@_require_admin
def model_set_tier(model_id: int):
    from app.services import ai_provider_service as svc
    m = svc.set_model_tier(model_id, request.form.get('tier') or None)
    return jsonify({'task_tier': m.task_tier})


@bp.post('/models/<int:model_id>/recommended')
@login_required
@_require_admin
def model_set_recommended(model_id: int):
    from app.services import ai_provider_service as svc
    m = svc.set_model_recommended(model_id, request.form.get('recommended') == '1')
    return jsonify({'is_recommended': m.is_recommended})


@bp.post('/models/<int:model_id>/params')
@login_required
@_require_admin
def model_set_request_params(model_id: int):
    from app.services import ai_provider_service as svc
    try:
        m = svc.set_model_request_params(model_id, request.form.get('request_params'))
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    return jsonify({'request_params': m.request_params})


@bp.post('/models/<int:model_id>/speaker-turns')
@login_required
@_require_admin
def model_set_speaker_turns(model_id: int):
    from app.services import ai_provider_service as svc
    try:
        m = svc.set_model_speaker_turns(model_id, request.form.get('speaker_turns'))
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    return jsonify({'speaker_turns': m.speaker_turns})


# ── Messaging ─────────────────────────────────────────────────────────────────

def _pit_container_dir() -> str:
    """Where a Docker installation shows the PIT share inside the app (medui_os: /pit)."""
    import os
    return os.environ.get('PIT_CONTAINER_DIR', '')


def _messaging_tab_data() -> dict:
    from app.models.system_setting import SystemSetting
    from app.services import email_service, sms_service
    return {
        'email.smtp_host':       SystemSetting.get('email.smtp_host', ''),
        'email.smtp_port':       SystemSetting.get('email.smtp_port', 587),
        'email.smtp_username':   SystemSetting.get('email.smtp_username', ''),
        'email.sender_name':     SystemSetting.get('email.sender_name', ''),
        'email.sender_address':  SystemSetting.get('email.sender_address', ''),
        'email.use_tls':         SystemSetting.get('email.use_tls', True),
        'email_password_set':    email_service.password_is_set(),
        'email_password_from_env': email_service.password_from_env(),
        'sms.smtp_host':         SystemSetting.get('sms.smtp_host', ''),
        'sms.smtp_port':         SystemSetting.get('sms.smtp_port', 25),
        'sms.sender_address':    SystemSetting.get('sms.sender_address', ''),
        'sms.recipient_template': SystemSetting.get('sms.recipient_template', ''),
        'sms.requires_auth':     SystemSetting.get('sms.requires_auth', False),
        'sms.smtp_username':     SystemSetting.get('sms.smtp_username', ''),
        'sms.use_tls':           SystemSetting.get('sms.use_tls', False),
        'sms_password_set':      sms_service.sms_password_is_set(),
        'pit_export_path':       SystemSetting.get('pit_export_path', ''),
        'pit_container_dir':     _pit_container_dir(),
        'ai.provenance_footer':  SystemSetting.get('ai.provenance_footer', False),
        'ai.provenance_include_model': SystemSetting.get('ai.provenance_include_model', False),
    }


def _render_messaging_tab(**flash_kwargs):
    return render_template('setup/partials/tab_messaging.html',
                           tab_data=_messaging_tab_data(), **flash_kwargs)


@bp.post('/messaging/save-email')
@login_required
@_require_admin
def messaging_save_email():
    from app.models.system_setting import SystemSetting
    from app.services.email_service import _set_secret
    for key in ('email.smtp_host', 'email.smtp_username',
                'email.sender_name', 'email.sender_address'):
        val = request.form.get(key, '').strip()
        if val:
            SystemSetting.set(key, val)
    port = request.form.get('email.smtp_port', '').strip()
    if port.isdigit():
        SystemSetting.set('email.smtp_port', int(port))
    SystemSetting.set('email.use_tls', 'email.use_tls' in request.form)
    pw = request.form.get('email.smtp_password', '').strip()
    if pw:
        _set_secret('email.smtp_password', pw)
    return _render_messaging_tab(flash_email='Email settings saved.', flash_email_ok=True)


@bp.post('/messaging/save-sms')
@login_required
@_require_admin
def messaging_save_sms():
    from app.models.system_setting import SystemSetting
    from app.services.sms_service import _set_secret as sms_set_secret
    for key in ('sms.smtp_host', 'sms.sender_address',
                'sms.recipient_template', 'sms.smtp_username'):
        val = request.form.get(key, '').strip()
        if val:
            SystemSetting.set(key, val)
    port = request.form.get('sms.smtp_port', '').strip()
    if port.isdigit():
        SystemSetting.set('sms.smtp_port', int(port))
    SystemSetting.set('sms.requires_auth', 'sms.requires_auth' in request.form)
    SystemSetting.set('sms.use_tls',       'sms.use_tls'       in request.form)
    pw = request.form.get('sms.smtp_password', '').strip()
    if pw:
        sms_set_secret('sms.smtp_password', pw)
    return _render_messaging_tab(flash_sms='SMS settings saved.', flash_sms_ok=True)


@bp.post('/messaging/save-pit')
@login_required
@_require_admin
def messaging_save_pit():
    from app.models.system_setting import SystemSetting
    from app.utils.pit_utils import folder_problem
    folder = request.form.get('pit_export_path', '').strip()
    SystemSetting.set('pit_export_path', folder)
    SystemSetting.set('ai.provenance_footer', 'ai.provenance_footer' in request.form)
    SystemSetting.set('ai.provenance_include_model', 'ai.provenance_include_model' in request.form)
    problem = folder_problem(folder) if folder else None
    if problem:
        return _render_messaging_tab(flash_pit=f'PIT settings saved, but: {problem}', flash_pit_ok=False)
    return _render_messaging_tab(flash_pit='PIT settings saved.', flash_pit_ok=True)


@bp.post('/messaging/test-email')
@login_required
@_require_admin
def messaging_test_email():
    from app.services import email_service
    from app.models.system_setting import SystemSetting
    host     = request.form.get('email.smtp_host', '').strip()
    port     = int(request.form.get('email.smtp_port', 587) or 587)
    username = request.form.get('email.smtp_username', '').strip()
    password = request.form.get('email.smtp_password', '').strip()
    use_tls  = 'email.use_tls' in request.form
    sender   = request.form.get('email.sender_address', '').strip()
    if not password:
        import os
        password = os.environ.get('EMAIL_SMTP_PASSWORD') or email_service._get_secret('email.smtp_password')
    result = email_service.test_connection(host, port, username, password, use_tls, sender)
    return jsonify(result)


@bp.post('/messaging/test-sms')
@login_required
@_require_admin
def messaging_test_sms():
    from app.services import sms_service
    number = request.form.get('mobile_number', '').strip()
    if not number:
        return jsonify({'ok': False, 'message': 'No mobile number provided.'})
    return jsonify(sms_service.test(number))


# ── User management ───────────────────────────────────────────────────────────

@bp.post('/users/<int:user_id>/update')
@login_required
@_require_admin
def user_update(user_id: int):
    from app.models.user import User
    u = db.session.get(User, user_id)
    if not u:
        return '<div class="alert alert-danger">User not found.</div>', 404

    raw_internal = request.form.get('bpsdb_internal_id', '').strip()
    u.bpsdb_internal_id = int(raw_internal) if raw_internal.isdigit() else None

    u.title = request.form.get('title', '').strip() or None

    # ADR-106: the name MedUI shows instead of the BP name (BP users only).
    if u.bpsdb_user_id and 'preferred_name' in request.form:
        from app.services import practitioner_names
        u.preferred_name = ' '.join(request.form.get('preferred_name', '').split())[:120] or None
        practitioner_names.apply_to_user(u)

    grant_admin = request.form.get('is_local_admin') == '1'
    u.is_local_admin = grant_admin
    if grant_admin and u.security_level < 4:
        u.security_level = 9

    db.session.commit()
    users = User.query.order_by(User.username).all()
    return render_template('setup/partials/tab_users.html', users=users)


# ── External service CRUD ──────────────────────────────────────────────────────

def _render_external_list():
    from app.models.external_service import ExternalServiceConfig
    services = ExternalServiceConfig.query.order_by(ExternalServiceConfig.id).all()
    return render_template('setup/partials/external_services.html', services=services)


@bp.post('/external/add')
@login_required
@_require_admin
def external_add():
    from app.models.external_service import ExternalServiceConfig, ExternalServiceType
    data = request.form
    if data.get('service_type', 'ocr') != 'ocr':
        return 'Only OCR services are supported in this release.', 400
    try:
        svc = ExternalServiceConfig(
            display_name=data.get('display_name', '').strip(),
            service_type=ExternalServiceType(data.get('service_type', 'ocr')),
            base_url=data.get('base_url', '').strip(),
            health_check_path=data.get('health_check_path', '').strip() or '/health',
            api_path=data.get('api_path', '').strip() or None,
            auth_header_name=data.get('auth_header_name', '').strip() or 'X-API-KEY',
            notes=data.get('notes', '').strip() or None,
            is_enabled=True,
        )
        api_key = data.get('api_key', '').strip()
        if api_key:
            svc.api_key = api_key
        db.session.add(svc)
        db.session.commit()
    except Exception as exc:
        return f'<div class="alert alert-danger">{exc}</div>', 400
    return _render_external_list()


@bp.post('/external/<int:service_id>/update')
@login_required
@_require_admin
def external_update(service_id: int):
    from app.models.external_service import ExternalServiceConfig, ExternalServiceType
    svc = db.session.get(ExternalServiceConfig, service_id)
    if not svc:
        return '<div class="alert alert-danger">Service not found.</div>', 404
    data = request.form
    if data.get('service_type', 'ocr') != 'ocr':
        return 'Only OCR services are supported in this release.', 400
    try:
        svc.display_name = data.get('display_name', '').strip() or svc.display_name
        svc.service_type = ExternalServiceType(data.get('service_type', svc.service_type.value))
        svc.base_url = data.get('base_url', '').strip() or svc.base_url
        svc.health_check_path = data.get('health_check_path', '').strip() or '/health'
        svc.api_path = data.get('api_path', '').strip() or None
        svc.auth_header_name = data.get('auth_header_name', '').strip() or 'X-API-KEY'
        svc.notes = data.get('notes', '').strip() or None
        svc.is_enabled = data.get('is_enabled') == '1'
        api_key = data.get('api_key', '').strip()
        if api_key:
            svc.api_key = api_key
        elif data.get('clear_api_key') == '1':
            svc.api_key = None
        db.session.commit()
    except Exception as exc:
        return f'<div class="alert alert-danger">{exc}</div>', 400
    return _render_external_list()


@bp.post('/external/<int:service_id>/delete')
@login_required
@_require_admin
def external_delete(service_id: int):
    from app.models.external_service import ExternalServiceConfig
    svc = db.session.get(ExternalServiceConfig, service_id)
    if svc:
        db.session.delete(svc)
        db.session.commit()
    return _render_external_list()


@bp.post('/external/<int:service_id>/test')
@login_required
@_require_admin
def external_test(service_id: int):
    from app.models.external_service import ExternalServiceConfig
    import requests as _req
    svc = db.session.get(ExternalServiceConfig, service_id)
    if not svc:
        return '<span style="color:var(--danger); font-size:0.72rem;">✗ Not found</span>'
    path = (svc.api_path or '/parse').strip()
    if not path.startswith('/'):
        path = '/' + path
    url = svc.base_url.rstrip('/') + path
    headers = {}
    key = svc.api_key
    if key:
        headers[svc.auth_header_name or 'X-API-KEY'] = key
    try:
        resp = _req.post(url, headers=headers, timeout=8,
                         verify=current_app.config.get('OCR_CA_BUNDLE', True))
        if resp.status_code != 400:
            resp.raise_for_status()
            raise ValueError('Expected LiteParse to reject a missing file with HTTP 400')
        colour = 'var(--success)'
        msg = '✓ LiteParse is reachable'
    except _req.Timeout:
        colour = 'var(--danger)'
        msg = '✗ Timeout'
    except _req.ConnectionError:
        colour = 'var(--danger)'
        msg = '✗ Cannot connect'
    except _req.HTTPError as exc:
        colour = 'var(--warning)'
        msg = f'⚠ HTTP {exc.response.status_code}'
    except Exception as exc:
        colour = 'var(--danger)'
        msg = f'✗ {str(exc)[:80]}'
    return f'<span style="color:{colour}; font-size:0.72rem;">{msg}</span>'


# ── Helpers ────────────────────────────────────────────────────────────────────

def _render_model_list(flash: dict | None = None):
    from app.services import ai_provider_service as svc
    providers = svc.get_all_providers()
    models_by_provider = {p.id: svc.get_models_for_provider(p.id) for p in providers}
    return render_template('setup/partials/model_list.html',
                           providers=providers,
                           models_by_provider=models_by_provider,
                           flash_models=flash)


def _render_provider_list(flash: str = '', provider_error: str = ''):
    from app.services import ai_provider_service as svc
    from app.models.ai_provider import AIModel
    from app.models.system_setting import SystemSetting
    inference_models = AIModel.query.filter_by(is_enabled=True, is_asr=False).join(AIModel.provider).all()
    local_models     = [m for m in inference_models if m.provider.is_local]
    return render_template('setup/partials/provider_list.html',
                           providers=svc.get_all_providers(),
                           presets=svc.get_all_presets(),
                           inference_models=inference_models,
                           local_models=local_models,
                           default_model_id=SystemSetting.get('default_model_id'),
                           default_local_model_id=SystemSetting.get('default_local_model_id'),
                           default_chatbot_model_id=SystemSetting.get('default_chatbot_model_id'),
                           default_chatbot_local_model_id=SystemSetting.get('default_chatbot_local_model_id'),
                           flash_defaults=flash,
                           provider_error=provider_error)


# ── Administrator setup guide (renders docs/ for administrators) ─────────────

_GUIDE_DOCS = {
    'setup-guide': 'Administrator setup guide',
    'troubleshooting': 'Troubleshooting',
    'operations': 'Operations',
    'ocr': 'OCR',
    'seed-data': 'Seed data',
    'https': 'HTTPS for workstations',
    'cheatsheet': 'Cheat sheet',
    'repo/CHANGELOG': 'Changelog',
    'templates/practice-ai-use-policy': 'AI-use policy',
}


@bp.get('/guide')
@bp.get('/guide/<path:name>')
@login_required
@_require_admin
def guide(name: str = 'setup-guide'):
    # medui_os: every page under docs/ (and the few top-level ones it links to); the menu lists
    # the main ones. app/services/guide_docs.py renders them and keeps their links in the app.
    from flask import abort
    from app.services import guide_docs
    page = guide_docs.render(name)
    if page is None:
        abort(404)
    title, body = page
    return render_template('setup/guide.html', name=name, docs=_GUIDE_DOCS, title=title, body=body)
