from flask import Blueprint

bp = Blueprint('my_settings', __name__)

from . import routes  # noqa: E402, F401
