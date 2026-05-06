from functools import wraps
import secrets
from urllib.parse import urlparse

from flask import jsonify, request
from flask_login import current_user

_TEMP_PASSWORD_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789"
UNSAFE_METHODS = {"POST", "PATCH", "PUT", "DELETE"}


def role_required(*roles):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if not current_user.is_authenticated:
                return jsonify({"error": "Unauthorized"}), 401
            if hasattr(current_user, "is_active") and not current_user.is_active:
                return jsonify({"error": "Account disabled"}), 403
            if current_user.role not in roles:
                return jsonify({"error": "Forbidden"}), 403
            return fn(*args, **kwargs)

        return wrapper

    return decorator


def generate_temp_password(length=12):
    return "".join(secrets.choice(_TEMP_PASSWORD_ALPHABET) for _ in range(length))


def _origin_tuple(url):
    parsed = urlparse(url or "")
    if not parsed.scheme or not parsed.netloc:
        return None
    scheme = parsed.scheme.lower()
    hostname = (parsed.hostname or "").lower()
    port = parsed.port
    if port is None:
        if scheme == "http":
            port = 80
        elif scheme == "https":
            port = 443
    return scheme, hostname, port


def request_host_origin():
    return _origin_tuple(request.host_url)


def is_same_origin_url(value):
    incoming = _origin_tuple(value)
    expected = request_host_origin()
    return bool(incoming and expected and incoming == expected)


def unsafe_request_is_same_origin():
    if request.method not in UNSAFE_METHODS:
        return True
    origin = request.headers.get("Origin")
    if origin:
        return is_same_origin_url(origin)
    referer = request.headers.get("Referer")
    if referer:
        return is_same_origin_url(referer)
    return True
