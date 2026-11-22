from flask import Blueprint

bp = Blueprint('protocols', __name__)

from . import routes  # noqa: E402, F401
