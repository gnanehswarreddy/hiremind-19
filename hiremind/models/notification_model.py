from datetime import datetime

from bson import ObjectId
from flask import current_app


class NotificationModel:
    collection_name = "notifications"

    @classmethod
    def _collection(cls):
        return current_app.db[cls.collection_name]

    @classmethod
    def create(cls, user_id: str, title: str, message: str, category: str = "system", metadata: dict | None = None):
        payload = {
            "user_id": user_id,
            "title": title,
            "message": message,
            "category": category,
            "metadata": metadata or {},
            "read": False,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }
        result = cls._collection().insert_one(payload)
        return str(result.inserted_id)

    @classmethod
    def for_user(cls, user_id: str, unread_only: bool = False):
        filters = {"user_id": user_id}
        if unread_only:
            filters["read"] = False
        return list(cls._collection().find(filters).sort("created_at", -1))

    @classmethod
    def mark_read(cls, notification_id: str):
        if not ObjectId.is_valid(notification_id):
            return
        cls._collection().update_one(
            {"_id": ObjectId(notification_id)},
            {"$set": {"read": True, "updated_at": datetime.utcnow()}},
        )
