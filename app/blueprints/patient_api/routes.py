"""Patient API blueprint — optional REST API for PatientJSON data.

Enabled via SystemSettings.patient_api_enabled (or PATIENT_API_ENABLED in config).
All endpoints require a valid API key supplied as Bearer token or X-Api-Key header.

Routes
------
GET /api/patient/<patient_id>/block/<block_name>    Single atomic block
GET /api/patient/<patient_id>/bundle/<bundle_name>  Full bundle (?fmt=text|json|markdown)
GET /api/patient/<patient_id>/blocks                List of available block names
"""

import functools

from flask import jsonify, request, current_app
from flask_login import current_user, login_required

from . import bp
from app.services.patient_json_service import PatientJsonService, BLOCK_LABELS
from app.services.bundle_render_service import BundleRenderService


# ── Auth guard ────────────────────────────────────────────────────────────────

def _api_enabled():
    """Return True if the patient API is enabled in settings or config."""
    try:
        from app.models.system_settings import SystemSettings
        setting = SystemSettings.query.filter_by(key='patient_api_enabled').first()
        if setting:
            return setting.value in ('1', 'true', 'True', True)
    except Exception:
        pass
    return current_app.config.get('PATIENT_API_ENABLED', False)


def _check_api_key() -> bool:
    """Validate the API key from Bearer token or X-Api-Key header."""
    valid_keys: list[str] = current_app.config.get('PATIENT_API_KEYS', [])
    if not valid_keys:
        return False

    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        token = auth_header[7:].strip()
        return token in valid_keys

    x_key = request.headers.get('X-Api-Key', '').strip()
    return x_key in valid_keys


def api_required(f):
    """Decorator: gate on API enabled + valid key OR active session."""
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if not _api_enabled():
            return jsonify({'error': 'Patient API is not enabled.'}), 403

        # Session auth (browser / pipeline internal use)
        if current_user.is_authenticated:
            return f(*args, **kwargs)

        # API key auth (external integrations)
        if not _check_api_key():
            return jsonify({'error': 'Unauthorized. Provide a valid API key.'}), 401

        return f(*args, **kwargs)
    return decorated


# ── Helpers ───────────────────────────────────────────────────────────────────

def _deidentify_param() -> bool:
    return request.args.get('deidentify', '0') in ('1', 'true', 'True')


def _make_pjs() -> PatientJsonService:
    return PatientJsonService()


# ── Routes ────────────────────────────────────────────────────────────────────

@bp.get('/patient/<int:patient_id>/blocks')
@api_required
def list_blocks(patient_id: int):
    """List all available block names and their display labels."""
    return jsonify({
        'patient_id': patient_id,
        'blocks': [
            {'name': name, 'label': label}
            for name, label in sorted(BLOCK_LABELS.items())
        ],
    })


@bp.get('/patient/<int:patient_id>/block/<block_name>')
@api_required
def get_block(patient_id: int, block_name: str):
    """Return a single atomic block as JSON.

    Extra query params for progress_notes:
      q   Free-text search string.  Synonym-expanded; searches all records.
          Response includes query, synonyms_used, and per-note matched_terms.
    """
    deidentify = _deidentify_param()
    q = request.args.get('q', '').strip() or None

    try:
        data = _make_pjs().get_atomic_block(
            block_name, patient_id, deidentify=deidentify, q=q
        )
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    except Exception as exc:
        current_app.logger.error('patient_api.get_block(%s, %s): %s', patient_id, block_name, exc)
        return jsonify({'error': 'Data retrieval failed.'}), 500

    response: dict = {
        'patient_id': patient_id,
        'block':      block_name,
        'deidentify': deidentify,
        'data':       data,
    }

    if q and block_name == 'progress_notes':
        from app.services.clinical_synonyms import expand_query
        response['query']        = q
        response['synonyms_used'] = expand_query(q)
        response['result_count'] = len(data) if isinstance(data, list) else None

    return jsonify(response)


@bp.get('/patient/<int:patient_id>/bundle/<bundle_name>')
@api_required
def get_bundle(patient_id: int, bundle_name: str):
    """Return a full bundle rendered in the requested format.

    Query params:
      fmt        text | json | markdown  (default: json)
      deidentify 1 | 0                  (default: 0)
    """
    fmt        = request.args.get('fmt', 'json')
    deidentify = _deidentify_param()

    try:
        rendered = BundleRenderService().render(
            bundle_name, patient_id, fmt=fmt, deidentify=deidentify
        )
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    except Exception as exc:
        current_app.logger.error('patient_api.get_bundle(%s, %s): %s', patient_id, bundle_name, exc)
        return jsonify({'error': 'Bundle retrieval failed.'}), 500

    if fmt == 'json':
        import json
        try:
            payload = json.loads(rendered)
        except Exception:
            payload = rendered
        return jsonify({
            'patient_id':   patient_id,
            'bundle':       bundle_name,
            'deidentify':   deidentify,
            'data':         payload,
        })

    # text or markdown — return as plain content
    from flask import Response
    mimetype = 'text/markdown' if fmt == 'markdown' else 'text/plain'
    return Response(rendered, mimetype=mimetype)
