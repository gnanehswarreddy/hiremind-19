from datetime import datetime

from bson import ObjectId
from flask import current_app


class ComparisonModel:
    collection_name = "comparisons"

    @classmethod
    def _collection(cls):
        return current_app.db[cls.collection_name]

    @classmethod
    def create(
        cls,
        user_id: str,
        job_url: str,
        result: dict,
        job_snapshot: dict | None = None,
        resume_snapshot: dict | None = None,
        metadata: dict | None = None,
    ):
        now = datetime.utcnow()
        payload = {
            "user_id": user_id,
            "job_url": job_url,
            "a3_score": result.get("a3_score", 0),
            "alignment": result.get("alignment", 0),
            "depth": result.get("depth", 0),
            "adaptability": result.get("adaptability", 0),
            "hiring_probability": result.get("hiring_probability", 0),
            "skill_gaps": result.get("skill_gaps", []),
            "suggestions": result.get("suggestions", []),
            "simulation": result.get("simulation", {}),
            "results": result,
            "job_snapshot": job_snapshot or {},
            "resume_snapshot": resume_snapshot or {},
            "metadata": metadata or {},
            "created_at": now,
            "updated_at": now,
        }
        created = cls._collection().insert_one(payload)
        return str(created.inserted_id)

    @classmethod
    def latest_for_user(cls, user_id: str):
        return cls._collection().find_one({"user_id": user_id}, sort=[("created_at", -1)])

    @classmethod
    def for_user(cls, user_id: str, limit: int = 5):
        return list(cls._collection().find({"user_id": user_id}).sort("created_at", -1).limit(limit))

    @classmethod
    def get(cls, comparison_id: str):
        if not ObjectId.is_valid(comparison_id):
            return None
        return cls._collection().find_one({"_id": ObjectId(comparison_id)})
