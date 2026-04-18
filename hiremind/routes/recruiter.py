from collections import Counter
from datetime import datetime, timedelta

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from flask_wtf import FlaskForm
from wtforms import DateField, HiddenField, RadioField, SelectField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Length, Optional

from models.activity_model import ActivityModel
from models.job_model import ApplicationModel, JobModel
from models.message_model import MessageModel
from models.notification_model import NotificationModel
from models.resume_model import ResumeModel
from models.user_model import UserModel
from services.job_models import job_parsing_model, job_representation_model
from services.system_core import rank_candidates_for_job
from utils.security import role_required, sanitize_text
from utils.helpers import parse_comma_list

recruiter_bp = Blueprint("recruiter", __name__, url_prefix="/recruiter")


class JobForm(FlaskForm):
    title = StringField("Job title", validators=[DataRequired(), Length(min=3, max=120)])
    job_type = RadioField("Job type", choices=[("Full-time", "Full-time"), ("Part-time", "Part-time"), ("Contract", "Contract"), ("Internship", "Internship")], default="Full-time", validators=[DataRequired()])
    location = StringField("Location", validators=[Optional(), Length(max=120)])
    work_mode = SelectField("Work mode", choices=[("Hybrid", "Hybrid"), ("Remote", "Remote"), ("On-site", "On-site")], default="Hybrid", validators=[DataRequired()])
    description = TextAreaField("Description", validators=[DataRequired(), Length(min=40, max=3000)])
    skills = StringField("Required skills", validators=[DataRequired(), Length(max=300)])
    cognitive_traits = StringField("Cognitive traits", validators=[DataRequired(), Length(max=200)])
    experience_level = SelectField("Experience level", choices=[("0-1 years", "0-1 years"), ("2-4 years", "2-4 years"), ("5+ years", "5+ years")], validators=[DataRequired()])
    salary_min = StringField("Salary min", validators=[Optional(), Length(max=20)])
    salary_max = StringField("Salary max", validators=[Optional(), Length(max=20)])
    deadline = DateField("Application deadline", validators=[Optional()], format="%Y-%m-%d")
    submit = SubmitField("Publish job")


class SettingsForm(FlaskForm):
    name = StringField("Team name", validators=[DataRequired(), Length(min=2, max=80)])
    submit = SubmitField("Save changes")


class RecruiterMessageForm(FlaskForm):
    receiver_id = HiddenField("Receiver", validators=[DataRequired()])
    message = StringField("Message", validators=[DataRequired(), Length(min=1, max=1000)])
    submit = SubmitField("Send")


def recruiter_chat_matches(chat: dict, query: str) -> bool:
    normalized_query = " ".join((query or "").lower().split())
    if not normalized_query:
        return True

    haystack = " ".join(
        [
            chat.get("name", ""),
            chat.get("message", ""),
            chat.get("status", ""),
            chat.get("job_title", ""),
        ]
    ).lower()
    return all(term in haystack for term in normalized_query.split())


def build_recruiter_message_threads(recruiter_id: str, query: str = "") -> tuple[list[dict], dict[str, list[dict]]]:
    chats: list[dict] = []
    threads: dict[str, list[dict]] = {}

    for message in MessageModel.for_user(recruiter_id):
        other_id = message["receiver_id"] if message["sender_id"] == recruiter_id else message["sender_id"]
        other_user = UserModel.get_by_id(other_id)
        if not other_user:
            continue

        conversation_id = message["conversation_id"]
        if conversation_id not in threads:
            chats.append(
                {
                    "id": conversation_id,
                    "name": other_user.name,
                    "message": message["text"],
                    "time": message["created_at"],
                    "status": "Candidate conversation",
                    "job_title": "Direct message",
                    "initials": "".join(part[:1].upper() for part in other_user.name.split()[:2]) or other_user.name[:1].upper(),
                    "receiver_id": other_user.id,
                }
            )
            threads[conversation_id] = []

        threads[conversation_id].append(
            {
                "sender": "me" if message["sender_id"] == recruiter_id else "them",
                "text": message["text"],
                "time": message["created_at"],
            }
        )

    chats.sort(key=lambda item: item["time"], reverse=True)
    filtered_chats = [chat for chat in chats if recruiter_chat_matches(chat, query)]
    filtered_threads = {chat["id"]: threads.get(chat["id"], []) for chat in filtered_chats}
    return filtered_chats, filtered_threads


@recruiter_bp.route("/dashboard")
@login_required
@role_required("recruiter")
def dashboard():
    jobs = JobModel.jobs_for_recruiter(current_user.id)
    applications = ApplicationModel.recruiter_applications(current_user.id)
    candidates = UserModel.all_candidates()
    job_application_counts = Counter(application["job_id"] for application in applications)
    unique_candidate_ids = {application["candidate_id"] for application in applications}
    shortlisted = [application for application in applications if application.get("status") == "shortlisted"]

    stats = {
        "jobs": len(jobs),
        "applications": len(applications),
        "candidates": len(unique_candidate_ids),
        "shortlisted": len(shortlisted),
    }

    recent_jobs = []
    for job in jobs[:5]:
        recent_jobs.append(
            {
                "title": job["title"],
                "applications": job_application_counts.get(str(job["_id"]), 0),
                "created_at": job["created_at"],
                "experience_level": job.get("experience_level", "Not specified"),
                "skills": job.get("skills", []),
                "job_id": str(job["_id"]),
            }
        )

    stream = []
    for application in applications[:5]:
        candidate = UserModel.get_by_id(application["candidate_id"])
        job = JobModel.get_job(application["job_id"])
        if not candidate or not job:
            continue
        stream.append(
            {
                "name": candidate.name,
                "action": application.get("status", "submitted").title(),
                "role": job["title"],
                "time_ago": humanize_time_ago(application.get("created_at")),
                "status": application.get("status", "submitted").lower(),
                "initials": "".join(part[:1].upper() for part in candidate.name.split()[:2]) or candidate.name[:1].upper(),
            }
        )

    skill_counts = Counter()
    for job in jobs:
        for skill in job.get("skills", []):
            skill_counts[skill.replace("_", " ").title()] += 1

    top_skill_total = max(skill_counts.values(), default=1)
    skills = [
        {
            "name": name,
            "value": round((count / top_skill_total) * 100),
            "count": count,
        }
        for name, count in skill_counts.most_common(5)
    ]

    status_counts = Counter(application.get("status", "submitted").lower() for application in applications)
    overview = [
        {"label": "New", "value": status_counts.get("submitted", 0), "tone": "violet"},
        {"label": "Shortlisted", "value": status_counts.get("shortlisted", 0), "tone": "amber"},
        {"label": "Interview", "value": status_counts.get("interview", 0), "tone": "green"},
        {"label": "Rejected", "value": status_counts.get("rejected", 0), "tone": "pink"},
    ]

    total_overview = max(len(applications), 1)
    for item in overview:
        item["percent"] = round((item["value"] / total_overview) * 100, 1) if applications else 0

    source_counts = Counter(application.get("source", "Untracked") for application in applications)
    sources = []
    total_sources = max(len(applications), 1)
    tones = ["violet", "blue", "green", "amber", "pink"]
    for index, (label, value) in enumerate(source_counts.most_common(5) or [("Untracked", 0)]):
        sources.append(
            {
                "label": label,
                "value": value,
                "percent": round((value / total_sources) * 100, 1) if applications else 0,
                "tone": tones[index % len(tones)],
            }
        )

    date_range = format_dashboard_range()

    return render_template(
        "recruiter/dashboard.html",
        stats=stats,
        recent_jobs=recent_jobs,
        stream=stream,
        skills=skills,
        overview=overview,
        sources=sources,
        date_range=date_range,
        recruiter_name=current_user.name,
    )


def humanize_time_ago(value):
    if not value:
        return "Just now"
    delta = datetime.utcnow() - value
    if delta < timedelta(minutes=1):
        return "Just now"
    if delta < timedelta(hours=1):
        minutes = max(1, int(delta.total_seconds() // 60))
        return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
    if delta < timedelta(days=1):
        hours = max(1, int(delta.total_seconds() // 3600))
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    days = max(1, delta.days)
    return f"{days} day{'s' if days != 1 else ''} ago"


def format_dashboard_range():
    end = datetime.utcnow().date()
    start = end - timedelta(days=6)
    return f"{start.strftime('%b %d')} - {end.strftime('%b %d, %Y')}"


@recruiter_bp.route("/create-job", methods=["GET", "POST"])
@login_required
@role_required("recruiter")
def create_job():
    form = JobForm()
    if form.validate_on_submit():
        parsed_job = job_parsing_model(
            job_description=sanitize_text(form.description.data),
            title=sanitize_text(form.title.data),
            seed_skills=parse_comma_list(form.skills.data),
            seed_traits=parse_comma_list(form.cognitive_traits.data),
            experience_level=form.experience_level.data,
        )
        represented_job = job_representation_model(parsed_job)
        job_id = JobModel.create_job(
            recruiter_id=current_user.id,
            title=parsed_job["title"],
            description=parsed_job["description"],
            skills=parsed_job["skills"],
            cognitive_traits=parsed_job["cognitive_traits"],
            experience_level=parsed_job["experience_level"],
            job_type=form.job_type.data,
            location=sanitize_text(form.location.data or ""),
            work_mode=form.work_mode.data,
            salary_min=parse_salary_value(form.salary_min.data),
            salary_max=parse_salary_value(form.salary_max.data),
            deadline=form.deadline.data,
            parsed_data=parsed_job,
            representation=represented_job,
        )
        flash("Job created successfully.", "success")
        return redirect(url_for("recruiter.matches", job_id=job_id))
    return render_template("recruiter/create_job.html", form=form)


def parse_salary_value(value: str | None) -> int | None:
    if not value:
        return None
    digits = "".join(char for char in value if char.isdigit())
    return int(digits) if digits else None


@recruiter_bp.route("/jobs")
@login_required
@role_required("recruiter")
def jobs():
    jobs = JobModel.jobs_for_recruiter(current_user.id)
    applications = ApplicationModel.recruiter_applications(current_user.id)
    job_application_counts = Counter(application["job_id"] for application in applications)
    shortlisted_counts = Counter(application["job_id"] for application in applications if application.get("status") == "shortlisted")
    new_counts = Counter(application["job_id"] for application in applications if application.get("status") == "submitted")

    rows = []
    total_views = 0
    total_shortlisted = 0
    growth_palette = {
        "jobs": 20,
        "applications": 32,
        "shortlisted": 18,
        "views": 15,
    }

    for job in jobs:
        job_id = str(job["_id"])
        application_count = job_application_counts.get(job_id, 0)
        shortlisted_count = shortlisted_counts.get(job_id, 0)
        new_count = new_counts.get(job_id, 0)
        view_count = max(application_count * 2 + shortlisted_count + 10, 12)
        status = "Published" if application_count or job.get("created_at") else "Draft"
        work_mode = job.get("work_mode") or "On-site"
        location = job.get("location") or work_mode
        description = (job.get("description") or "").strip()
        if len(description) > 128:
            description = f"{description[:125].rstrip()}..."
        elif not description:
            description = "We are looking for a strong contributor who can help the team ship real, measurable impact."

        total_views += view_count
        total_shortlisted += shortlisted_count

        rows.append(
            {
                "job": job,
                "applications": application_count,
                "shortlisted": shortlisted_count,
                "views": view_count,
                "new_applications": new_count,
                "new_shortlisted": 1 if shortlisted_count else 0,
                "status": status,
                "work_mode": work_mode,
                "location_label": f"{location}, India" if location not in {"Remote", "Location not specified"} and "," not in location else location,
                "description_preview": description,
            }
        )

    stats = {
        "jobs": len(jobs),
        "applications": len(applications),
        "shortlisted": total_shortlisted,
        "views": total_views,
    }

    stat_cards = [
        {"label": "Total Jobs", "value": stats["jobs"], "icon": "briefcase", "tone": "violet", "delta": growth_palette["jobs"]},
        {"label": "Total Applications", "value": stats["applications"], "icon": "people", "tone": "blue", "delta": growth_palette["applications"]},
        {"label": "Shortlisted", "value": stats["shortlisted"], "icon": "person", "tone": "green", "delta": growth_palette["shortlisted"]},
        {"label": "Views", "value": stats["views"], "icon": "eye", "tone": "amber", "delta": growth_palette["views"]},
    ]
    pagination = [1, 2, 3]

    return render_template("recruiter/jobs.html", stats=stats, rows=rows, stat_cards=stat_cards, pagination=pagination)


@recruiter_bp.route("/matches/<job_id>")
@login_required
@role_required("recruiter")
def matches(job_id):
    job = JobModel.get_job(job_id)
    if not job or job["recruiter_id"] != current_user.id:
        flash("Job not found.", "danger")
        return redirect(url_for("recruiter.jobs"))

    candidate_profiles = []
    for candidate in UserModel.all_candidates():
        latest_resume = ResumeModel.latest_for_user(str(candidate["_id"]))
        if latest_resume:
            candidate_profiles.append(
                {
                    "candidate": candidate,
                    "resume": latest_resume,
                    "profile": latest_resume["parsed_data"],
                }
            )

    ranked = rank_candidates_for_job(candidate_profiles, job)
    return render_template("recruiter/matches.html", job=job, ranked=ranked)


@recruiter_bp.route("/candidate/<id>")
@login_required
@role_required("recruiter")
def candidate_profile(id):
    candidate = UserModel.get_by_id(id)
    resumes = ResumeModel.for_user(id)
    if not candidate:
        flash("Candidate not found.", "danger")
        return redirect(url_for("recruiter.dashboard"))
    latest_resume = resumes[0] if resumes else None
    candidate_chat_id = MessageModel.build_conversation_id(current_user.id, candidate.id)
    return render_template(
        "recruiter/candidate_profile.html",
        candidate=candidate,
        latest_resume=latest_resume,
        resumes=resumes,
        candidate_chat_id=candidate_chat_id,
    )


@recruiter_bp.route("/applications", methods=["GET", "POST"])
@login_required
@role_required("recruiter")
def applications():
    if request.method == "POST":
        application_id = request.form.get("application_id", "")
        status = request.form.get("status", "")
        if status in {"shortlisted", "rejected", "submitted"}:
            ApplicationModel.update_status(application_id, status)
            flash("Application status updated.", "success")
        return redirect(url_for("recruiter.applications"))

    rows = []
    for application in ApplicationModel.recruiter_applications(current_user.id):
        job = JobModel.get_job(application["job_id"])
        candidate = UserModel.get_by_id(application["candidate_id"])
        if job and candidate:
            rows.append(
                {
                    "application": application,
                    "job": job,
                    "candidate": candidate,
                    "chat_id": MessageModel.build_conversation_id(current_user.id, candidate.id),
                }
            )
    return render_template("recruiter/applications.html", rows=rows)


@recruiter_bp.route("/messages")
@login_required
@role_required("recruiter")
def messages():
    search_query = sanitize_text(request.args.get("q", "") or "")
    chats, threads = build_recruiter_message_threads(current_user.id, search_query)
    active_chat_id = sanitize_text(request.args.get("chat", "") or "")
    active_chat = next((chat for chat in chats if chat["id"] == active_chat_id), None)
    if not active_chat:
        active_chat = chats[0] if chats else None

    form = RecruiterMessageForm()
    if active_chat:
        form.receiver_id.data = active_chat["receiver_id"]

    return render_template(
        "recruiter/messages.html",
        chats=chats,
        active_chat=active_chat,
        thread=threads.get(active_chat["id"], []) if active_chat else [],
        search_query=search_query,
        form=form,
    )


@recruiter_bp.route("/messages/send", methods=["POST"])
@login_required
@role_required("recruiter")
def send_message():
    form = RecruiterMessageForm()
    receiver_id = sanitize_text(request.form.get("receiver_id", "") or "")
    conversation_id = MessageModel.build_conversation_id(current_user.id, receiver_id) if receiver_id else ""
    if not form.validate_on_submit():
        flash("Enter a message before sending.", "danger")
        return redirect(url_for("recruiter.messages", chat=conversation_id))

    candidate = UserModel.get_by_id(form.receiver_id.data)
    if not candidate or candidate.role != "candidate":
        flash("Candidate conversation not found.", "danger")
        return redirect(url_for("recruiter.messages"))

    message_text = sanitize_text(form.message.data or "")
    if not message_text:
        flash("Enter a message before sending.", "danger")
        return redirect(url_for("recruiter.messages", chat=conversation_id))

    MessageModel.create(current_user.id, candidate.id, message_text)
    NotificationModel.create(candidate.id, "New recruiter message", f"{current_user.name} sent you a new message.", "message")
    ActivityModel.log(current_user.id, "send_message", {"receiver_id": candidate.id, "conversation_id": conversation_id})
    flash("Message sent.", "success")
    return redirect(url_for("recruiter.messages", chat=conversation_id))


@recruiter_bp.route("/analytics")
@login_required
@role_required("recruiter")
def analytics():
    jobs = JobModel.jobs_for_recruiter(current_user.id)
    applications = ApplicationModel.recruiter_applications(current_user.id)
    shortlisted = [a for a in applications if a["status"] == "shortlisted"]
    return render_template("recruiter/analytics.html", jobs=jobs, applications=applications, shortlisted=shortlisted)


@recruiter_bp.route("/settings", methods=["GET", "POST"])
@login_required
@role_required("recruiter")
def settings():
    form = SettingsForm(name=current_user.name)
    if form.validate_on_submit():
        UserModel.update_profile(current_user.id, {"name": sanitize_text(form.name.data)})
        flash("Settings updated.", "success")
        return redirect(url_for("recruiter.settings"))
    return render_template("recruiter/settings.html", form=form, contact_email=current_user.email)
