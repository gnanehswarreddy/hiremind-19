from datetime import datetime

from bson import ObjectId
from flask import current_app


class MessageModel:
    collection_name = "messages"

    @classmethod
    def _collection(cls):
        return current_app.db[cls.collection_name]

    @classmethod
    def build_conversation_id(cls, user_a: str, user_b: str) -> str:
        return "::".join(sorted([user_a, user_b]))

    @classmethod
    def create(cls, sender_id: str, receiver_id: str, text: str, metadata: dict | None = None):
        payload = {
            "conversation_id": cls.build_conversation_id(sender_id, receiver_id),
            "participants": sorted([sender_id, receiver_id]),
            "sender_id": sender_id,
            "receiver_id": receiver_id,
            "text": text,
            "metadata": metadata or {},
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }
        result = cls._collection().insert_one(payload)
        return str(result.inserted_id)

    @classmethod
    def for_user(cls, user_id: str):
        return list(cls._collection().find({"participants": user_id}).sort("created_at", -1))

    @classmethod
    def conversation(cls, user_a: str, user_b: str):
        return list(
            cls._collection()
            .find({"conversation_id": cls.build_conversation_id(user_a, user_b)})
            .sort("created_at", 1)
        )

    @classmethod
    def delete(cls, message_id: str):
        if not ObjectId.is_valid(message_id):
            return False
        result = cls._collection().delete_one({"_id": ObjectId(message_id)})
        return result.deleted_count > 0
