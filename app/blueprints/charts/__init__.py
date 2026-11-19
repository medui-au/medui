from flask import Blueprint

bp = Blueprint('charts', __name__)

from . import routes  # noqa: E402, F401
