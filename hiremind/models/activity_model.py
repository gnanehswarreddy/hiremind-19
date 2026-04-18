from datetime import datetime

from flask import current_app


class ActivityModel:
    collection_name = "activity_logs"

    @classmethod
    def _collection(cls):
        return current_app.db[cls.collection_name]

    @classmethod
    def log(cls, user_id: str | None, action: str, metadata: dict | None = None):
        cls._collection().insert_one(
            {
                "user_id": user_id,
                "action": action,
                "metadata": metadata or {},
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
            }
        )

    @classmethod
    def for_user(cls, user_id: str):
        return list(cls._collection().find({"user_id": user_id}).sort("created_at", -1))
