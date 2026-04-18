from db import get_collection


def recruiter_dashboard_analytics(recruiter_id: str) -> list[dict]:
    jobs = get_collection("jobs")
    pipeline = [
        {"$match": {"recruiter_id": recruiter_id}},
        {
            "$lookup": {
                "from": "applications",
                "localField": "_id",
                "foreignField": "job_object_id",
                "as": "applications",
            }
        },
        {
            "$project": {
                "title": 1,
                "created_at": 1,
                "application_count": {"$size": "$applications"},
            }
        },
        {"$sort": {"application_count": -1, "created_at": -1}},
    ]
    return list(jobs.aggregate(pipeline))


def application_status_overview() -> list[dict]:
    applications = get_collection("applications")
    pipeline = [
        {"$group": {"_id": "$status", "count": {"$sum": 1}}},
        {"$project": {"status": "$_id", "count": 1, "_id": 0}},
        {"$sort": {"count": -1}},
    ]
    return list(applications.aggregate(pipeline))


def user_activity_summary(user_id: str) -> list[dict]:
    activity = get_collection("activity_logs")
    pipeline = [
        {"$match": {"user_id": user_id}},
        {"$group": {"_id": "$action", "count": {"$sum": 1}}},
        {"$project": {"action": "$_id", "count": 1, "_id": 0}},
        {"$sort": {"count": -1}},
    ]
    return list(activity.aggregate(pipeline))
