from flask import Blueprint

bp = Blueprint('patient_api', __name__)

from . import routes  # noqa: E402, F401
