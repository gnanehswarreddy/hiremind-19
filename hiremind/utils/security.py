import re
from functools import wraps

import bcrypt
from flask import abort, flash, redirect, request, url_for
from flask_login import current_user


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def allowed_file(filename: str, allowed_extensions: set[str]) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in allowed_extensions


def valid_email(email: str) -> bool:
    return bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email.strip()))


def valid_password(password: str) -> bool:
    return len(password) >= 8 and any(char.isdigit() for char in password) and any(char.isalpha() for char in password)


def sanitize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def role_required(role: str):
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for("auth.login", next=request.path))
            if current_user.role != role:
                flash("You do not have permission to access that page.", "danger")
                abort(403)
            return view_func(*args, **kwargs)

        return wrapper

    return decorator
