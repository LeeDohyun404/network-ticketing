from functools import wraps

from flask import jsonify
from flask_jwt_extended import get_jwt, get_jwt_identity, verify_jwt_in_request

from .extensions import db


def error(message, status=400):
    return jsonify({"error": message}), status


def roles_required(*roles):
    """Wajib login dan memiliki salah satu role yang diizinkan."""
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            verify_jwt_in_request()
            if get_jwt().get("role") not in roles:
                return error("Anda tidak berhak mengakses ini", 403)
            return fn(*args, **kwargs)
        return wrapper
    return decorator


def current_user():
    from .models import User
    return db.session.get(User, int(get_jwt_identity()))
