# HireMind MongoDB Platform

## Core Principle

MongoDB is the primary and only database for HireMind. Every major module persists data in MongoDB Atlas through `pymongo`.

## Connection Layer

- Centralized in [db.py](/c:/Users/Gnaneshwar%20Reddy/OneDrive/Desktop/HIRE-MIND%20CODEX/hiremind/db.py)
- Secure URI loading through `.env` via `MONGO_URI`
- Reusable `MongoClient`, `Database`, `GridFSBucket`, and transaction helpers

## Collections

- `users`: auth identity, profile, profile image path, embedded profile metadata, embeddings
- `auth_sessions`: login session tracking
- `user_settings`: preferences and notification settings
- `resumes`: structured resume data, scores, GridFS file reference, embeddings
- `jobs`: job posts, searchable text, embeddings
- `applications`: job history and apply status
- `match_scores`: user-job ranking outputs
- `ai_results`: resume analysis and AI outputs
- `recommendations`: recommendation snapshots
- `messages`: recruiter and candidate communication
- `notifications`: in-app system updates
- `activity_logs`: login, resume edits, apply actions, settings edits

## Index Strategy

Implemented in `db.ensure_indexes()`:

- unique email index
- role and timestamp indexes
- user/job/application relationship indexes
- text indexes on `search_text`
- notification and message access indexes

Atlas Search / Vector index bootstrap is in [mongo_bootstrap.py](/c:/Users/Gnaneshwar%20Reddy/OneDrive/Desktop/HIRE-MIND%20CODEX/hiremind/mongo_bootstrap.py).

Run:

```bash
python mongo_bootstrap.py
```

## Vector Search

Embeddings are generated in [services/embeddings.py](/c:/Users/Gnaneshwar%20Reddy/OneDrive/Desktop/HIRE-MIND%20CODEX/hiremind/services/embeddings.py).

- Preferred: `sentence-transformers`
- Fallback: deterministic hashed embedding

Example vector query:

```python
from services.mongo_search import hybrid_job_search

results = hybrid_job_search("remote python backend role with mongodb")
for item in results:
    print(item["title"], item["score"])
```

## Full-Text Search

Example keyword query:

```python
from services.mongo_search import keyword_job_search

results = keyword_job_search("flask mongodb react")
```

## Aggregation Examples

See [services/mongo_analytics.py](/c:/Users/Gnaneshwar%20Reddy/OneDrive/Desktop/HIRE-MIND%20CODEX/hiremind/services/mongo_analytics.py)

- recruiter dashboard rollups
- application status overview
- user activity summaries

Example:

```python
from services.mongo_analytics import application_status_overview

print(application_status_overview())
```

## Real-Time Change Streams

See [services/realtime.py](/c:/Users/Gnaneshwar%20Reddy/OneDrive/Desktop/HIRE-MIND%20CODEX/hiremind/services/realtime.py)

Example:

```python
from services.realtime import stream_notifications

with stream_notifications() as stream:
    for change in stream:
        print(change["fullDocument"])
```

## GridFS

Resume source files are stored through GridFS and referenced by `document_file_id` inside `resumes`.

## Transactions

Job applications use MongoDB transactions in `ApplicationModel.apply()` through `db.run_in_transaction(...)`.

## CRUD Entry Points

### Users

```python
from models.user_model import UserModel

user_id = UserModel.create_user("Asha", "asha@example.com", "<hash>", "candidate")
user = UserModel.get_raw_by_id(user_id)
UserModel.update_profile(user_id, {"location": "Hyderabad"})
```

### Resume Builder

```python
from models.resume_model import ResumeModel

resume_id = ResumeModel.create_resume(
    user_id="...",
    filename="resume.pdf",
    content="Python Flask MongoDB",
    parsed_data={"skills": ["python", "flask", "mongodb"]},
    scores={"final_score": 88},
)
resume = ResumeModel.get_resume(resume_id)
ResumeModel.update_resume(resume_id, {"scores": {"final_score": 90}})
```

### Jobs and Applications

```python
from models.job_model import JobModel, ApplicationModel

job_id = JobModel.create_job("recruiter-id", "AI Engineer", "Build AI workflows", ["python"], ["analytical"], "2-4 years")
job = JobModel.get_job(job_id)
ApplicationModel.apply("candidate-id", job_id)
```

### AI Results

```python
from models.ai_model import AIResultModel, RecommendationModel

AIResultModel.create("user-id", "resume", "resume-id", "analysis", {"score": 91})
RecommendationModel.replace_for_user("user-id", [{"job_id": "1", "job_title": "AI Engineer"}])
```

### Messaging / Notifications

```python
from models.message_model import MessageModel
from models.notification_model import NotificationModel

MessageModel.create("recruiter-id", "candidate-id", "We liked your profile.")
NotificationModel.create("candidate-id", "Interview update", "Your application has moved forward.", "application")
```

### Settings

```python
from models.settings_model import UserSettingsModel

UserSettingsModel.upsert_for_user("user-id", {"theme": "Dark", "language": "English"})
```

### Activity Tracking

```python
from models.activity_model import ActivityModel

ActivityModel.log("user-id", "apply_job", {"job_id": "..."})
```
