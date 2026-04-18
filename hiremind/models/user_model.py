from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from bson import ObjectId
from flask import current_app
from flask_login import UserMixin

from services.embeddings import build_search_text, generate_embedding


@dataclass
class User(UserMixin):
    id: str
    name: str
    email: str
    role: str


class UserModel:
    collection_name = "users"

    @classmethod
    def _collection(cls):
        return current_app.db[cls.collection_name]

    @classmethod
    def create_indexes(cls):
        cls._collection().create_index("email", unique=True)
        cls._collection().create_index("role")
        cls._collection().create_index("created_at")

    @classmethod
    def _build_profile_document(cls, payload: dict) -> dict:
        search_text = build_search_text(
            [
                payload.get("name"),
                payload.get("email"),
                payload.get("headline"),
                payload.get("location"),
                ", ".join(payload.get("skills", [])),
                payload.get("preferred_role"),
            ]
        )
        return {
            **payload,
            "search_text": search_text,
            "profile_embedding": generate_embedding(search_text),
            "profile_embedding_status": "ready",
        }

    @classmethod
    def create_user(cls, name: str, email: str, password_hash: str, role: str):
        now = datetime.utcnow()
        payload = cls._build_profile_document(
            {
                "name": name,
                "email": email.lower().strip(),
                "password": password_hash,
                "role": role,
                "profile_image": None,
                "skills": [],
                "preferences": {},
                "notifications": {},
                "created_at": now,
                "updated_at": now,
            }
        )
        result = cls._collection().insert_one(payload)
        return str(result.inserted_id)

    @classmethod
    def create_social_user(cls, name: str, email: str, password_hash: str, role: str, provider: str):
        now = datetime.utcnow()
        payload = cls._build_profile_document(
            {
                "name": name,
                "email": email.lower().strip(),
                "password": password_hash,
                "role": role,
                "auth_provider": provider,
                "profile_image": None,
                "skills": [],
                "preferences": {},
                "notifications": {},
                "created_at": now,
                "updated_at": now,
            }
        )
        result = cls._collection().insert_one(payload)
        return str(result.inserted_id)

    @classmethod
    def get_raw_by_email(cls, email: str) -> Optional[dict]:
        return cls._collection().find_one({"email": email.lower().strip()})

    @classmethod
    def get_by_id(cls, user_id: str) -> Optional[User]:
        if not ObjectId.is_valid(user_id):
            return None
        user = cls._collection().find_one({"_id": ObjectId(user_id)})
        if not user:
            return None
        return User(id=str(user["_id"]), name=user["name"], email=user["email"], role=user["role"])

    @classmethod
    def get_raw_by_id(cls, user_id: str) -> Optional[dict]:
        if not ObjectId.is_valid(user_id):
            return None
        return cls._collection().find_one({"_id": ObjectId(user_id)})

    @classmethod
    def all_candidates(cls):
        return list(cls._collection().find({"role": "candidate"}))

    @classmethod
    def update_profile(cls, user_id: str, payload: dict):
        existing = cls.get_raw_by_id(user_id) or {}
        merged = {**existing, **payload}
        updated_payload = cls._build_profile_document(merged)
        updated_payload["updated_at"] = datetime.utcnow()
        cls._collection().update_one({"_id": ObjectId(user_id)}, {"$set": updated_payload})

    @classmethod
    def update_password_by_email(cls, email: str, password_hash: str):
        result = cls._collection().update_one(
            {"email": email.lower().strip()},
            {"$set": {"password": password_hash, "updated_at": datetime.utcnow()}},
        )
        return result.modified_count > 0
