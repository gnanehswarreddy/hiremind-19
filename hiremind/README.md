# HireMind

HireMind is a production-ready Flask and MongoDB hiring platform with candidate and recruiter dashboards, secure session authentication, resume scoring, and job-fit ranking.

## Features

- Session-based authentication with bcrypt password hashing and CSRF protection
- Candidate workflows for resume upload, resume builder, analysis, job discovery, recommendations, and applications
- Recruiter workflows for job creation, ranked candidate matching, application triage, and analytics
- Resume parsing, R3 scoring, and CFMA fit matching services
- Responsive SaaS-style UI built with Jinja2 templates and custom CSS

## Setup

1. Create and activate a virtual environment.
2. Install dependencies with `pip install -r requirements.txt`.
3. Create a `.env` file from `.env.example`.
4. Add your MongoDB connection string to `MONGO_URI` in `.env`.
5. Optional environment variables:

```bash
MONGO_URI=<PASTE_YOUR_MONGODB_URL_HERE>
DB_NAME=hiremind
SECRET_KEY=replace-me
```

6. Seed sample data with `python seed.py`.
7. Run the app with `python app.py`.
8. Open `http://127.0.0.1:5000`.

## MongoDB Integration

The project uses `pymongo` for MongoDB access and `python-dotenv` to load environment variables securely from `.env`.

The reusable connection lives in [db.py](/c:/Users/Gnaneshwar%20Reddy/OneDrive/Desktop/HIRE-MIND%20CODEX/hiremind/db.py). It:

- loads `MONGO_URI` from environment variables
- creates a reusable `MongoClient`
- verifies the connection with `ping`
- raises a clear error if MongoDB is unavailable

### Example `.env`

```bash
MONGO_URI=<PASTE_YOUR_MONGODB_URL_HERE>
DB_NAME=hiremind
SECRET_KEY=replace-me
```

### Loading environment variables with `python-dotenv`

```python
from dotenv import load_dotenv
import os

load_dotenv()
mongo_uri = os.environ.get("MONGO_URI")
```

### Example usage

```python
from db import get_database

db = get_database()

# Insert data
result = db["users"].insert_one({
    "name": "Demo User",
    "email": "demo@example.com",
})

print("Inserted id:", result.inserted_id)

# Fetch data
user = db["users"].find_one({"email": "demo@example.com"})
print(user)
```

## Sample Accounts

- Candidate: `candidate@hiremind.dev` / `Password123`
- Recruiter: `recruiter@hiremind.dev` / `Password123`

## Notes

- Resume upload accepts PDF and DOCX files up to 5 MB.
- The parser uses lightweight keyword extraction and heuristic trait detection.
- The R3 engine scores relevance, representation, readability, and a final weighted score.
- The CFMA engine ranks candidates using skill overlap, trait alignment, and experience alignment.

## Vercel Deployment

This repository is now set up to deploy from the repo root on Vercel using the Python runtime.

### Files added for deployment

- `api/index.py` wires Vercel requests into the Flask app
- `vercel.json` routes all traffic to the Python serverless function
- root `requirements.txt` points Vercel to `hiremind/requirements.txt`

### Required Vercel environment variables

```bash
MONGO_URI=<your-mongodb-connection-string>
DB_NAME=hiremind
SECRET_KEY=<strong-random-secret>
APP_BASE_URL=https://your-project-name.vercel.app
GOOGLE_CLIENT_ID=<optional>
GOOGLE_CLIENT_SECRET=<optional>
GOOGLE_REDIRECT_URI=https://your-project-name.vercel.app/auth/google/callback
LINKEDIN_CLIENT_ID=<optional>
LINKEDIN_CLIENT_SECRET=<optional>
LINKEDIN_REDIRECT_URI=https://your-project-name.vercel.app/auth/linkedin/callback
```

### Deploy commands

```bash
npx vercel login
npx vercel
npx vercel --prod
```

### Current serverless limitations

- Resume uploads work because files are temporarily written to a writable temp directory and then stored in MongoDB/GridFS.
- Profile photo uploads are not persisted on Vercel yet because the current implementation expects writable static files.
- PDF export from the resume builder falls back to the print-ready HTML view because `wkhtmltopdf` is not available in Vercel's serverless runtime.
