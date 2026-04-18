import os
import tempfile
from datetime import timedelta

from dotenv import load_dotenv


load_dotenv()


def _is_truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def _default_base_url() -> str:
    explicit_url = (os.environ.get("APP_BASE_URL") or "").strip()
    if explicit_url:
        return explicit_url.rstrip("/")

    for env_name in ("VERCEL_PROJECT_PRODUCTION_URL", "VERCEL_URL"):
        candidate = (os.environ.get(env_name) or "").strip()
        if not candidate:
            continue
        if candidate.startswith(("http://", "https://")):
            return candidate.rstrip("/")
        return f"https://{candidate.rstrip('/')}"

    return "http://127.0.0.1:5000"


IS_VERCEL = _is_truthy(os.environ.get("VERCEL"))
BASE_URL = _default_base_url()
DEFAULT_UPLOAD_FOLDER = os.path.join(tempfile.gettempdir(), "hiremind_uploads") if IS_VERCEL else os.path.join(os.path.dirname(__file__), "instance", "uploads")


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me")
    MONGO_URI = os.environ.get("MONGO_URI")
    DB_NAME = os.environ.get("DB_NAME", "hiremind")
    UPLOAD_FOLDER = os.environ.get("UPLOAD_FOLDER", DEFAULT_UPLOAD_FOLDER)
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024
    ALLOWED_EXTENSIONS = {"pdf", "doc", "docx"}
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SECURE = IS_VERCEL or _is_truthy(os.environ.get("SESSION_COOKIE_SECURE"))
    SESSION_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SECURE = SESSION_COOKIE_SECURE
    PERMANENT_SESSION_LIFETIME = timedelta(hours=12)
    WTF_CSRF_TIME_LIMIT = None
    GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
    GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
    GOOGLE_REDIRECT_URI = os.environ.get("GOOGLE_REDIRECT_URI", f"{BASE_URL}/auth/google/callback")
    LINKEDIN_CLIENT_ID = os.environ.get("LINKEDIN_CLIENT_ID", "")
    LINKEDIN_CLIENT_SECRET = os.environ.get("LINKEDIN_CLIENT_SECRET", "")
    LINKEDIN_REDIRECT_URI = os.environ.get("LINKEDIN_REDIRECT_URI", f"{BASE_URL}/auth/linkedin/callback")
    PROFILE_IMAGE_UPLOADS_ENABLED = not IS_VERCEL and not _is_truthy(os.environ.get("DISABLE_PROFILE_IMAGE_UPLOADS"))
