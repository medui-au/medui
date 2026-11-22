from flask import Blueprint

bp = Blueprint('gpccmp', __name__)

from . import routes  # noqa: E402, F401
