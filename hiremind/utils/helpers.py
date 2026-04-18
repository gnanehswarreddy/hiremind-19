from bson import ObjectId
from flask import current_app


def parse_comma_list(value: str) -> list[str]:
    return sorted({item.strip().lower() for item in value.split(",") if item.strip()})


def active_role(user):
    return getattr(user, "role", None)


def fetch_user_name(user_id: str) -> str:
    if not ObjectId.is_valid(user_id):
        return "Unknown"
    user = current_app.db["users"].find_one({"_id": ObjectId(user_id)})
    return user["name"] if user else "Unknown"
