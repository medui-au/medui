from flask import Blueprint

bp = Blueprint('doc_library', __name__)

from . import routes  # noqa: E402, F401
