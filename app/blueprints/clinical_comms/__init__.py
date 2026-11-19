from flask import Blueprint

bp = Blueprint('clinical_comms', __name__)

from . import routes  # noqa: E402, F401
