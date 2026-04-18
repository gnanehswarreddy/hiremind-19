from db import get_collection
from services.embeddings import generate_embedding


def hybrid_job_search(query: str, limit: int = 10) -> list[dict]:
    collection = get_collection("jobs")
    pipeline = [
        {
            "$vectorSearch": {
                "index": "jobs_hybrid_search",
                "path": "embedding",
                "queryVector": generate_embedding(query),
                "numCandidates": max(50, limit * 5),
                "limit": limit,
            }
        },
        {
            "$project": {
                "title": 1,
                "description": 1,
                "skills": 1,
                "location": 1,
                "work_mode": 1,
                "score": {"$meta": "vectorSearchScore"},
            }
        },
    ]
    return list(collection.aggregate(pipeline))


def keyword_job_search(query: str, limit: int = 10) -> list[dict]:
    collection = get_collection("jobs")
    pipeline = [
        {"$match": {"$text": {"$search": query}}},
        {"$addFields": {"text_score": {"$meta": "textScore"}}},
        {"$sort": {"text_score": -1, "created_at": -1}},
        {"$limit": limit},
    ]
    return list(collection.aggregate(pipeline))
