import os
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import requests
from flask import Flask
from cryptography.fernet import Fernet

from app.services import ocr_service


@pytest.fixture
def context():
    app = Flask(__name__)
    app.config.update(OCR_TIMEOUT=90, OCR_CA_BUNDLE=True, AI_ENABLED=False,
                      MESSAGING_ENABLED=False, PIT_EXPORT_ENABLED=False,
                      SCRIBE_ENCRYPTION_KEY=Fernet.generate_key().decode())
    with app.app_context():
        yield app


def test_ocr_plain_text_contract(context, monkeypatch):
    cfg = SimpleNamespace(base_url='http://ocr:5707', api_path='/parse',
                          api_key='test-only', auth_header_name='X-API-KEY')
    monkeypatch.setattr(ocr_service, '_get_config', lambda: cfg)
    response = Mock(headers={'Content-Type': 'text/plain; charset=utf-8'}, text=' Extracted text ')
    post = Mock(return_value=response)
    monkeypatch.setattr(ocr_service.requests, 'post', post)
    assert ocr_service.extract_text(b'file', 'application/pdf') == 'Extracted text'
    args, kwargs = post.call_args
    assert args == ('http://ocr:5707/parse',)
    assert kwargs['params'] == {'text': 'true'}
    assert kwargs['files']['file'] == ('document.pdf', b'file', 'application/pdf')
    assert kwargs['verify'] is True
    assert kwargs['timeout'] == (5, 90)


@pytest.mark.parametrize('kind', ['timeout', 'html', 'unconfigured'])
def test_ocr_failure_does_not_become_document_text(context, monkeypatch, kind):
    cfg = SimpleNamespace(base_url='http://ocr:5707', api_path='/parse', api_key=None)
    monkeypatch.setattr(ocr_service, '_get_config', lambda: None if kind == 'unconfigured' else cfg)
    post = Mock(side_effect=requests.Timeout()) if kind == 'timeout' else Mock(
        return_value=Mock(headers={'Content-Type': 'text/html'}, text='<html>Error</html>'))
    monkeypatch.setattr(ocr_service.requests, 'post', post)
    assert ocr_service.extract_text(b'file', 'application/pdf') is None
    if kind == 'unconfigured':
        post.assert_not_called()


def test_ocr_unavailable_keeps_pdf_viewable(context, monkeypatch):
    from app.services.document_service import DocumentResult, extract_text
    monkeypatch.setattr(ocr_service, 'extract_text', lambda *a, **kw: None)
    result = DocumentResult('pdf', b'%PDF', 'application/pdf')
    assert 'OCR' in extract_text(result)
    assert result.content == b'%PDF'
    assert result.render_type == 'pdf'


def test_encrypted_columns_use_installation_key(context):
    from app.utils.encrypted_type import EncryptedText
    field = EncryptedText()
    encrypted = field.process_bind_param('Synthetic confidential text', None)
    assert 'Synthetic' not in encrypted
    assert field.process_result_value(encrypted, None) == 'Synthetic confidential text'


def test_optional_transports_block_before_network(context):
    from app.services.ai_providers.factory import get_provider
    from app.services.sms_service import _smtp_send
    from app.utils.pit_utils import pit_delivery
    with pytest.raises(RuntimeError, match='disabled'):
        get_provider(None, 'test')
    with pytest.raises(RuntimeError, match='disabled'):
        _smtp_send({}, 'nobody', None)
    with pytest.raises(RuntimeError, match='disabled'):
        pit_delivery('synthetic', 'test', 'Synthetic')


def test_missing_vaccine_tables_report_unavailable(context, monkeypatch):
    from app.services import vaccine_eligibility_service as svc
    monkeypatch.setattr(svc, '_get_mapping_rows', Mock(side_effect=ValueError('Missing table')))
    repo = Mock()
    result = svc.get_vaccine_eligibility(1, repo)
    assert result[0]['Status'] == 'Unavailable'
    assert 'not been assessed' in result[0]['Reason']
    repo.get_atomic_demographics.assert_not_called()


@pytest.fixture(scope='module')
def installed_app():
    url = os.environ.get('MEDUI_TEST_DATABASE_URL')
    if not url:
        pytest.skip('Set MEDUI_TEST_DATABASE_URL to a disposable PostgreSQL database')
    from sqlalchemy.engine import make_url
    assert make_url(url).database.endswith('_test'), 'Tests require a dedicated *_test database'
    from app.config import ProductionConfig
    old = ProductionConfig.SQLALCHEMY_DATABASE_URI
    ProductionConfig.SQLALCHEMY_DATABASE_URI = url
    from app import create_app
    app = create_app()
    app.config.update(TESTING=True, BPSDB_URI=None)
    runner = app.test_cli_runner()
    result = runner.invoke(args=['db', 'upgrade'])
    assert result.exit_code == 0, result.output
    try:
        yield app
    finally:
        ProductionConfig.SQLALCHEMY_DATABASE_URI = old
        from app.extensions import db
        with app.app_context():
            db.session.remove()
            db.engine.dispose()


def test_clean_install_is_idempotent(installed_app):
    from app.models.system_setting import SystemSetting
    from app.models.data_bundle import DataBundle
    runner = installed_app.test_cli_runner()
    assert runner.invoke(args=['install', 'defaults']).exit_code == 0
    with installed_app.app_context():
        SystemSetting.set('ui.default_theme', 'dark')
    assert runner.invoke(args=['install', 'defaults']).exit_code == 0
    with installed_app.app_context():
        assert SystemSetting.get('ui.default_theme') == 'dark'
        assert DataBundle.query.filter_by(name='clinical_context').count() == 1
    assert runner.invoke(args=['seed', 'import']).exit_code != 0
    check = runner.invoke(args=['db', 'check'])
    assert check.exit_code == 0, check.output


def test_admin_bootstrap_and_core_pages(installed_app):
    from app.models.user import User
    runner = installed_app.test_cli_runner()
    from uuid import uuid4
    username = 'test-admin-' + uuid4().hex[:8]
    args = ['install', 'admin', '--username', username, '--password', 'synthetic-test-password']
    result = runner.invoke(args=args)
    assert result.exit_code == 0, result.output
    assert runner.invoke(args=args).exit_code != 0
    with installed_app.app_context():
        admin = User.query.filter_by(username=username).one()
        assert admin.check_password('synthetic-test-password')
        uid = admin.id
    client = installed_app.test_client()
    assert client.get('/auth/login').status_code == 200
    with client.session_transaction() as session:
        session['_user_id'] = str(uid)
        session['_fresh'] = True
    for path in ['/', '/setup/', '/clinical/', '/library/', '/governance/complaints/', '/governance/adverse-events/']:
        response = client.get(path)
        assert response.status_code in (200, 302, 308), (path, response.status_code)
    home = client.get('/').get_data(as_text=True)
    for label in ['Document Summary', 'Fridge Temperatures', 'Quick Scribe', 'AI Assistant']:
        assert label not in home
    # The administrator setup guide renders docs/ for administrators, with links kept in the app.
    guide = client.get('/setup/guide')
    assert guide.status_code == 200
    text = guide.get_data(as_text=True)
    assert 'OCR_ENABLED' in text and 'AI_ENABLED=true' in text
    assert 'href="/setup/guide/troubleshooting#best-practice-connection"' in text
    assert 'Administrator setup guide' in client.get('/setup/').get_data(as_text=True)
    assert client.get('/setup/guide/release-status').status_code == 200      # any page under docs/
    assert client.get('/setup/guide/repo/CLAUDE').status_code == 404       # not documentation
    assert client.get('/setup/guide/no-such-page').status_code == 404
    # My settings, and Setup's AI scope and user defaults tabs (upstream ADR-085, ADR-087).
    for path in ['/me/settings', '/setup/tab/ai-scope', '/setup/tab/user-defaults']:
        assert client.get(path).status_code == 200, path
    assert 'Record — organise' in client.get('/setup/tab/ai-scope').get_data(as_text=True)
    assert installed_app.test_client().get('/setup/guide').status_code in (302, 401, 403)
    # The About page shows the intended purpose to anyone, signed in or not.
    for c in (client, installed_app.test_client()):
        about = c.get('/about')
        assert about.status_code == 200
        assert 'MedUI does not diagnose' in about.get_data(as_text=True)
    assert 'href="/about"' in home
    # In-app help (upstream ADR-102): the help centre and a topic, for an administrator.
    assert client.get('/help/').status_code == 200
    assert 'Who can log in' in client.get('/help/logging-in').get_data(as_text=True)
    # Flagged AI requests (upstream ADR-103): opens, with the practice-responsibility statement.
    flagged = client.get('/admin/flagged-ai')
    assert flagged.status_code == 200 and 'must be included in' in flagged.get_data(as_text=True)
    # Results-based badges and the criterion review start off (upstream ADR-104/107/109).
    from app.models.system_setting import SystemSetting
    with installed_app.app_context():
        for key in ('clinical.egfr_criterion_badge', 'clinical.hba1c_criterion_badge',
                    'clinical.criterion_review'):
            assert SystemSetting.get(key) is False, key
    assert client.get('/doctor/criterion-review').status_code == 404
    assert 'Criterion Review' not in home


def test_removed_routes_and_blocks(installed_app):
    from app.services.patient_json_service import BLOCK_LABELS
    endpoints = {rule.endpoint for rule in installed_app.url_map.iter_rules()}
    assert not any('doc_summary' in name or 'rollup_status' in name for name in endpoints)
    assert 'charts.fridge' not in endpoints
    for block in ['atomic_rollup', 'recent_atomic_rollup', 'inbox_recent_docs_rollup']:
        assert block not in BLOCK_LABELS
    client = installed_app.test_client()
    assert client.get('/voice/scribe').status_code == 404
    assert client.get('/api/patient/1/blocks').status_code == 403
    for template in installed_app.jinja_env.list_templates():
        installed_app.jinja_env.get_template(template)


def test_saved_disabled_ocr_overrides_environment(installed_app):
    from app.extensions import db
    from app.models.external_service import ExternalServiceConfig, ExternalServiceType
    with installed_app.app_context():
        service = ExternalServiceConfig(service_type=ExternalServiceType.ocr, display_name='Test',
                                        base_url='http://unused', is_enabled=False)
        db.session.add(service)
        db.session.commit()
        assert ocr_service._get_config() is None


def test_image_ocr_wraps_all_tiff_frames(context, monkeypatch):
    import io, pathlib, re
    from PIL import Image
    data = io.BytesIO()
    Image.new('RGB', (100, 100), 'white').save(data, format='TIFF', save_all=True,
        append_images=[Image.new('RGB', (100, 100), 'white')])
    monkeypatch.setattr(ocr_service, '_get_config', lambda: SimpleNamespace(
        base_url='http://ocr:5707', api_path='/parse', api_key=None))
    post = Mock(return_value=Mock(headers={'Content-Type': 'text/plain'}, text='pages'))
    monkeypatch.setattr(ocr_service.requests, 'post', post)
    assert ocr_service.extract_text(data.getvalue(), 'image/tiff') == 'pages'
    name, content, mime = post.call_args.kwargs['files']['file']
    assert mime == 'application/pdf'
    # One page object per TIFF frame (counted directly: no PDF library needed).
    assert content.startswith(b'%PDF')
    assert len(re.findall(rb'/Type\s*/Page(?!s)', content)) == 2


def test_portable_seed_package():
    from app.services.seed_service import load_package
    starter, reference = load_package()
    assert len(reference['drug_mappings']) == 402
    assert all(not row['approved'] for row in reference['drug_mappings'])
    assert all(not row['is_active'] for row in starter['message_templates'])
    assert all(not row['is_default'] for row in starter['system_prompts'])
    import json
    content = json.dumps(starter)
    # Practice-specific names and numbers are checked by the maintainers' private release scan,
    # so this public test doesn't have to carry them.
    for forbidden in ('{{bundle:', '{{LIVE_TRANSCRIPT}}', 'model_id', 'created_by_id',
                      'recent_atomic_rollup', 'inbox_recent_docs_rollup'):
        assert forbidden not in content.lower()
    from app.services.seed_service import load_admin_lists
    labels = load_admin_lists()['identifier_labels']
    assert labels['columns'] == ['label', 'shape', 'active', 'note']
    assert len(labels['rows']) == 17 and all(r['active'] == 'true' for r in labels['rows'])
    assert {'UR', 'URN', 'MRN', 'Accession', 'Patient ID'} <= {r['label'] for r in labels['rows']}


def test_seed_install_rollback_preservation_and_links(installed_app):
    import json
    from sqlalchemy import inspect, text
    from app.extensions import db
    from app.services.seed_service import install_seeds
    from app.models.prompt import UserPrompt
    from app.models.pipeline import Pipeline, PipelineStatus, RedactionPolicy
    from app.models.drug_mapping import DrugMapping
    from app.models.mapping_table import MappingTable
    from app.models.patient_message import MessageTemplate
    with installed_app.app_context():
        before = UserPrompt.query.count()
        install_seeds(dry_run=True, include_reference_data=True)
        assert UserPrompt.query.count() == before
        assert not inspect(db.engine).has_table('mapdata_vaccine_mapping')
        assert not inspect(db.engine).has_table('mapdata_identifier_labels')
        assert DrugMapping.query.count() == 0
        # A late error must also undo earlier inserts and reference-table DDL.
        db.session.execute(text('CREATE TABLE mapdata_nip_risk_mapping (id integer PRIMARY KEY)'))
        db.session.commit()
        with pytest.raises(ValueError, match='Inconsistent'):
            install_seeds(include_reference_data=True)
        assert UserPrompt.query.count() == before
        assert not inspect(db.engine).has_table('mapdata_vaccine_mapping')
        assert not inspect(db.engine).has_table('mapdata_identifier_labels')
        assert DrugMapping.query.count() == 0
        db.session.execute(text('DROP TABLE mapdata_nip_risk_mapping'))
        db.session.commit()
        install_seeds()
        assert DrugMapping.query.count() == 0
        assert not inspect(db.engine).has_table('mapdata_vaccine_mapping')
        # The identifier labels come with the starter install, and redaction uses them.
        assert MappingTable.query.filter_by(name='identifier_labels').one().row_count == 17
        from app.services import redaction_core, redaction_service
        redaction_core.forget()
        assert redaction_service.RedactionService.redact_identifier_labels(
            'Hospital UR Number: 123456') == 'Hospital UR Number: [ID Removed]'
        # Once installed, the list is the practice's: a rerun changes nothing in it.
        db.session.execute(text("DELETE FROM mapdata_identifier_labels WHERE label = 'Episode'"))
        db.session.execute(text("UPDATE mapdata_identifier_labels SET active = 'false' WHERE label = 'UR'"))
        db.session.commit()
        result = install_seeds(include_reference_data=True)
        assert result['drug_mappings']['added'] == 402
        unredacted = {'PII Erasure'}
        for pipeline in Pipeline.query.all():
            assert pipeline.status == PipelineStatus.draft
            assert pipeline.redaction_policy == (
                RedactionPolicy.redact_none if pipeline.name in unredacted else RedactionPolicy.redact_all)
            assert not pipeline.is_default and not pipeline.show_in_topnav
            for step in pipeline.steps:
                cfg = json.loads(step.config_json)
                assert 'model_id' not in cfg
                if step.node_type == 'prompt_assembly':
                    assert db.session.get(UserPrompt, cfg['user_prompt_id']) is not None
        # The generic chatbot: PII Erasure falls back to the local-only default model.
        erasure = Pipeline.query.filter_by(name='PII Erasure').one()
        assert [s.node_type for s in erasure.steps] == ['prompt_assembly', 'inference']
        assert json.loads(erasure.steps[1].config_json) == {'default_setting_key': 'default_local_model_id'}
        generic = Pipeline.query.filter_by(name='Chatbot Generic').one()
        assert [s.node_type for s in generic.steps] == ['prompt_assembly', 'inference', 'deredaction']
        assert json.loads(generic.steps[1].config_json) == {'default_setting_key': 'default_chatbot_model_id'}
        assert not DrugMapping.query.filter_by(approved=True).count()
        assert not MessageTemplate.query.filter_by(is_active=True).count()
        prompt = UserPrompt.query.first()
        prompt.prompt_text = 'Locally customised prompt'
        prompt.is_active = False
        drug = DrugMapping.query.first()
        drug.generic_name = 'Local reviewed mapping'
        drug.approved = True
        db.session.commit()
        result = install_seeds(include_reference_data=True)
        assert all(v['added'] == 0 for v in result.values())
        assert prompt.prompt_text == 'Locally customised prompt' and not prompt.is_active
        assert drug.generic_name == 'Local reviewed mapping' and drug.approved
        assert MappingTable.query.filter_by(name='vaccine_mapping').one().row_count == 57
        labels = dict(db.session.execute(text('SELECT label, active FROM mapdata_identifier_labels')).all())
        assert len(labels) == 16 and 'Episode' not in labels and labels['UR'] == 'false'
        from app.services.vaccine_eligibility_service import _build_vaccine_lookup, _build_risk_codes_by_disease
        lookup = _build_vaccine_lookup()
        assert len(lookup) == 57
        assert len(_build_risk_codes_by_disease(lookup)) == 2


def test_seed_checksum_rejects_modified_assets(tmp_path, monkeypatch):
    import shutil
    from app.services import seed_service
    for source in seed_service.ASSETS.glob('*.json'):
        shutil.copy(source, tmp_path / source.name)
    (tmp_path / 'starter.json').write_text('{}')
    monkeypatch.setattr(seed_service, 'ASSETS', tmp_path)
    with pytest.raises(ValueError, match='checksum mismatch'):
        seed_service.load_package()


def _package_with(tmp_path, monkeypatch, change):
    import hashlib, json, shutil
    from app.services import seed_service
    for source in seed_service.ASSETS.glob('*.json'):
        shutil.copy(source, tmp_path / source.name)
    starter = json.loads((tmp_path / 'starter.json').read_text())
    change({p['name']: p for p in starter['pipelines']})
    raw = json.dumps(starter).encode()
    (tmp_path / 'starter.json').write_bytes(raw)
    manifest = json.loads((tmp_path / 'manifest.json').read_text())
    manifest['files']['starter.json'] = hashlib.sha256(raw).hexdigest()
    (tmp_path / 'manifest.json').write_text(json.dumps(manifest))
    monkeypatch.setattr(seed_service, 'ASSETS', tmp_path)
    return seed_service.load_package


def test_generic_chatbot_seeds():
    from app.services.seed_service import load_package
    starter, _ = load_package()
    pipelines = {p['name']: p for p in starter['pipelines']}
    erasure, generic = pipelines['PII Erasure'], pipelines['Chatbot Generic']
    assert erasure['classifier'] == '[chatbot_generic_pii]' and erasure['redaction_policy'] == 'redact_none'
    assert [s['node_type'] for s in erasure['steps']] == ['prompt_assembly', 'inference']
    assert erasure['steps'][1]['config'] == {'model_default': 'local'}
    assert generic['classifier'] == '[chatbot_generic]' and generic['redaction_policy'] == 'redact_all'
    assert [s['node_type'] for s in generic['steps']] == ['prompt_assembly', 'inference', 'deredaction']
    # Only the generic chatbot's first stage is unredacted.
    assert [p['name'] for p in starter['pipelines'] if p.get('redaction_policy', 'redact_all') != 'redact_all'] \
        == ['PII Erasure']


@pytest.mark.parametrize('change, error', [
    # Unredacted patient data in a seeded workflow.
    (lambda p: p['Patient Chatbot'].update(redaction_policy='redact_none'), 'redaction policy'),
    # An unredacted stage that would de-redact, or a redacted one that would not.
    (lambda p: p['Chatbot Generic'].update(redaction_policy='redact_none'), 'redaction policy'),
    (lambda p: p['PII Erasure'].update(redaction_policy='redact_all'), 'redaction policy'),
    (lambda p: p['PII Erasure']['steps'][1]['config'].update(model_default='cloud'), 'inference settings'),
    (lambda p: p['PII Erasure']['steps'][1].update(config={'model_id': 7}), 'step settings'),
    (lambda p: p['Case Summary']['steps'][2]['config'].update(ai_notice='reassuring'), 'scope or notice'),
    (lambda p: p['Case Summary']['steps'][1]['config'].update(scope_key='anything'), 'scope or notice'),
    (lambda p: p['PII Erasure']['steps'].reverse(), 'workflow sequence'),
])
def test_seed_workflow_rules(tmp_path, monkeypatch, change, error):
    load = _package_with(tmp_path, monkeypatch, change)
    with pytest.raises(ValueError, match=error):
        load()


@pytest.mark.parametrize('change, error', [
    (lambda rows: rows.append(dict(rows[0])), 'Invalid identifier labels'),          # duplicate
    (lambda rows: rows[0].update(label='U'), 'Invalid identifier labels'),            # too short
    (lambda rows: rows[0].update(shape='.*'), 'shape'),                               # not a mask
    (lambda rows: rows[0].pop('note'), 'do not match columns'),
])
def test_admin_list_seed_rules(tmp_path, monkeypatch, change, error):
    import hashlib, json, shutil
    from app.services import seed_service
    for source in seed_service.ASSETS.glob('*.json'):
        shutil.copy(source, tmp_path / source.name)
    lists = json.loads((tmp_path / 'admin_lists.json').read_text())
    change(lists['identifier_labels']['rows'])
    raw = json.dumps(lists).encode()
    (tmp_path / 'admin_lists.json').write_bytes(raw)
    manifest = json.loads((tmp_path / 'manifest.json').read_text())
    manifest['files']['admin_lists.json'] = hashlib.sha256(raw).hexdigest()
    (tmp_path / 'manifest.json').write_text(json.dumps(manifest))
    monkeypatch.setattr(seed_service, 'ASSETS', tmp_path)
    with pytest.raises(ValueError, match=error):
        seed_service.load_admin_lists()


def test_one_gunicorn_worker():
    # Pipeline progress queues are per process (PipelineEngine._RUN_QUEUES): a second
    # worker splits a run from its progress stream.
    from pathlib import Path
    import re
    root = Path(__file__).resolve().parents[1]
    counts = re.findall(r'--workers["\s,]+"?(\d+)', (root / 'Dockerfile').read_text())
    assert counts and set(counts) == {'1'}, counts


def test_version_matches_changelog():
    # One version number, in app/version.py, with its CHANGELOG entry (docs/maintainers/releasing.md).
    import re
    from pathlib import Path
    from app.version import __version__
    assert re.fullmatch(r'\d+\.\d+\.\d+', __version__)
    changelog = (Path(__file__).resolve().parents[1] / 'CHANGELOG.md').read_text()
    assert f'## {__version__} ' in changelog


def test_case_summary_replaces_second_opinion():
    # Seeds limited to what the manufacturer considers not a medical device (plans: TGA triage):
    # no Life Expectancy or Second Opinion; Case Summary reports what is recorded, nothing more.
    from app.services.seed_service import load_package
    starter, _ = load_package()
    names = {p['name'] for p in starter['pipelines']} | {p['name'] for p in starter['user_prompts']}
    assert not names & {'Life Expectancy Discussion', 'Second Opinion'}
    # Held from the release pending TGA advice (likely devices, or personalised advice).
    held = {'Interaction Checker', 'Medication Review', 'Medication  Review', 'Developmental Milestones',
            'Developmental Milestones 6m to 4 years', 'Pathology Result - Brief', 'Pathology Result - SMS',
            'Pathology Result - Explainer', 'Pathology Results - SMS', 'Pathology Results - Explainer',
            'Report Explainer', '*GP Chronic Conditions Management Plan', 'GP Chronic Conditions Management Plan',
            'GP Mental Health Plan', 'GP Mental Health Care Plan', 'Health Status Report - Comprehensive',
            'Exercise Plan Detailed', 'Hypertension Information and Log', 'Travel Advice',
            'Weekly Meal Planner', 'Mind Gymnasium'}
    assert not names & held, names & held
    summary = next(p for p in starter['user_prompts'] if p['name'] == 'Case Summary')
    system = next(p for p in starter['system_prompts'] if p['name'] == summary['system_prompt_name'])
    assert 'Do not diagnose' in system['prompt_text'] and '{{data.blocks}}' in summary['prompt_text']


def test_seed_prompts_do_not_ask_the_model_to_hide_ai():
    # Transparency (MSIA & MTAA AI Governance Code): no seeded prompt tells the model to disguise itself.
    import re
    from app.services.seed_service import load_package
    starter, _ = load_package()
    for kind in ('system_prompts', 'user_prompts'):
        for prompt in starter[kind]:
            assert not re.search(r"(?i)don.t make it obvious|real doctor|appear obviously AI", prompt['prompt_text']), prompt['name']


def test_provenance_footer(monkeypatch):
    # Off by default; when on: AI-assisted, filed by, date and time, the run reference.
    import re
    from app.models.system_setting import SystemSetting
    from app.services import ai_provenance_service as ap
    settings = {}
    monkeypatch.setattr(SystemSetting, 'get', staticmethod(lambda k, d=None: settings.get(k, d)))
    class User:
        bpsdb_firstname, bpsdb_surname, display_name = 'Ann', 'Example', 'aexample'
    assert ap.footer_for_run(1234, User()) == ''
    settings['ai.provenance_footer'] = True
    assert re.fullmatch(r'\n\nAI-assisted draft · filed by Ann Example · \d\d/\d\d/\d{4} \d\d:\d\d · MedUI ref 1234',
                        ap.footer_for_run(1234, User()))
    assert ap.footer_for_run(None, User()) == '' and ap.footer_for_run('x', User()) == ''


def test_chatbot_prompts_confined():
    # Patient chatbot: what is recorded only. General chatbot: general reference, no "no censorship".
    from app.services.seed_service import load_package
    starter, _ = load_package()
    sp = {p['name']: p['prompt_text'] for p in starter['system_prompts']}
    patient, general = sp['Chatbot System Prompt'], sp['Chatbot Generic']
    assert 'Do not suggest diagnoses' in patient and 'use your knowledge and training' not in patient
    assert 'no censorship' not in general.lower() and 'answer any question' not in general.lower()
    assert all('RESPONSE FORMAT (mandatory):' in t and '"Title"' in t and '"Response"' in t for t in (patient, general))


def test_remaining_prompts_confined():
    # Scribe, To-Do, document summary and User Query stay within what was said or recorded.
    from app.services.seed_service import load_package
    starter, _ = load_package()
    sp = {p['name']: p['prompt_text'] for p in starter['system_prompts']}
    up = {p['name']: p for p in starter['user_prompts']}
    issues, normal, summary = sp['Consult Notes Issues List'], sp['Consult Notes Normal'], sp['Medical Document Text Summarization']
    assert 'whether or not it is an existing diagnosis' in issues and 'mapping each issue to a known medical diagnosis' not in issues
    assert 'or implied' not in issues and 'group heading' in issues
    assert 'You may use inference' not in normal and 'Infer examination findings' not in normal
    assert 'Patient Explanation' not in summary and 'directly inferred' not in summary
    assert 'Outstanding items recorded' in up['*Consultation To Do List']['prompt_text']
    assert up['Default Info Sheet Prompt']['system_prompt_name'] == 'Record Questions (factual)'
    assert 'Summarize and Explain Clinical Document [EXP]' not in up and 'Summarise Clinical Document [EXP]' in up
    # The [SUM] and [EXP] document buttons each need an active-able pipeline with that classifier.
    pipes = {p['classifier']: p for p in starter['pipelines']}
    assert {'[SUM]', '[EXP]'} <= set(pipes)
    sum_prompt = next(s['config']['user_prompt_name'] for s in pipes['[SUM]']['steps'] if s['node_type'] == 'prompt_assembly')
    assert sum_prompt in up


def test_no_undefined_names():
    # A missing import only fails when that code path runs (e.g. Setup → OCR → Test).
    pyflakes_api = pytest.importorskip('pyflakes.api')
    from pyflakes.reporter import Reporter
    import io, pathlib
    out = io.StringIO()
    pyflakes_api.checkRecursive([str(pathlib.Path(__file__).parent.parent / 'app')], Reporter(out, io.StringIO()))
    undefined = [line for line in out.getvalue().splitlines() if 'undefined name' in line]
    assert not undefined, undefined


def test_seed_history_covers_current_seeds():
    # Rebuild with scripts/build_seed_history.py whenever starter.json changes.
    from app.services.seed_service import load_package
    from app.services.seed_resync_service import load_history
    starter, _ = load_package()
    history = load_history(starter)
    assert set(history['user_prompts']) >= {r['name'] for r in starter['user_prompts']}


def test_seed_fingerprint_ignores_practice_choices():
    from app.services import seed_fingerprint as fp
    base = {'name': 'Invented', 'prompt_text': ' Summarise. ', 'description': '',
            'system_prompt_name': 'Sys', 'classifier': None, 'temperature': 0.2, 'max_tokens': None}
    same = dict(base, prompt_text='Summarise.', description=None, temperature=0.2,
                show_in_assistant=True, default_model_id=7, is_active=False)
    assert fp.user_prompt(base) == fp.user_prompt(same)
    assert fp.user_prompt(base) != fp.user_prompt(dict(base, prompt_text='Diagnose.'))


def test_seed_resync(installed_app, monkeypatch):
    import json
    from app.extensions import db
    from app.services import seed_fingerprint as fp
    from app.services import seed_resync_service
    from app.services.seed_service import install_seeds, load_package
    from app.models.prompt import SystemPrompt, UserPrompt
    from app.models.user_prompt_version import UserPromptVersion
    from app.models.pipeline import Pipeline, PipelineStatus, PipelineStep, RedactionPolicy

    def outcomes(report):
        return {(r['category'], r['name']): r['outcome'] for r in report}

    def steps(pipeline):
        return PipelineStep.query.filter_by(pipeline_id=pipeline.id).order_by(PipelineStep.step_order).all()

    def config(pipeline, node_type):
        return json.loads(next(s for s in steps(pipeline) if s.node_type == node_type).config_json)

    starter, _ = load_package()
    workflow = next(p for p in starter['pipelines'] if p['steps'][0]['node_type'] == 'data_assembly')
    prompt_name = workflow['steps'][1]['config']['user_prompt_name']
    edited_name = next(p['name'] for p in starter['user_prompts'] if p['name'] != prompt_name)
    system_name = starter['system_prompts'][0]['name']
    extra = []   # (category, name, fingerprint) of an invented earlier release

    with installed_app.app_context():
        install_seeds()
        # A fresh install is current; an earlier test edits one prompt on purpose.
        first = seed_resync_service.resync_seeds()
        assert {r['outcome'] for r in first} <= {'current', 'customised'}, first

        # An earlier release's text, with the practice's own choices made since.
        prompt = UserPrompt.query.filter_by(name=prompt_name).one()
        seeded_text = prompt.prompt_text
        prompt.prompt_text = 'Earlier invented wording.'
        prompt.show_in_assistant = True
        extra.append(('user_prompts', prompt_name, fp.user_prompt(
            {f: getattr(prompt, f) for f in fp.USER_FIELDS})))
        # A prompt the practice has edited: matches no release.
        edited = UserPrompt.query.filter_by(name=edited_name).one()
        edited.prompt_text = 'Our practice wording.'
        # An earlier system prompt, set as the default.
        system = SystemPrompt.query.filter_by(name=system_name, is_active=True).one()
        system.prompt_text = 'Earlier system wording.'
        system.is_default = True
        extra.append(('system_prompts', system_name, fp.system_prompt(
            {f: getattr(system, f) for f in fp.SYSTEM_FIELDS})))
        # An earlier workflow, activated with a model and another bundle.
        pipeline = Pipeline.query.filter_by(name=workflow['name']).one()
        pipeline.description = 'Earlier invented description.'
        pipeline.status = PipelineStatus.active
        for step in steps(pipeline):
            cfg = json.loads(step.config_json)
            if step.node_type == 'inference':
                cfg['model_id'] = 4242
            if step.node_type == 'data_assembly':
                cfg['bundle_name'] = 'clinical_context'
            step.config_json = json.dumps(cfg)
        db.session.flush()
        extra.append(('pipelines', workflow['name'],
                      seed_resync_service._pipeline_fingerprint(pipeline, steps(pipeline))))
        # A workflow and prompt an earlier release had and this one dropped.
        old_prompt = UserPrompt(name='Invented Dropped Prompt', prompt_text='Old.')
        db.session.add(old_prompt)
        db.session.flush()
        old_flow = Pipeline(name='Invented Dropped Workflow', redaction_policy=RedactionPolicy.redact_all)
        db.session.add(old_flow)
        db.session.flush()
        db.session.add(PipelineStep(pipeline_id=old_flow.id, step_order=0, node_type='prompt_assembly',
                                    config_json=json.dumps({'user_prompt_id': old_prompt.id})))
        # A dropped prompt one of the practice's own workflows still uses.
        shared = UserPrompt(name='Invented Dropped Shared Prompt', prompt_text='Shared.')
        db.session.add(shared)
        db.session.flush()
        own_flow = Pipeline(name='Invented Practice Workflow', redaction_policy=RedactionPolicy.redact_all)
        db.session.add(own_flow)
        db.session.flush()
        db.session.add(PipelineStep(pipeline_id=own_flow.id, step_order=0, node_type='prompt_assembly',
                                    config_json=json.dumps({'user_prompt_id': shared.id})))
        extra.append(('user_prompts', shared.name, fp.user_prompt(
            {f: getattr(shared, f) for f in fp.USER_FIELDS})))
        # The practice's own prompt.
        db.session.add(UserPrompt(name='Invented Practice Prompt', prompt_text='Ours.'))
        db.session.flush()
        extra.append(('user_prompts', old_prompt.name, fp.user_prompt(
            {f: getattr(old_prompt, f) for f in fp.USER_FIELDS})))
        extra.append(('pipelines', old_flow.name,
                      seed_resync_service._pipeline_fingerprint(old_flow, steps(old_flow))))
        db.session.commit()

        original = seed_resync_service.load_history

        def with_earlier_release(starter):
            history = original(starter)
            for category, name, fingerprint in extra:
                history[category].setdefault(name, []).insert(0, fingerprint)
            return history
        monkeypatch.setattr(seed_resync_service, 'load_history', with_earlier_release)

        # Dry run: reports, changes nothing.
        preview = outcomes(seed_resync_service.resync_seeds(dry_run=True))
        assert preview[('user_prompts', prompt_name)] == 'updated'
        assert UserPrompt.query.filter_by(name=prompt_name).one().prompt_text == 'Earlier invented wording.'

        report = outcomes(seed_resync_service.resync_seeds())
        assert report[('user_prompts', prompt_name)] == 'updated'
        assert report[('user_prompts', edited_name)] == 'customised'
        assert report[('system_prompts', system_name)] == 'updated'
        assert report[('pipelines', workflow['name'])] == 'updated'
        assert report[('pipelines', 'Invented Dropped Workflow')] == 'dropped'
        # Used only by a dropped workflow, it goes with it; used by the practice's own, it stays.
        assert report[('user_prompts', 'Invented Dropped Prompt')] == 'dropped'
        assert report[('user_prompts', 'Invented Dropped Shared Prompt')] == 'dropped-in-use'
        assert ('user_prompts', 'Invented Practice Prompt') not in report
        assert ('pipelines', 'Invented Practice Workflow') not in report

        prompt = UserPrompt.query.filter_by(name=prompt_name).one()
        assert prompt.prompt_text == seeded_text and prompt.show_in_assistant
        saved = UserPromptVersion.query.filter_by(user_prompt_id=prompt.id).one()
        assert saved.prompt_text == 'Earlier invented wording.' and saved.version == 1
        assert UserPrompt.query.filter_by(name=edited_name).one().prompt_text == 'Our practice wording.'
        versions = SystemPrompt.query.filter_by(name=system_name).order_by(SystemPrompt.version).all()
        assert [v.is_active for v in versions] == [False, True]
        assert versions[0].prompt_text == 'Earlier system wording.' and versions[1].is_default
        pipeline = Pipeline.query.filter_by(name=workflow['name']).one()
        assert pipeline.description == workflow['description'] and pipeline.status == PipelineStatus.active
        assert config(pipeline, 'inference')['model_id'] == 4242
        assert config(pipeline, 'data_assembly')['bundle_name'] == 'clinical_context'
        assert config(pipeline, 'prompt_assembly')['user_prompt_id'] == prompt.id

        # Edited items only on request; dropped items archived only on request.
        report = outcomes(seed_resync_service.resync_seeds(archive_dropped=True, replace=[edited_name]))
        assert report[('user_prompts', edited_name)] == 'replaced'
        assert report[('pipelines', 'Invented Dropped Workflow')] == 'dropped-archived'
        assert report[('user_prompts', 'Invented Dropped Prompt')] == 'dropped-archived'
        assert Pipeline.query.filter_by(name='Invented Dropped Workflow').one().status == PipelineStatus.archived
        assert not UserPrompt.query.filter_by(name='Invented Dropped Prompt').one().is_active
        assert report[('user_prompts', 'Invented Dropped Shared Prompt')] == 'dropped-in-use'
        assert UserPrompt.query.filter_by(name='Invented Dropped Shared Prompt').one().is_active
        edited = UserPrompt.query.filter_by(name=edited_name).one()
        assert UserPromptVersion.query.filter_by(user_prompt_id=edited.id).one().prompt_text == 'Our practice wording.'

        # Nothing left to do.
        assert {r['outcome'] for r in seed_resync_service.resync_seeds()} <= {'current', 'customised', 'dropped-in-use'}

        import pytest as _pytest
        with _pytest.raises(ValueError, match='Not a seeded'):
            seed_resync_service.resync_seeds(replace=['Invented Practice Prompt'])


def test_seeded_system_prompts_have_a_scope():
    # Every seeded system prompt names its scope instruction; 'none' only for utilities.
    import json
    from pathlib import Path
    starter = json.loads((Path(__file__).resolve().parents[1] / 'app/seed_assets/starter.json').read_text())
    scopes = {r['name']: r.get('scope_key') for r in starter['system_prompts']}
    assert all(scopes.values())
    assert {n for n, s in scopes.items() if s == 'none'} == {'PII_Eraser', 'Text Formatting Cleanup'}
    assert scopes['Consult Notes Normal'] == scopes['Consult Notes Issues List'] == 'scribe'
    assert scopes['Chatbot Generic'] == scopes['Library Assistant'] == 'general'


def test_intended_purpose_statement_matches():
    # One statement, written in docs/intended_purpose.md and quoted unchanged in README and
    # AGENTS.md (docs/maintainers/releasing.md). Compared with line breaks and quote markers removed.
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]

    def words(text):
        return ' '.join(line.lstrip('> ').strip() for line in text.splitlines()).split()

    doc = (root / 'docs' / 'intended_purpose.md').read_text()
    statement = doc.split('## Statement\n\n', 1)[1].split('\n\n', 1)[0]
    assert 'MedUI does not diagnose' in statement
    for name in ('README.md', 'AGENTS.md'):
        text = (root / name).read_text()
        assert ' '.join(words(statement)) in ' '.join(words(text)), name


def test_help_check():
    # Every help file parses, and every [?] (templates, scripts) and help link points to a
    # section that exists: `flask help check` as a test (upstream ADR-102).
    from pathlib import Path
    from types import SimpleNamespace
    from flask import Flask
    from app.services import help_service as hs
    app = Flask('app', root_path=str(Path(__file__).resolve().parents[1] / 'app'))
    with app.app_context():
        assert hs.check() == []
        topics = hs.topics()
        assert len(topics) >= 10 and all(t.sections for t in topics.values())
        admin = SimpleNamespace(is_admin=True, security_level=9)
        app.config['AI_ENABLED'] = True
        with_ai = {t.id for t in hs.visible_topics(admin)}
        app.config['AI_ENABLED'] = False
        without_ai = {t.id for t in hs.visible_topics(admin)}
        # AI topics hide while AI is off; the rest stay.
        assert {'scribe', 'chatbots', 'prompts'} <= with_ai - without_ai
        assert 'daysheet' in without_ai


def test_dependency_licences():
    # MedUI's licence is decided last (docs/release-status.md). To keep every choice open,
    # no dependency may be under a strong copyleft licence (GPL, AGPL) without a decision:
    # add it to ALLOWED with the reason. Weak copyleft (LGPL, MPL) doesn't bind MedUI's code.
    import re
    from importlib import metadata
    from pathlib import Path
    ALLOWED = {}   # package name (lower case) -> why a GPL/AGPL licence is accepted
    strong = re.compile(r'\bA?GPL\b|Affero|GNU General Public', re.I)
    weak = re.compile(r'\bLGPL\b|Lesser General Public', re.I)
    root = Path(__file__).resolve().parents[1]
    found = []
    for line in (root / 'requirements.txt').read_text().splitlines():
        name = re.split(r'[=<>\[;\s]', line.strip(), maxsplit=1)[0]
        if not name or name.startswith('#'):
            continue
        try:
            meta = metadata.metadata(name)
        except metadata.PackageNotFoundError:
            continue                                   # not installed here: nothing to read
        texts = [meta.get('License-Expression') or '', (meta.get('License') or '').split('\n')[0]]
        texts += [c for c in (meta.get_all('Classifier') or []) if c.startswith('License')]
        licence = ' | '.join(t for t in texts if t)
        if strong.search(weak.sub('', licence)) and name.lower() not in ALLOWED:
            found.append(f'{name}: {licence[:80]}')
    assert not found, 'Strong copyleft dependencies (decide first, see docs/release-status.md):\n' + '\n'.join(found)


def test_every_url_for_names_a_route(installed_app):
    # A template carried over from upstream can name a route this edition removes (the
    # document summariser's rollup status did, in 0.21.0): the page then fails to render.
    import pathlib
    import re
    endpoints = {r.endpoint for r in installed_app.url_map.iter_rules()}
    pattern = re.compile(r"""url_for\(\s*['"]([A-Za-z_][\w.]*)['"]""")
    missing = sorted({(m.group(1), str(f)) for f in pathlib.Path('app').rglob('*')
                      if f.suffix in ('.html', '.py')
                      for m in pattern.finditer(f.read_text(errors='replace'))
                      if not m.group(1).startswith('.') and m.group(1) not in endpoints})
    assert not missing, missing


def test_ai_assistant_page_renders(installed_app, monkeypatch):
    from app.models.user import User
    from app.services import clinical_service
    from uuid import uuid4
    username = 'test-ai-' + uuid4().hex[:8]
    runner = installed_app.test_cli_runner()
    assert runner.invoke(args=['install', 'admin', '--username', username,
                               '--password', 'synthetic-test-password']).exit_code == 0
    with installed_app.app_context():
        uid = User.query.filter_by(username=username).one().id
    monkeypatch.setitem(installed_app.config, 'AI_ENABLED', True)
    monkeypatch.setattr(clinical_service.ClinicalService, 'get_patient_demographics',
                        staticmethod(lambda pid: {'FIRSTNAME': 'Marigold', 'SURNAME': 'Quillfeather'}))
    client = installed_app.test_client()
    with client.session_transaction() as session:
        session['_user_id'] = str(uid)
        session['_fresh'] = True
    response = client.get('/clinical/patient/1001/ai')
    assert response.status_code == 200, response.status_code
    assert 'Sent to AI' in response.get_data(as_text=True)


@pytest.mark.parametrize('ai_enabled', [False, True])
def test_usage_pages_render(installed_app, monkeypatch, ai_enabled):
    """Application Usage (ADR-137) and My Usage (ADR-138) open on an empty install."""
    from app.models.user import User
    from uuid import uuid4
    username = 'test-usage-' + uuid4().hex[:8]
    runner = installed_app.test_cli_runner()
    assert runner.invoke(args=['install', 'admin', '--username', username,
                               '--password', 'synthetic-test-password']).exit_code == 0
    with installed_app.app_context():
        uid = User.query.filter_by(username=username).one().id
    monkeypatch.setitem(installed_app.config, 'AI_ENABLED', ai_enabled)
    client = installed_app.test_client()
    with client.session_transaction() as session:
        session['_user_id'] = str(uid)
        session['_fresh'] = True
    for path in ('/doctor/usage', '/doctor/usage?tab=nonai&view=rows', '/me/settings/usage',
                 '/me/settings/usage?tab=nonai&by=task', '/me/settings/usage?measure=scribe&view=rows'):
        response = client.get(path)
        assert response.status_code == 200, (path, response.status_code)
    page = client.get('/me/settings/usage').get_data(as_text=True)
    assert 'Practice:' in page
    # With AI switched off the page opens on Non-AI.
    assert ('Charts opened' in page) is (not ai_enabled)
