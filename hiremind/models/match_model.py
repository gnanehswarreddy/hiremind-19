from datetime import datetime

from flask import current_app


class MatchScoreModel:
    collection_name = "match_scores"

    @classmethod
    def _collection(cls):
        return current_app.db[cls.collection_name]

    @classmethod
    def upsert(cls, user_id: str, job_id: str, payload: dict):
        document = {
            "user_id": user_id,
            "job_id": job_id,
            **payload,
            "updated_at": datetime.utcnow(),
        }
        cls._collection().update_one(
            {"user_id": user_id, "job_id": job_id},
            {"$set": document, "$setOnInsert": {"created_at": datetime.utcnow()}},
            upsert=True,
        )

    @classmethod
    def for_user(cls, user_id: str):
        return list(cls._collection().find({"user_id": user_id}).sort("updated_at", -1))
