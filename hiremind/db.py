import os
from collections.abc import Callable
from contextlib import suppress

from dotenv import load_dotenv
from gridfs import GridFSBucket
from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.collection import Collection
from pymongo.database import Database
from pymongo.errors import OperationFailure, PyMongoError


load_dotenv()

_mongo_client: MongoClient | None = None
_database: Database | None = None
_gridfs_bucket: GridFSBucket | None = None


def get_mongo_client() -> MongoClient:
    global _mongo_client

    if _mongo_client is not None:
        return _mongo_client

    mongo_uri = os.environ.get("MONGO_URI")
    if not mongo_uri:
        raise RuntimeError("MONGO_URI is not set. Add it to your environment or .env file.")

    try:
        client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000, retryWrites=True)
        client.admin.command("ping")
    except PyMongoError as exc:
        raise RuntimeError(f"Failed to connect to MongoDB: {exc}") from exc

    _mongo_client = client
    return _mongo_client


def get_database(db_name: str | None = None) -> Database:
    global _database

    if _database is not None and db_name is None:
        return _database

    database_name = db_name or os.environ.get("DB_NAME", "hiremind")

    try:
        database = get_mongo_client()[database_name]
    except PyMongoError as exc:
        raise RuntimeError(f"Failed to access MongoDB database '{database_name}': {exc}") from exc

    if db_name is None:
        _database = database

    return database


def get_collection(name: str, db_name: str | None = None) -> Collection:
    return get_database(db_name)[name]


def get_gridfs_bucket(bucket_name: str = "documents") -> GridFSBucket:
    global _gridfs_bucket

    if _gridfs_bucket is not None and bucket_name == "documents":
        return _gridfs_bucket

    bucket = GridFSBucket(get_database(), bucket_name=bucket_name)
    if bucket_name == "documents":
        _gridfs_bucket = bucket
    return bucket


def run_in_transaction(callback: Callable, *args, **kwargs):
    client = get_mongo_client()
    with client.start_session() as session:
        return session.with_transaction(lambda s: callback(s, *args, **kwargs))


def safe_watch(collection_name: str, pipeline: list | None = None):
    collection = get_collection(collection_name)
    try:
        return collection.watch(pipeline or [], full_document="updateLookup")
    except PyMongoError:
        return None


def _safe_create_index(collection: Collection, keys: list[tuple], **kwargs):
    with suppress(OperationFailure):
        collection.create_index(keys, **kwargs)


def ensure_indexes():
    users = get_collection("users")
    resumes = get_collection("resumes")
    jobs = get_collection("jobs")
    applications = get_collection("applications")
    messages = get_collection("messages")
    notifications = get_collection("notifications")
    recommendations = get_collection("recommendations")
    auth_sessions = get_collection("auth_sessions")
    settings = get_collection("user_settings")
    activity_logs = get_collection("activity_logs")
    match_scores = get_collection("match_scores")
    ai_results = get_collection("ai_results")

    _safe_create_index(users, [("email", ASCENDING)], unique=True)
    _safe_create_index(users, [("role", ASCENDING), ("updated_at", DESCENDING)])
    _safe_create_index(users, [("profile_embedding_status", ASCENDING)])
    _safe_create_index(users, [("search_text", "text")])

    _safe_create_index(resumes, [("user_id", ASCENDING), ("created_at", DESCENDING)])
    _safe_create_index(resumes, [("document_file_id", ASCENDING)])
    _safe_create_index(resumes, [("search_text", "text")])

    _safe_create_index(jobs, [("recruiter_id", ASCENDING), ("created_at", DESCENDING)])
    _safe_create_index(jobs, [("location", ASCENDING), ("work_mode", ASCENDING)])
    _safe_create_index(jobs, [("search_text", "text")])

    _safe_create_index(applications, [("candidate_id", ASCENDING), ("job_id", ASCENDING)], unique=True)
    _safe_create_index(applications, [("job_id", ASCENDING), ("status", ASCENDING)])
    _safe_create_index(applications, [("candidate_id", ASCENDING), ("created_at", DESCENDING)])

    _safe_create_index(messages, [("conversation_id", ASCENDING), ("created_at", DESCENDING)])
    _safe_create_index(messages, [("participants", ASCENDING)])

    _safe_create_index(notifications, [("user_id", ASCENDING), ("read", ASCENDING), ("created_at", DESCENDING)])
    _safe_create_index(recommendations, [("user_id", ASCENDING), ("created_at", DESCENDING)])
    _safe_create_index(auth_sessions, [("user_id", ASCENDING), ("created_at", DESCENDING)])
    _safe_create_index(settings, [("user_id", ASCENDING)], unique=True)
    _safe_create_index(activity_logs, [("user_id", ASCENDING), ("created_at", DESCENDING)])
    _safe_create_index(match_scores, [("user_id", ASCENDING), ("job_id", ASCENDING)], unique=True)
    _safe_create_index(ai_results, [("user_id", ASCENDING), ("result_type", ASCENDING), ("created_at", DESCENDING)])


def ensure_search_indexes():
    db = get_database()
    search_definitions = [
        (
            "jobs",
            "jobs_hybrid_search",
            {
                "fields": {
                    "search_text": {"type": "string"},
                    "embedding": {
                        "type": "vector",
                        "numDimensions": 256,
                        "similarity": "cosine",
                    },
                }
            },
        ),
        (
            "resumes",
            "resumes_hybrid_search",
            {
                "fields": {
                    "search_text": {"type": "string"},
                    "embedding": {
                        "type": "vector",
                        "numDimensions": 256,
                        "similarity": "cosine",
                    },
                }
            },
        ),
        (
            "users",
            "users_hybrid_search",
            {
                "fields": {
                    "search_text": {"type": "string"},
                    "profile_embedding": {
                        "type": "vector",
                        "numDimensions": 256,
                        "similarity": "cosine",
                    },
                }
            },
        ),
    ]

    for collection, index_name, definition in search_definitions:
        with suppress(OperationFailure, PyMongoError):
            db.command(
                {
                    "createSearchIndexes": collection,
                    "indexes": [{"name": index_name, "definition": definition}],
                }
            )


def initialize_mongo(app):
    try:
        app.mongo_client = get_mongo_client()
        app.db = get_database(app.config.get("DB_NAME"))
        app.gridfs_bucket = get_gridfs_bucket()
        ensure_indexes()
    except RuntimeError as exc:
        app.logger.error(str(exc))
        raise
