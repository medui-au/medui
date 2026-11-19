from flask import Blueprint

bp = Blueprint('doctor', __name__)

from . import routes  # noqa: E402, F401

