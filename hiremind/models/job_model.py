from datetime import datetime

from bson import ObjectId
from flask import current_app

from db import run_in_transaction
from services.embeddings import build_search_text, generate_embedding


class JobModel:
    collection_name = "jobs"

    @classmethod
    def _collection(cls):
        return current_app.db[cls.collection_name]

    @classmethod
    def _build_job_document(cls, payload: dict) -> dict:
        search_text = build_search_text(
            [
                payload.get("title"),
                payload.get("description"),
                payload.get("location"),
                payload.get("work_mode"),
                payload.get("experience_level"),
                ", ".join(payload.get("skills", [])),
                ", ".join(payload.get("cognitive_traits", [])),
            ]
        )
        return {
            **payload,
            "search_text": search_text,
            "embedding": generate_embedding(search_text),
            "embedding_status": "ready",
        }

    @classmethod
    def create_job(
        cls,
        recruiter_id: str,
        title: str,
        description: str,
        skills: list[str],
        cognitive_traits: list[str],
        experience_level: str,
        job_type: str | None = None,
        location: str | None = None,
        work_mode: str | None = None,
        salary_min: int | None = None,
        salary_max: int | None = None,
        deadline: datetime | None = None,
        parsed_data: dict | None = None,
        representation: dict | None = None,
    ):
        now = datetime.utcnow()
        payload = cls._build_job_document(
            {
                "recruiter_id": recruiter_id,
                "title": title,
                "description": description,
                "skills": skills,
                "cognitive_traits": cognitive_traits,
                "experience_level": experience_level,
                "job_type": job_type,
                "location": location,
                "work_mode": work_mode,
                "salary_min": salary_min,
                "salary_max": salary_max,
                "deadline": deadline,
                "parsed_data": parsed_data or {},
                "representation": representation or {},
                "created_at": now,
                "updated_at": now,
            }
        )
        result = cls._collection().insert_one(payload)
        return str(result.inserted_id)

    @classmethod
    def update_job(cls, job_id: str, payload: dict):
        if not ObjectId.is_valid(job_id):
            return False
        existing = cls.get_job(job_id)
        if not existing:
            return False
        merged = cls._build_job_document({**existing, **payload})
        merged["updated_at"] = datetime.utcnow()
        cls._collection().update_one({"_id": ObjectId(job_id)}, {"$set": merged})
        return True

    @classmethod
    def delete_job(cls, job_id: str):
        if not ObjectId.is_valid(job_id):
            return False
        result = cls._collection().delete_one({"_id": ObjectId(job_id)})
        return result.deleted_count > 0

    @classmethod
    def all_jobs(cls):
        return list(cls._collection().find().sort("created_at", -1))

    @classmethod
    def jobs_for_recruiter(cls, recruiter_id: str):
        return list(cls._collection().find({"recruiter_id": recruiter_id}).sort("created_at", -1))

    @classmethod
    def get_job(cls, job_id: str):
        if not ObjectId.is_valid(job_id):
            return None
        return cls._collection().find_one({"_id": ObjectId(job_id)})


class ApplicationModel:
    collection_name = "applications"

    @classmethod
    def _collection(cls):
        return current_app.db[cls.collection_name]

    @classmethod
    def apply(cls, candidate_id: str, job_id: str):
        def callback(session):
            existing = cls._collection().find_one({"candidate_id": candidate_id, "job_id": job_id}, session=session)
            if existing:
                return False
            now = datetime.utcnow()
            job_object_id = ObjectId(job_id) if ObjectId.is_valid(job_id) else None
            cls._collection().insert_one(
                {
                    "candidate_id": candidate_id,
                    "job_id": job_id,
                    "job_object_id": job_object_id,
                    "status": "submitted",
                    "source": "platform",
                    "created_at": now,
                    "updated_at": now,
                },
                session=session,
            )
            return True

        return run_in_transaction(callback)

    @classmethod
    def candidate_applications(cls, candidate_id: str):
        return list(cls._collection().find({"candidate_id": candidate_id}).sort("created_at", -1))

    @classmethod
    def recruiter_applications(cls, recruiter_id: str):
        jobs = JobModel.jobs_for_recruiter(recruiter_id)
        job_ids = [str(job["_id"]) for job in jobs]
        return list(cls._collection().find({"job_id": {"$in": job_ids}}).sort("created_at", -1))

    @classmethod
    def update_status(cls, application_id: str, status: str):
        if ObjectId.is_valid(application_id):
            cls._collection().update_one(
                {"_id": ObjectId(application_id)},
                {"$set": {"status": status, "updated_at": datetime.utcnow()}},
            )

    @classmethod
    def delete(cls, application_id: str):
        if not ObjectId.is_valid(application_id):
            return False
        result = cls._collection().delete_one({"_id": ObjectId(application_id)})
        return result.deleted_count > 0
