from flask import Blueprint

bp = Blueprint('viewer', __name__)

from . import routes  # noqa: E402, F401
