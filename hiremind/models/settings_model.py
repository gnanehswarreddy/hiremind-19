from datetime import datetime

from flask import current_app


class UserSettingsModel:
    collection_name = "user_settings"

    @classmethod
    def _collection(cls):
        return current_app.db[cls.collection_name]

    @classmethod
    def get_for_user(cls, user_id: str):
        return cls._collection().find_one({"user_id": user_id})

    @classmethod
    def upsert_for_user(cls, user_id: str, payload: dict):
        cls._collection().update_one(
            {"user_id": user_id},
            {
                "$set": {
                    **payload,
                    "user_id": user_id,
                    "updated_at": datetime.utcnow(),
                },
                "$setOnInsert": {"created_at": datetime.utcnow()},
            },
            upsert=True,
        )
