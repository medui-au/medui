"""Route guards shared across blueprints."""
from functools import wraps

from flask import abort, jsonify, request
from flask_login import current_user


def ai_required(f):
    """Refuse users who may not start AI queries (User.can_use_ai): 403.

    JSON callers get {'error': ...}; pages get the standard 403.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        if not (current_user.is_authenticated and current_user.can_use_ai):
            if request.is_json or request.accept_mimetypes.best == 'application/json':
                return jsonify({'error': 'AI is not available for your login.'}), 403
            abort(403)
        return f(*args, **kwargs)
    return decorated
