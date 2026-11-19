from flask import Blueprint

bp = Blueprint('pipeline_run', __name__)

from . import routes  # noqa: E402, F401
