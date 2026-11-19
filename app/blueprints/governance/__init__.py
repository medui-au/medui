from flask import Blueprint

bp = Blueprint('governance', __name__)

from . import complaints_routes      # noqa: E402, F401
from . import adverse_event_routes   # noqa: E402, F401
from . import register_routes        # noqa: E402, F401
from . import permissions_routes     # noqa: E402, F401


@bp.context_processor
def inject_governance_level():
    from flask_login import current_user
    from .permissions import effective_governance_level, has_governance_level
    if current_user.is_authenticated:
        gov_level = effective_governance_level(current_user)
        return {
            'gov_level': gov_level,
            'has_gov_level': lambda n: gov_level >= n,
        }
    return {'gov_level': 0, 'has_gov_level': lambda n: False}
