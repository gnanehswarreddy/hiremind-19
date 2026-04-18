from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required

from ai_core import chat as ai_chat
from ai_core import explain_score, generate_insights, improve_resume, recommend_jobs, simulate_improvement
from models.ai_model import AIResultModel
from models.comparison_model import ComparisonModel
from models.job_model import JobModel
from models.resume_model import ResumeModel
from models.user_model import UserModel
from services.resume_comparator import compare_parsed_job_and_resume, normalize_job_payload, normalize_resume_payload
from utils.security import role_required, sanitize_text

ai_bp = Blueprint("ai_core", __name__)


def _latest_candidate_context(user_id: str) -> dict:
    latest_resume = ResumeModel.latest_for_user(user_id)
    latest_comparison = ComparisonModel.latest_for_user(user_id)
    explanation = explain_score(latest_comparison) if latest_comparison else {}
    return {
        "resume": latest_resume,
        "comparison": latest_comparison,
        "explanation": explanation,
    }


@ai_bp.route("/ai/chat", methods=["POST"])
@login_required
def chat():
    payload = request.get_json(silent=True) or {}
    query = sanitize_text(payload.get("query", "") or "")
    if not query:
        return jsonify({"error": "Query is required."}), 400

    context = payload.get("context") or {}
    if current_user.role == "candidate":
        context = {**_latest_candidate_context(current_user.id), **context}
    result = ai_chat(query, context)
    AIResultModel.create(current_user.id, "ai_chat", current_user.id, "chat_response", {"query": query, **result})
    return jsonify(result)


@ai_bp.route("/ai/improve-resume", methods=["POST"])
@login_required
@role_required("candidate")
def improve_resume_route():
    latest_resume = ResumeModel.latest_for_user(current_user.id)
    latest_comparison = ComparisonModel.latest_for_user(current_user.id)
    if not latest_resume or not latest_comparison:
        return jsonify({"error": "Run a resume comparison first."}), 400

    job_context = latest_comparison.get("job_snapshot", {}) or latest_comparison.get("meta", {}).get("job", {})
    resume_context = normalize_resume_payload(latest_resume)
    result = improve_resume(resume_context, normalize_job_payload(job_context), latest_comparison)
    AIResultModel.create(current_user.id, "resume", str(latest_resume.get("_id", "")), "resume_improvement", result)
    return jsonify(result)


@ai_bp.route("/ai/generate-insights", methods=["POST"])
@login_required
@role_required("recruiter")
def generate_insights_route():
    payload = request.get_json(silent=True) or {}
    candidate_id = sanitize_text(payload.get("candidate_id", "") or "")
    job_id = sanitize_text(payload.get("job_id", "") or "")
    candidate_doc = UserModel.get_raw_by_id(candidate_id)
    latest_resume = ResumeModel.latest_for_user(candidate_id)
    if not candidate_doc or not latest_resume:
        return jsonify({"error": "Candidate or resume not found."}), 404

    job = JobModel.get_job(job_id) if job_id else None
    comparison = compare_parsed_job_and_resume(
        normalize_job_payload(job or {"title": "General role", "description": latest_resume.get("content", ""), "skills": latest_resume.get("parsed_data", {}).get("skills", [])}),
        normalize_resume_payload(latest_resume),
    )
    result = generate_insights(candidate_doc, comparison, job or {})
    AIResultModel.create(current_user.id, "candidate", candidate_id, "recruiter_insights", result)
    return jsonify(result)


@ai_bp.route("/recommend-jobs", methods=["GET"])
@login_required
@role_required("candidate")
def recommend_jobs_route():
    latest_resume = ResumeModel.latest_for_user(current_user.id)
    if not latest_resume:
        return jsonify({"items": []})
    items = recommend_jobs(latest_resume.get("parsed_data", {}), JobModel.all_jobs())
    AIResultModel.create(current_user.id, "candidate", current_user.id, "job_recommendations", {"items": items})
    return jsonify({"items": items})


@ai_bp.route("/compare", methods=["POST"])
@login_required
@role_required("candidate")
def compare_alias():
    from routes.candidate import compare_resume_api

    return compare_resume_api()


@ai_bp.route("/ai/simulate-improvement", methods=["POST"])
@login_required
def simulate_improvement_route():
    payload = request.get_json(silent=True) or {}
    if current_user.role == "candidate":
        latest_resume = ResumeModel.latest_for_user(current_user.id)
        latest_comparison = ComparisonModel.latest_for_user(current_user.id)
        if not latest_resume or not latest_comparison:
            return jsonify({"error": "Run a resume comparison first."}), 400
        result = simulate_improvement(normalize_resume_payload(latest_resume), latest_comparison.get("job_snapshot", {}), latest_comparison)
        return jsonify(result)

    candidate_id = sanitize_text(payload.get("candidate_id", "") or "")
    job_id = sanitize_text(payload.get("job_id", "") or "")
    latest_resume = ResumeModel.latest_for_user(candidate_id)
    job = JobModel.get_job(job_id) if job_id else None
    if not latest_resume or not job:
        return jsonify({"error": "Candidate resume and job are required."}), 400
    comparison = compare_parsed_job_and_resume(normalize_job_payload(job), normalize_resume_payload(latest_resume))
    return jsonify(simulate_improvement(normalize_resume_payload(latest_resume), normalize_job_payload(job), comparison))
