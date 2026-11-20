"""What an installation still needs, for the administrator's home page (medui_os only).

Each item says whether a part of the installation is ready, with a link to the Setup tab that
changes it and to the guide section that explains it. The checks only read: settings, `.env`
switches, and a short connection to Best Practice (or the demo SQL Server) and to OCR.

States:
  ok       ready
  warn     not finished, or not working
  missing  the installation can't be used until this is done (database, an administrator)
  off      switched off on purpose (an optional feature); not counted against the installation
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from types import SimpleNamespace

from flask import current_app, request, url_for

OK, WARN, MISSING, OFF = 'ok', 'warn', 'missing', 'off'
CONNECT_TIMEOUT_S = 3


@dataclass
class Item:
    key: str
    label: str
    state: str
    detail: str
    setup_tab: str | None = None        # Setup tab slug (/setup/tab/<slug>), None for none
    guide: str | None = None            # 'doc' or 'doc#anchor' in the in-app guide
    why: str = ''                       # what it is needed for: the panel's ? popup

    @property
    def setup_url(self) -> str | None:
        if not self.setup_tab:
            return None
        return url_for('setup.index', tab=self.setup_tab)

    @property
    def guide_url(self) -> str | None:
        if not self.guide:
            return None
        name, _, anchor = self.guide.partition('#')
        return url_for('setup.guide', name=name) + (f'#{anchor}' if anchor else '')


# What each item is needed for, shown in the panel's ? popup.
WHY = {
    'practice': 'Required for accurate location-specific timestamps.',
    'database': 'Required to connect to your live BP data.',
    'database_demo': 'Required to show the demo practice\'s invented patients.',
    'https': 'Required to use MedUI from the practice\'s other computers, and for the '
             'scribe\'s microphone.',
    'ai': 'Required for any AI function. Switch it on once the practice has adopted its '
          'AI-use policy.',
    'ai_provider': 'Required for general AI queries and scribe functionality.',
    'voice': 'Required for scribe functionality.',
    'ocr': 'Required to read the text of scanned documents.',
    'pit': 'Required to save MedUI outputs back to BP via the user\'s inbox.',
    'messaging': 'Required to send patient emails and SMS messages.',
    'email': 'Required to send patient emails.',
    'sms': 'Required to send patient SMS messages.',
    'admins': 'Required to change MedUI\'s settings and users. A second administrator means a '
              'lost password doesn\'t lock the practice out.',
}


def is_demo() -> bool:
    """A demo installation (MEDUI_INSTANCE=demo in .env, set by ./install.sh --demo)."""
    return (os.environ.get('MEDUI_INSTANCE') or '').strip().lower() == 'demo'


def _flag(name: str) -> bool:
    return bool(current_app.config.get(name))


# ── the checks ────────────────────────────────────────────────────────────────

def _practice() -> Item:
    from app.models.system_setting import SystemSetting
    from app.services import practice_time
    name = (SystemSetting.get('general.practice_name', '') or '').strip()
    zone = practice_time.configured_zone()
    if name and name != 'MedUI Gen5 Clinic':
        return Item('practice', 'Practice name and timezone', OK, f'{name}; timezone {zone}.',
                    'general', 'setup-guide#two-places-settings-live')
    return Item('practice', 'Practice name and timezone', WARN,
                f'The practice name isn\'t set. Timezone {zone}: check it is the practice\'s.',
                'general', 'setup-guide#two-places-settings-live')


def _database(demo: bool) -> Item:
    label = 'Demo data (demo SQL Server)' if demo else 'Best Practice database'
    guide = 'setup-guide#a-demo-installation' if demo else 'setup-guide#2-best-practice-connection'
    uri = current_app.config.get('BPSDB_URI')
    if not uri:
        detail = ('The demo SQL Server isn\'t set up: rerun ./install.sh --demo.' if demo else
                  'Not set up: ./medui.sh bp sets the connection. Users other than local '
                  'administrators can\'t sign in until it works.')
        return Item('database', label, MISSING, detail, 'database', guide)
    try:
        import pyodbc
        pyodbc.connect(uri, timeout=CONNECT_TIMEOUT_S).close()
    except Exception as exc:                     # don't show the connection string or message
        return Item('database', label, MISSING,
                    f'Set up, but MedUI can\'t connect ({type(exc).__name__}). '
                    './medui.sh bp-check checks it again.', 'database', guide)
    from app.services import bp_login_service
    last = bp_login_service.cached()
    if last and last.status == bp_login_service.CAN_WRITE:
        return Item('database', label, WARN,
                    'Connected, but the login can change data: use a read-only login.',
                    'database', guide)
    return Item('database', label, OK, 'Connected.', 'database', guide)


def _https() -> Item:
    if request.is_secure or _flag('SESSION_COOKIE_SECURE'):
        return Item('https', 'HTTPS for the workstations', OK,
                    'On: workstations reach MedUI by its HTTPS address.',
                    None, 'setup-guide#3-https-for-the-workstations')
    return Item('https', 'HTTPS for the workstations', WARN,
                'Off: MedUI answers only on its own computer. ./medui.sh https turns it on.',
                None, 'setup-guide#3-https-for-the-workstations')


def _ai() -> list[Item]:
    from app.models.ai_provider import AIProviderConfig, AIModel
    from app.models.system_setting import SystemSetting
    if not _flag('AI_ENABLED'):
        return [Item('ai', 'AI', OFF,
                     'Switched off. ./medui.sh features turns it on, once the practice has '
                     'adopted its AI-use policy.', None, 'setup-guide#5-turn-on-ai')]
    items = [Item('ai', 'AI', OK, 'Switched on.', None, 'setup-guide#5-turn-on-ai')]
    providers = AIProviderConfig.query.filter_by(is_enabled=True).count()
    # Enabled text models of enabled providers ("Recommended" in Setup → Models is a label only).
    models = (AIModel.query.join(AIProviderConfig, AIModel.provider_id == AIProviderConfig.id)
              .filter(AIModel.is_enabled.is_(True), AIModel.is_asr.is_(False),
                      AIProviderConfig.is_enabled.is_(True)).count())
    if providers and models:
        items.append(Item('ai_provider', 'AI provider and model', OK,
                          f'{providers} provider{"s" if providers != 1 else ""}, '
                          f'{models} model{"s" if models != 1 else ""} enabled.',
                          'providers', 'setup-guide#6-add-an-ai-provider-and-models'))
    elif not providers:
        items.append(Item('ai_provider', 'AI provider and model', WARN,
                          'AI is on, but no AI provider is set up yet.',
                          'providers', 'setup-guide#6-add-an-ai-provider-and-models'))
    else:
        items.append(Item('ai_provider', 'AI provider and model', WARN,
                          'AI is on, but no model is enabled yet: Fetch Models in Providers, '
                          'then turn models on in Models.',
                          'models', 'setup-guide#6-add-an-ai-provider-and-models'))
    if SystemSetting.get('active_asr_model_id'):
        items.append(Item('voice', 'Voice model (scribe)', OK, 'Chosen.', 'tasks', None))
    else:
        items.append(Item('voice', 'Voice model (scribe)', WARN,
                          'No voice model chosen: the scribe can\'t transcribe.', 'tasks', None))
    return items


def _ocr() -> Item:
    from app.services import ocr_service
    if not _flag('OCR_ENABLED'):
        return Item('ocr', 'OCR (text from scanned documents)', OFF,
                    'Switched off. ./medui.sh features OCR_ENABLED=on turns it on.', None, 'ocr')
    cfg = ocr_service._get_config()
    if cfg is None:
        return Item('ocr', 'OCR (text from scanned documents)', WARN,
                    'Not in use: the OCR service saved in Setup is disabled, or no OCR address '
                    'is set. Scanned documents show no text.', 'external', 'ocr')
    import requests
    # The same check as Setup's Test button and the container's healthcheck: LiteParse has no
    # health endpoint, and answers a request without a file with HTTP 400.
    path = (getattr(cfg, 'api_path', None) or '/parse').strip()
    path = path if path.startswith('/') else '/' + path
    key = getattr(cfg, 'api_key', None)
    headers = {(getattr(cfg, 'auth_header_name', None) or 'X-API-KEY'): key} if key else {}
    saved = not isinstance(cfg, SimpleNamespace)
    try:
        resp = requests.post(cfg.base_url.rstrip('/') + path, headers=headers,
                             timeout=CONNECT_TIMEOUT_S,
                             verify=current_app.config.get('OCR_CA_BUNDLE') or True)
        if resp.status_code == 400:
            return Item('ocr', 'OCR (text from scanned documents)', OK,
                        'Answering.' if saved else
                        "Answering: the installation's own LiteParse, used automatically.",
                        'external', 'ocr')
    except Exception:
        pass
    return Item('ocr', 'OCR (text from scanned documents)', WARN,
                'Set up, but not answering: is the OCR container running?', 'external', 'ocr')


def _pit() -> Item:
    from app.models.system_setting import SystemSetting
    guide = 'setup-guide#9-other-optional-features'
    if not _flag('PIT_EXPORT_ENABLED'):            # counted: how MedUI's work reaches BP
        return Item('pit', 'Sending to Best Practice (PIT folder)', WARN,
                    'Switched off: ./medui.sh features PIT_EXPORT_ENABLED=on, then set the folder '
                    'in Setup → Messaging.', 'messaging', guide)
    folder = (SystemSetting.get('pit_export_path', '') or '').strip()
    if not folder:
        return Item('pit', 'Sending to Best Practice (PIT folder)', WARN,
                    'Switched on, but no folder is set.', 'messaging', guide)
    if not (os.path.isdir(folder) and os.access(folder, os.W_OK)):
        return Item('pit', 'Sending to Best Practice (PIT folder)', WARN,
                    'The folder isn\'t reachable or MedUI can\'t write to it.', 'messaging', guide)
    return Item('pit', 'Sending to Best Practice (PIT folder)', OK, 'Folder reachable.',
                'messaging', guide)


def _messaging() -> list[Item]:
    from app.services import email_service, sms_service
    guide = 'setup-guide#9-other-optional-features'
    if not _flag('MESSAGING_ENABLED'):             # counted: most practices' everyday use
        return [Item('messaging', 'Email and SMS', WARN,
                     'Switched off: ./medui.sh features MESSAGING_ENABLED=on, then set up email '
                     'and SMS in Setup → Messaging.', 'messaging', guide)]
    email = email_service.is_configured()
    sms = sms_service.is_configured()
    return [
        Item('email', 'Email (SMTP)', OK if email else WARN,
             'Set up.' if email else 'Messaging is on, but email isn\'t set up.', 'messaging', guide),
        Item('sms', 'SMS (by email-to-SMS)', OK if sms else WARN,
             'Set up.' if sms else 'Not set up.', 'messaging', guide),
    ]


def _admins() -> Item:
    from app.models.user import User
    local = User.query.filter_by(is_active=True, is_local_admin=True).count()
    bp = User.query.filter(User.is_active.is_(True), User.is_local_admin.is_(False),
                           User.security_level >= 9).count()
    if not local and not bp:
        return Item('admins', 'Administrators', MISSING,
                    'No active administrator: ./medui.sh admin creates one.', 'users',
                    'troubleshooting#administrator-access')
    if local + bp < 2:
        return Item('admins', 'Administrators', WARN,
                    'Only one administrator: add another so a lost password doesn\'t lock the '
                    'practice out (./medui.sh admin).', 'users',
                    'troubleshooting#administrator-access')
    return Item('admins', 'Administrators', OK, f'{local + bp} active.', 'users', None)


def items() -> list[Item]:
    """Every item, in the order the setup guide takes them. A failing check becomes a warning."""
    demo = is_demo()
    checks = [_practice, lambda: _database(demo), _https, _ai, _ocr]
    if not demo:                                 # nothing to send in a demo
        checks += [_pit, _messaging]
    checks += [_admins]
    result: list[Item] = []
    for check in checks:
        try:
            found = check()
        except Exception as exc:
            current_app.logger.warning('install_status: a check failed: %s', type(exc).__name__)
            found = Item('error', 'A check', WARN, 'Couldn\'t be completed.', None,
                         'troubleshooting')
        for item in (found if isinstance(found, list) else [found]):
            if not item.why:
                key = 'database_demo' if item.key == 'database' and demo else item.key
                item.why = WHY.get(key, '')
            result.append(item)
    return result


def summary(found: list[Item]) -> dict:
    counted = [i for i in found if i.state != OFF]
    ready = sum(1 for i in counted if i.state == OK)
    return {'ready': ready, 'total': len(counted), 'complete': ready == len(counted),
            'blocked': any(i.state == MISSING for i in found)}
