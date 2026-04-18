from datetime import datetime

from bson import ObjectId
from flask import current_app, request


class AuthSessionModel:
    collection_name = "auth_sessions"

    @classmethod
    def _collection(cls):
        return current_app.db[cls.collection_name]

    @classmethod
    def create_session(cls, user_id: str, auth_provider: str = "password"):
        payload = {
            "user_id": user_id,
            "auth_provider": auth_provider,
            "ip_address": request.headers.get("X-Forwarded-For", request.remote_addr),
            "user_agent": request.headers.get("User-Agent", ""),
            "logged_out_at": None,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }
        result = cls._collection().insert_one(payload)
        return str(result.inserted_id)

    @classmethod
    def close_session(cls, session_id: str):
        if not ObjectId.is_valid(session_id):
            return
        cls._collection().update_one(
            {"_id": ObjectId(session_id)},
            {"$set": {"logged_out_at": datetime.utcnow(), "updated_at": datetime.utcnow()}},
        )

    @classmethod
    def active_for_user(cls, user_id: str):
        return list(cls._collection().find({"user_id": user_id, "logged_out_at": None}).sort("created_at", -1))
