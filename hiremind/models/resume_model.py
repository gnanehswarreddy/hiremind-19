from datetime import datetime
from io import BytesIO

from bson import ObjectId
from gridfs.errors import NoFile
from flask import current_app

from db import get_gridfs_bucket
from services.embeddings import build_search_text, generate_embedding


class ResumeModel:
    collection_name = "resumes"

    @classmethod
    def _collection(cls):
        return current_app.db[cls.collection_name]

    @classmethod
    def _build_resume_document(cls, payload: dict) -> dict:
        parsed = payload.get("parsed_data", {}) or {}
        search_text = build_search_text(
            [
                payload.get("content"),
                payload.get("filename"),
                parsed.get("summary"),
                ", ".join(parsed.get("skills", [])),
                parsed.get("experience"),
                " ".join(parsed.get("education", [])) if isinstance(parsed.get("education"), list) else parsed.get("education"),
            ]
        )
        return {
            **payload,
            "search_text": search_text,
            "embedding": generate_embedding(search_text),
            "embedding_status": "ready",
        }

    @classmethod
    def create_resume(
        cls,
        user_id: str,
        filename: str,
        content: str,
        parsed_data: dict,
        scores: dict,
        algorithm_outputs: dict | None = None,
        original_file_bytes: bytes | None = None,
        content_type: str | None = None,
        sections: dict | None = None,
    ):
        now = datetime.utcnow()
        document_file_id = None
        if original_file_bytes:
            bucket = get_gridfs_bucket()
            document_file_id = bucket.upload_from_stream(
                filename,
                BytesIO(original_file_bytes),
                metadata={
                    "user_id": user_id,
                    "content_type": content_type or "application/octet-stream",
                    "created_at": now,
                },
            )

        payload = cls._build_resume_document(
            {
                "user_id": user_id,
                "filename": filename,
                "content": content,
                "parsed_data": parsed_data,
                "scores": scores,
                "sections": sections or {},
                "algorithm_outputs": algorithm_outputs or {},
                "document_file_id": document_file_id,
                "created_at": now,
                "updated_at": now,
            }
        )
        result = cls._collection().insert_one(payload)
        return str(result.inserted_id)

    @classmethod
    def update_resume(cls, resume_id: str, payload: dict):
        if not ObjectId.is_valid(resume_id):
            return False
        existing = cls.get_resume(resume_id)
        if not existing:
            return False
        merged = cls._build_resume_document({**existing, **payload})
        merged["updated_at"] = datetime.utcnow()
        cls._collection().update_one({"_id": ObjectId(resume_id)}, {"$set": merged})
        return True

    @classmethod
    def delete_resume(cls, resume_id: str):
        if not ObjectId.is_valid(resume_id):
            return False
        existing = cls.get_resume(resume_id)
        if not existing:
            return False
        file_id = existing.get("document_file_id")
        if file_id:
            try:
                get_gridfs_bucket().delete(file_id)
            except NoFile:
                pass
        result = cls._collection().delete_one({"_id": ObjectId(resume_id)})
        return result.deleted_count > 0

    @classmethod
    def for_user(cls, user_id: str):
        return list(cls._collection().find({"user_id": user_id}).sort("created_at", -1))

    @classmethod
    def latest_for_user(cls, user_id: str):
        return cls._collection().find_one({"user_id": user_id}, sort=[("created_at", -1)])

    @classmethod
    def get_resume(cls, resume_id: str):
        if not ObjectId.is_valid(resume_id):
            return None
        return cls._collection().find_one({"_id": ObjectId(resume_id)})
