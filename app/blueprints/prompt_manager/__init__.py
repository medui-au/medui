from flask import Blueprint

bp = Blueprint('prompt_manager', __name__)

from . import routes  # noqa: E402, F401
