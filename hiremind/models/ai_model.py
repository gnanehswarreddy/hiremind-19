from datetime import datetime

from bson import ObjectId
from flask import current_app


class AIResultModel:
    collection_name = "ai_results"

    @classmethod
    def _collection(cls):
        return current_app.db[cls.collection_name]

    @classmethod
    def create(cls, user_id: str, source_type: str, source_id: str, result_type: str, payload: dict):
        result = cls._collection().insert_one(
            {
                "user_id": user_id,
                "source_type": source_type,
                "source_id": source_id,
                "result_type": result_type,
                "payload": payload,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
            }
        )
        return str(result.inserted_id)

    @classmethod
    def for_user(cls, user_id: str, result_type: str | None = None):
        filters = {"user_id": user_id}
        if result_type:
            filters["result_type"] = result_type
        return list(cls._collection().find(filters).sort("created_at", -1))


class RecommendationModel:
    collection_name = "recommendations"

    @classmethod
    def _collection(cls):
        return current_app.db[cls.collection_name]

    @classmethod
    def replace_for_user(cls, user_id: str, items: list[dict], source_resume_id: str | None = None):
        cls._collection().delete_many({"user_id": user_id})
        if not items:
            return
        cls._collection().insert_many(
            [
                {
                    "user_id": user_id,
                    "source_resume_id": source_resume_id,
                    "rank": index + 1,
                    **item,
                    "created_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow(),
                }
                for index, item in enumerate(items)
            ]
        )

    @classmethod
    def for_user(cls, user_id: str):
        return list(cls._collection().find({"user_id": user_id}).sort("rank", 1))

    @classmethod
    def delete(cls, recommendation_id: str):
        if not ObjectId.is_valid(recommendation_id):
            return False
        result = cls._collection().delete_one({"_id": ObjectId(recommendation_id)})
        return result.deleted_count > 0
