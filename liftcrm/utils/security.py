from functools import wraps
import secrets
import string

from flask import jsonify
from flask_login import current_user

from .. import config


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


def generate_temp_password(length: int = 10) -> str:
    preset = (config.MASTER_PASSWORD or "").strip()
    if preset:
        return preset
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(max(8, length)))
