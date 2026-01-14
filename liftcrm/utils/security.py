from functools import wraps
import secrets
import string

from flask import jsonify
from flask_login import current_user

from .. import config

_TEMP_PASSWORD_ALPHABET = string.ascii_letters + string.digits


def role_required(*roles):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if not current_user.is_authenticated:
                return jsonify({"error": "Unauthorized"}), 401
            if current_user.role not in roles:
                return jsonify({"error": "Forbidden"}), 403
            return fn(*args, **kwargs)

        return wrapper

    return decorator


def generate_temp_password(length: int = 12, preset: str | None = None) -> str:
    if preset is not None and preset.strip() != "":
        return preset.strip()
    return "".join(secrets.choice(_TEMP_PASSWORD_ALPHABET) for _ in range(max(8, length)))
