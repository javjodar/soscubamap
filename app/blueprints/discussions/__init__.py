from flask import Blueprint


discussions_bp = Blueprint("discussions", __name__)

from . import routes  # noqa: E402,F401
