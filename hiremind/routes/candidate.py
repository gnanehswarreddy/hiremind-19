import os
import shutil
from tempfile import NamedTemporaryFile

from flask import Blueprint, current_app, flash, make_response, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from flask_wtf import FlaskForm
from werkzeug.utils import secure_filename
from wtforms import BooleanField, FileField, HiddenField, SelectField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Email, Length, Optional

from models.activity_model import ActivityModel
from models.ai_model import AIResultModel, RecommendationModel
from models.job_model import ApplicationModel, JobModel
from models.match_model import MatchScoreModel
from models.message_model import MessageModel
from models.notification_model import NotificationModel
from models.resume_model import ResumeModel
from models.settings_model import UserSettingsModel
from models.user_model import UserModel
from services.parser import read_resume_file
from services.improvement_engine import resume_improvement_engine
from services.system_core import analyze_resume_with_ses, match_candidate_to_job
from utils.helpers import fetch_user_name, parse_comma_list
from utils.security import allowed_file, role_required, sanitize_text

try:
    import pdfkit
except ImportError:
    pdfkit = None

candidate_bp = Blueprint("candidate", __name__, url_prefix="/candidate")


@candidate_bp.app_context_processor
def inject_candidate_shell():
    if not current_user.is_authenticated or getattr(current_user, "role", None) != "candidate":
        return {}

    latest_resume = ResumeModel.latest_for_user(current_user.id)
    user_doc = UserModel.get_raw_by_id(current_user.id) or {}
    name_parts = [part for part in current_user.name.split() if part]
    user_initials = "".join(part[:1].upper() for part in name_parts[:2]) or current_user.name[:1].upper()
    return {
        "candidate_shell_resume": latest_resume,
        "candidate_shell_initials": user_initials,
        "candidate_shell_image_path": user_doc.get("profile_image"),
    }


class ResumeUploadForm(FlaskForm):
    resume = FileField("Resume", validators=[DataRequired()])
    submit = SubmitField("Upload resume")


class ResumeBuilderForm(FlaskForm):
    name = StringField("Full name", validators=[DataRequired(), Length(min=2, max=80)])
    title = StringField("Job title", validators=[DataRequired(), Length(min=2, max=80)])
    email = StringField("Email", validators=[Optional(), Length(max=120)])
    phone = StringField("Phone", validators=[Optional(), Length(max=40)])
    location = StringField("Location", validators=[Optional(), Length(max=120)])
    linkedin = StringField("LinkedIn", validators=[Optional(), Length(max=160)])
    summary = TextAreaField("Professional summary", validators=[DataRequired(), Length(min=40, max=1500)])
    skills = TextAreaField("Skills", validators=[DataRequired(), Length(max=600)])
    experience = TextAreaField("Work experience", validators=[DataRequired(), Length(max=3000)])
    education = TextAreaField("Education", validators=[Optional(), Length(max=1800)])
    projects = TextAreaField("Projects", validators=[Optional(), Length(max=1800)])
    certifications = TextAreaField("Certifications", validators=[Optional(), Length(max=1800)])
    submit = SubmitField("Generate / Update Resume")


class SettingsForm(FlaskForm):
    name = StringField("Full name", validators=[DataRequired(), Length(min=2, max=80)])
    email = StringField("Email address", validators=[DataRequired(), Email(), Length(max=120)])
    phone = StringField("Phone number", validators=[Optional(), Length(max=40)])
    location = StringField("Location", validators=[Optional(), Length(max=120)])
    linkedin = StringField("LinkedIn profile", validators=[Optional(), Length(max=160)])
    role = StringField("Current role", validators=[Optional(), Length(max=80)])
    preferred_role = StringField("Preferred job role", validators=[Optional(), Length(max=80)])
    experience = SelectField(
        "Experience level",
        choices=[
            ("Fresher", "Fresher"),
            ("0-1 years", "0-1 years"),
            ("1-2 years", "1-2 years"),
            ("2-4 years", "2-4 years"),
            ("4-6 years", "4-6 years"),
            ("6+ years", "6+ years"),
        ],
        validators=[Optional()],
    )
    skills = StringField("Primary skills", validators=[Optional(), Length(max=220)])
    salary = StringField("Expected salary", validators=[Optional(), Length(max=60)])
    availability = SelectField(
        "Availability",
        choices=[
            ("Immediately", "Immediately"),
            ("Within 2 weeks", "Within 2 weeks"),
            ("Within 1 month", "Within 1 month"),
            ("Open to discuss", "Open to discuss"),
        ],
        validators=[Optional()],
    )
    theme = SelectField("Theme", choices=[("Light", "Light"), ("Dark", "Dark"), ("System", "System")], validators=[Optional()])
    language = SelectField("Language", choices=[("English", "English"), ("Hindi", "Hindi"), ("Telugu", "Telugu")], validators=[Optional()])
    timezone = SelectField(
        "Timezone",
        choices=[
            ("(GMT+05:30) Asia/Kolkata", "(GMT+05:30) Asia/Kolkata"),
            ("(GMT+04:00) Asia/Dubai", "(GMT+04:00) Asia/Dubai"),
            ("(GMT+00:00) UTC", "(GMT+00:00) UTC"),
        ],
        validators=[Optional()],
    )
    job_alerts = BooleanField("Job alerts")
    application_updates = BooleanField("Application updates")
    interview_reminders = BooleanField("Interview reminders")
    email_notifications = BooleanField("Email notifications")
    image = FileField("Profile photo")
    submit = SubmitField("Save changes")


class MessageReplyForm(FlaskForm):
    receiver_id = HiddenField("Receiver", validators=[DataRequired()])
    chat_id = HiddenField("Chat")
    message = StringField("Message", validators=[DataRequired(), Length(min=1, max=1000)])
    submit = SubmitField("Send")


def default_candidate_profile(user_doc: dict | None) -> dict:
    user_doc = user_doc or {}
    settings_doc = UserSettingsModel.get_for_user(current_user.id) or {}
    if not settings_doc:
        UserSettingsModel.upsert_for_user(
            current_user.id,
            {
                "theme": "Light",
                "language": "English",
                "timezone": "(GMT+05:30) Asia/Kolkata",
                "notifications": {
                    "job_alerts": True,
                    "application_updates": True,
                    "interview_reminders": True,
                    "email_notifications": True,
                },
            },
        )
        settings_doc = UserSettingsModel.get_for_user(current_user.id) or {}
    notification_settings = settings_doc.get("notifications", {})
    return {
        "name": user_doc.get("name", current_user.name),
        "email": user_doc.get("email", current_user.email),
        "phone": user_doc.get("phone", "+91 98765 43210"),
        "location": user_doc.get("location", "Hyderabad, Telangana, India"),
        "linkedin": user_doc.get("linkedin", "linkedin.com/in/candidate"),
        "role": user_doc.get("headline", "Frontend Developer"),
        "preferred_role": user_doc.get("preferred_role", "Software Engineer"),
        "experience": user_doc.get("experience_level", "2-4 years"),
        "skills": ", ".join(user_doc.get("skills", ["React", "JavaScript", "Tailwind CSS", "Node.js"])),
        "salary": user_doc.get("salary_expectation", "Rs 8,00,000"),
        "availability": user_doc.get("availability", "Immediately"),
        "theme": settings_doc.get("theme", "Light"),
        "language": settings_doc.get("language", "English"),
        "timezone": settings_doc.get("timezone", "(GMT+05:30) Asia/Kolkata"),
        "job_alerts": notification_settings.get("job_alerts", True),
        "application_updates": notification_settings.get("application_updates", True),
        "interview_reminders": notification_settings.get("interview_reminders", True),
        "email_notifications": notification_settings.get("email_notifications", True),
        "image_path": user_doc.get("profile_image"),
    }


def save_profile_image(file_storage) -> str | None:
    if not file_storage or not file_storage.filename:
        return None

    if not current_app.config.get("PROFILE_IMAGE_UPLOADS_ENABLED", True):
        return "__storage_unavailable__"

    filename = secure_filename(file_storage.filename)
    if not filename:
        return None

    if not allowed_file(filename, {"png", "jpg", "jpeg", "webp"}):
        return None

    avatar_folder = os.path.join(current_app.static_folder, "uploads", "avatars")
    try:
        os.makedirs(avatar_folder, exist_ok=True)
    except OSError:
        return "__storage_unavailable__"
    stored_name = f"{current_user.id}_{filename}"
    absolute_path = os.path.join(avatar_folder, stored_name)
    try:
        file_storage.save(absolute_path)
    except OSError:
        return "__storage_unavailable__"
    return f"uploads/avatars/{stored_name}"


def parse_multiline_entries(value: str) -> list[str]:
    return [line.strip(" -•\t") for line in (value or "").splitlines() if line.strip()]


def normalize_builder_payload(source: dict) -> dict:
    return {
        "name": sanitize_text(source.get("name", "") or ""),
        "title": sanitize_text(source.get("title", "") or ""),
        "email": sanitize_text(source.get("email", "") or ""),
        "phone": sanitize_text(source.get("phone", "") or ""),
        "location": sanitize_text(source.get("location", "") or ""),
        "linkedin": sanitize_text(source.get("linkedin", "") or ""),
        "summary": " ".join((source.get("summary", "") or "").split()),
        "skills": [item.strip() for item in (source.get("skills", "") or "").split(",") if item.strip()],
        "experience": parse_multiline_entries(source.get("experience", "") or ""),
        "education": parse_multiline_entries(source.get("education", "") or ""),
        "projects": parse_multiline_entries(source.get("projects", "") or ""),
        "certifications": parse_multiline_entries(source.get("certifications", "") or ""),
    }


def build_resume_content(data: dict) -> str:
    sections = [
        f"Name: {data['name']}",
        f"Title: {data['title']}",
        f"Email: {data['email']}",
        f"Phone: {data['phone']}",
        f"Location: {data['location']}",
        f"LinkedIn: {data['linkedin']}",
        f"Summary: {data['summary']}",
        f"Skills: {', '.join(data['skills'])}",
        f"Experience: {'; '.join(data['experience'])}",
        f"Education: {'; '.join(data['education'])}",
        f"Projects: {'; '.join(data['projects'])}",
        f"Certifications: {'; '.join(data['certifications'])}",
    ]
    return "\n".join(section for section in sections if section.split(': ', 1)[1].strip())


def detect_wkhtmltopdf() -> str | None:
    configured = current_app.config.get("WKHTMLTOPDF_PATH")
    if configured and os.path.exists(configured):
        return configured

    for candidate in (
        r"C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe",
        r"C:\Program Files (x86)\wkhtmltopdf\bin\wkhtmltopdf.exe",
    ):
        if os.path.exists(candidate):
            return candidate

    return shutil.which("wkhtmltopdf")


def pdfkit_configuration():
    if pdfkit is None:
        return None

    binary_path = detect_wkhtmltopdf()
    if not binary_path:
        return None

    return pdfkit.configuration(wkhtmltopdf=binary_path)


def build_match_breakdown(match: dict, resume_scores: dict | None, profile: dict) -> dict:
    resume_scores = resume_scores or {}
    profile = profile or {}
    completeness = profile.get("profile_completeness", 0) or 0
    final_score = resume_scores.get("final_score", 0) or 0
    missing_skills = len(match.get("sga", {}).get("missing_skills", []))

    project_strength = round(min(100, (final_score * 0.65) + (completeness * 0.35)))
    growth_potential = round(min(100, (completeness * 0.55) + (max(0, 100 - (missing_skills * 12)) * 0.45)))
    context_fit = round((match.get("cfma", {}).get("fit_score", 0) * 0.55) + (match.get("hcs", {}).get("holistic_score", 0) * 0.45))

    return {
        "skill": round(match.get("wsms", {}).get("skill_score", 0)),
        "exp": round(match.get("eas", {}).get("experience_score", 0)),
        "project": project_strength,
        "cognitive": round(match.get("cmm", {}).get("cognitive_fit_score", 0)),
        "growth": growth_potential,
        "context": context_fit,
    }


def chat_matches_filters(chat: dict, query: str, selected_tab: str) -> bool:
    if selected_tab == "recruiters" and chat.get("chat_type") != "direct":
        return False
    if selected_tab == "system" and chat.get("chat_type") == "direct":
        return False

    normalized_query = normalize_search_query(query)
    if not normalized_query:
        return True

    haystack = normalize_search_query(
        " ".join(
            [
                chat.get("name", ""),
                chat.get("message", ""),
                chat.get("status", ""),
                chat.get("job_title", ""),
            ]
        )
    )
    return all(term in haystack for term in normalized_query.split())


def build_message_threads(candidate_id: str, query: str = "", selected_tab: str = "all") -> tuple[list[dict], dict[str, list[dict]]]:
    chats: list[dict] = []
    threads: dict[str, list[dict]] = {}

    for message in MessageModel.for_user(candidate_id):
        other_id = message["receiver_id"] if message["sender_id"] == candidate_id else message["sender_id"]
        other_name = fetch_user_name(other_id)
        conversation_id = message["conversation_id"]

        if conversation_id not in threads:
            chats.append(
                {
                    "id": conversation_id,
                    "name": other_name,
                    "message": message["text"],
                    "time": message["created_at"],
                    "badge": 0,
                    "initials": "".join(part[:1].upper() for part in other_name.split()[:2]) or "HM",
                    "active": False,
                    "status": "Recruiter conversation",
                    "job_title": "Direct message",
                    "chat_type": "direct",
                    "reply_enabled": True,
                    "reply_target_id": other_id,
                }
            )
            threads[conversation_id] = []

        threads[conversation_id].append(
            {
                "sender": "me" if message["sender_id"] == candidate_id else "them",
                "text": message["text"],
                "time": message["created_at"],
            }
        )

    for application in ApplicationModel.candidate_applications(candidate_id):
        job = JobModel.get_job(application["job_id"])
        if not job:
            continue

        recruiter_name = fetch_user_name(job.get("recruiter_id", ""))
        event_time = application.get("updated_at") or application.get("created_at")
        chat_id = str(application["_id"])
        status_label = application.get("status", "submitted").title()
        summary = f"Application status: {status_label} for {job.get('title', 'role')}"

        chats.append(
            {
                "id": chat_id,
                "name": recruiter_name or "Hiring Team",
                "message": summary,
                "time": event_time,
                "badge": 1 if application.get("status", "").lower() in {"shortlisted", "interview"} else 0,
                "initials": "".join(part[:1].upper() for part in (recruiter_name or "Hiring Team").split()[:2]) or "HT",
                "active": False,
                "status": status_label,
                "job_title": job.get("title", "Role"),
                "chat_type": "application",
                "reply_enabled": False,
                "reply_target_id": None,
            }
        )

        threads[chat_id] = [
            {
                "sender": "them",
                "text": f"Role: {job.get('title', 'Role')}",
                "time": event_time,
            },
            {
                "sender": "them",
                "text": f"Application recorded on {application.get('created_at').strftime('%b %d, %Y')}.",
                "time": application.get("created_at"),
            },
            {
                "sender": "them",
                "text": f"Current status: {status_label}.",
                "time": event_time,
            },
            {
                "sender": "them",
                "text": f"Experience level: {job.get('experience_level', 'Not specified')}.",
                "time": event_time,
            },
        ]

    latest_resume = ResumeModel.latest_for_user(candidate_id)
    if latest_resume:
        resume_chat_id = f"resume-{latest_resume['_id']}"
        chats.append(
            {
                "id": resume_chat_id,
                "name": "HireMind System",
                "message": f"Resume analyzed: {latest_resume.get('filename', 'resume')}",
                "time": latest_resume.get("created_at"),
                "badge": 0,
                "initials": "HM",
                "active": False,
                "status": "Analysis complete",
                "job_title": "Resume update",
                "chat_type": "system",
                "reply_enabled": False,
                "reply_target_id": None,
            }
        )
        threads[resume_chat_id] = [
            {
                "sender": "them",
                "text": f"Resume stored as {latest_resume.get('filename', 'resume')}.",
                "time": latest_resume.get("created_at"),
            },
            {
                "sender": "them",
                "text": f"Final score: {latest_resume.get('scores', {}).get('final_score', 0)}.",
                "time": latest_resume.get("created_at"),
            },
            {
                "sender": "them",
                "text": f"Skills detected: {', '.join(latest_resume.get('parsed_data', {}).get('skills', [])[:6]) or 'None detected yet'}.",
                "time": latest_resume.get("created_at"),
            },
        ]

    chats.sort(key=lambda item: item["time"] or item.get("created_at"), reverse=True)
    filtered_chats = [chat for chat in chats if chat_matches_filters(chat, query, selected_tab)]
    filtered_threads = {chat["id"]: threads.get(chat["id"], []) for chat in filtered_chats}
    return filtered_chats, filtered_threads


def normalize_search_query(value: str) -> str:
    return " ".join((value or "").lower().split())


def job_matches_search(job: dict, company_name: str, query: str) -> bool:
    normalized_query = normalize_search_query(query)
    if not normalized_query:
        return True

    haystack_parts = [
        job.get("title", ""),
        job.get("description", ""),
        company_name,
        job.get("experience_level", ""),
        job.get("job_type", ""),
        job.get("location", ""),
        job.get("work_mode", ""),
        " ".join(job.get("skills", [])),
        " ".join(job.get("cognitive_traits", [])),
    ]

    parsed_data = job.get("parsed_data", {}) or {}
    haystack_parts.extend(
        [
            parsed_data.get("title", ""),
            parsed_data.get("description", ""),
            parsed_data.get("location", ""),
            " ".join(parsed_data.get("skills", [])),
            " ".join(parsed_data.get("cognitive_traits", [])),
        ]
    )

    searchable_text = normalize_search_query(" ".join(str(part or "") for part in haystack_parts))
    return all(term in searchable_text for term in normalized_query.split())


@candidate_bp.route("/dashboard")
@login_required
@role_required("candidate")
def dashboard():
    latest_resume = ResumeModel.latest_for_user(current_user.id)
    all_jobs = JobModel.all_jobs()
    all_applications = ApplicationModel.candidate_applications(current_user.id)

    parsed_profile = latest_resume.get("parsed_data", {}) if latest_resume else {}
    resume_scores = latest_resume.get("scores", {}) if latest_resume else {}
    resume_score = round(resume_scores.get("final_score", 0), 1) if latest_resume else None
    profile_strength = round(parsed_profile.get("profile_completeness", 0)) if latest_resume else 0
    name_parts = [part for part in current_user.name.split() if part]
    user_initials = "".join(part[:1].upper() for part in name_parts[:2]) or current_user.name[:1].upper()

    top_matches = []
    if latest_resume:
        for job in all_jobs:
            match = match_candidate_to_job(parsed_profile, job, resume_scores)
            top_matches.append({"job": job, "match": match})
        top_matches.sort(key=lambda item: item["match"]["cfma"]["fit_score"], reverse=True)
    top_matches = top_matches[:2]

    job_match_score = round(top_matches[0]["match"]["cfma"]["fit_score"]) if top_matches else 0
    top_match = top_matches[0] if top_matches else None
    insight_items = resume_improvement_engine(parsed_profile, resume_scores) if latest_resume else [
        "Upload your resume to unlock personalized AI insights.",
        "Add your strongest technical skills to improve role matching.",
        "Keep your profile updated to surface more relevant opportunities.",
    ]

    status_counts = {"submitted": 0, "shortlisted": 0, "interview": 0, "rejected": 0}
    for application in all_applications:
        status = application.get("status", "submitted").lower()
        if status in status_counts:
            status_counts[status] += 1

    interviews_count = status_counts["interview"] or status_counts["shortlisted"]
    success_rate = round((((status_counts["shortlisted"] + status_counts["interview"]) / max(len(all_applications), 1)) * 100), 0) if all_applications else 0

    skill_gap_rows = []
    if top_match:
        missing_skills = top_match["match"]["sga"]["missing_skills"][:3]
        for index, skill in enumerate(missing_skills, start=1):
            skill_gap_rows.append(
                {
                    "label": skill.replace("_", " ").title(),
                    "percent": max(25, 70 - (index * 12)),
                }
            )
    if not skill_gap_rows:
        skill_gap_rows = [
            {"label": "System Design", "percent": 60},
            {"label": "Backend Depth", "percent": 45},
            {"label": "Cloud Delivery", "percent": 50},
        ]

    recommended_items = top_match["match"]["lps"][:2] if top_match else [
        "Build practical portfolio projects tailored to your target role.",
        "Advance one core skill with a focused short course this week.",
    ]

    return render_template(
        "candidate/dashboard.html",
        latest_resume=latest_resume,
        resume_score=resume_score,
        profile_strength=profile_strength,
        job_match_score=job_match_score,
        top_matches=top_matches,
        insight_items=insight_items[:3],
        application_count=len(all_applications),
        status_counts=status_counts,
        user_initials=user_initials,
        interviews_count=interviews_count,
        success_rate=success_rate,
        skill_gap_rows=skill_gap_rows,
        recommended_items=recommended_items,
    )


@candidate_bp.route("/upload", methods=["GET", "POST"])
@login_required
@role_required("candidate")
def upload():
    form = ResumeUploadForm()
    if form.validate_on_submit():
        file = form.resume.data
        filename = secure_filename(file.filename or "")
        if not allowed_file(filename, current_app.config["ALLOWED_EXTENSIONS"]):
            flash("Only PDF and DOCX resumes are allowed.", "danger")
        else:
            suffix = os.path.splitext(filename)[1]
            with NamedTemporaryFile(delete=False, suffix=suffix, dir=current_app.config["UPLOAD_FOLDER"]) as temp_file:
                file.save(temp_file.name)
                content = read_resume_file(temp_file.name)
            with open(temp_file.name, "rb") as uploaded_file:
                original_file_bytes = uploaded_file.read()
            analysis = analyze_resume_with_ses(content)
            resume_id = ResumeModel.create_resume(
                current_user.id,
                filename,
                content,
                analysis["parsed_data"],
                analysis["scores"],
                analysis["algorithm_outputs"],
                original_file_bytes=original_file_bytes,
                content_type=file.mimetype,
            )
            AIResultModel.create(current_user.id, "resume", resume_id, "analysis", analysis)
            NotificationModel.create(current_user.id, "Resume analyzed", f"{filename} was analyzed successfully.", "resume")
            ActivityModel.log(current_user.id, "upload_resume", {"resume_id": resume_id, "filename": filename})
            os.unlink(temp_file.name)
            flash("Resume uploaded and analyzed successfully.", "success")
            return redirect(url_for("candidate.analysis", id=resume_id))
    return render_template("candidate/upload.html", form=form)


@candidate_bp.route("/resume-builder", methods=["GET", "POST"])
@login_required
@role_required("candidate")
def resume_builder():
    latest_resume = ResumeModel.latest_for_user(current_user.id)
    starter_profile = latest_resume.get("parsed_data", {}) if latest_resume else {}
    form = ResumeBuilderForm(
        name=current_user.name,
        email=current_user.email,
        summary=starter_profile.get("summary", ""),
        skills=", ".join(starter_profile.get("skills", [])),
        experience=starter_profile.get("experience", ""),
        education="\n".join(starter_profile.get("education", [])) if isinstance(starter_profile.get("education"), list) else starter_profile.get("education", ""),
    )

    if request.method == "POST":
        form = ResumeBuilderForm()

    if form.validate_on_submit():
        resume_data = normalize_builder_payload(form.data)
        content = build_resume_content(resume_data)
        analysis = analyze_resume_with_ses(content, parse_comma_list(form.skills.data))
        filename_root = secure_filename(resume_data["name"]) or "candidate"
        resume_id = ResumeModel.create_resume(
            current_user.id,
            f"{filename_root}-resume.txt",
            content,
            analysis["parsed_data"],
            analysis["scores"],
            analysis["algorithm_outputs"],
            sections=resume_data,
        )
        AIResultModel.create(current_user.id, "resume", resume_id, "builder_analysis", analysis)
        ActivityModel.log(current_user.id, "build_resume", {"resume_id": resume_id})
        flash("Resume profile saved successfully.", "success")
        return redirect(url_for("candidate.analysis", id=resume_id))

    resume_data = normalize_builder_payload(form.data)
    return render_template(
        "candidate/resume_builder.html",
        form=form,
        resume_data=resume_data,
        pdf_export_ready=pdfkit_configuration() is not None,
    )


@candidate_bp.route("/resume-builder/download", methods=["POST"])
@login_required
@role_required("candidate")
def resume_builder_download():
    resume_data = normalize_builder_payload(request.form)
    rendered = render_template("candidate/resume_builder_pdf.html", resume_data=resume_data, print_mode=False)
    config = pdfkit_configuration()

    if config is None:
        return render_template("candidate/resume_builder_pdf.html", resume_data=resume_data, print_mode=True)

    pdf = pdfkit.from_string(
        rendered,
        False,
        configuration=config,
        options={
            "encoding": "UTF-8",
            "enable-local-file-access": "",
            "margin-top": "12mm",
            "margin-right": "12mm",
            "margin-bottom": "12mm",
            "margin-left": "12mm",
        },
    )

    response = make_response(pdf)
    response.headers["Content-Type"] = "application/pdf"
    response.headers["Content-Disposition"] = "attachment; filename=hiremind-resume.pdf"
    return response


@candidate_bp.route("/analysis/<id>")
@login_required
@role_required("candidate")
def analysis(id):
    resume = ResumeModel.get_resume(id)
    if not resume or resume["user_id"] != current_user.id:
        flash("Resume not found.", "danger")
        return redirect(url_for("candidate.resumes"))
    algorithm_outputs = resume.get("algorithm_outputs") or analyze_resume_with_ses(resume.get("content", "")).get("algorithm_outputs", {})
    return render_template("candidate/analysis.html", resume=resume, algorithm_outputs=algorithm_outputs)


@candidate_bp.route("/resumes/<id>/delete", methods=["POST"])
@login_required
@role_required("candidate")
def delete_resume(id):
    resume = ResumeModel.get_resume(id)
    if not resume or resume["user_id"] != current_user.id:
        flash("Resume not found.", "danger")
        return redirect(url_for("candidate.resumes"))

    filename = resume.get("filename", "resume")
    if ResumeModel.delete_resume(id):
        NotificationModel.create(current_user.id, "Resume deleted", f"{filename} was removed from your resume library.", "resume")
        ActivityModel.log(current_user.id, "delete_resume", {"resume_id": id, "filename": filename})
        flash("Resume deleted successfully.", "success")
    else:
        flash("We couldn't delete that resume right now.", "danger")

    return redirect(url_for("candidate.resumes"))


@candidate_bp.route("/recommendations")
@login_required
@role_required("candidate")
def recommendations():
    latest_resume = ResumeModel.latest_for_user(current_user.id)
    jobs = JobModel.all_jobs()
    recommendations_data = []
    overall = None
    gaps = []
    if latest_resume:
        profile = latest_resume["parsed_data"]
        for job in jobs:
            match = match_candidate_to_job(profile, job, latest_resume.get("scores", {}))
            recommendations_data.append(
                {
                    "job": job,
                    "fit": match["cfma"],
                    "skill_score": round(match["wsms"]["skill_score"], 2),
                    "cognitive_score": round(match["cmm"]["cognitive_fit_score"], 2),
                    "experience_score": round(match["eas"]["experience_score"], 2),
                    "missing_skills": match["sga"]["missing_skills"][:4],
                    "learning_paths": match["lps"],
                    "holistic_score": match["hcs"]["holistic_score"],
                }
            )
        recommendations_data.sort(key=lambda item: item["holistic_score"], reverse=True)
        RecommendationModel.replace_for_user(
            current_user.id,
            [
                {
                    "job_id": str(item["job"]["_id"]),
                    "job_title": item["job"]["title"],
                    "fit": item["fit"],
                    "skill_score": item["skill_score"],
                    "cognitive_score": item["cognitive_score"],
                    "experience_score": item["experience_score"],
                    "missing_skills": item["missing_skills"],
                    "learning_paths": item["learning_paths"],
                    "holistic_score": item["holistic_score"],
                }
                for item in recommendations_data[:10]
            ],
            source_resume_id=str(latest_resume["_id"]),
        )
        ActivityModel.log(current_user.id, "generate_recommendations", {"resume_id": str(latest_resume["_id"])})

        top_item = recommendations_data[0] if recommendations_data else None
        if top_item:
            overall = {
                "fit": round(top_item["fit"]["fit_score"]),
                "skills": round(top_item["skill_score"]),
                "cognitive": round(top_item["cognitive_score"]),
                "experience": round(top_item["experience_score"]),
            }

        gap_scores: dict[str, int] = {}
        for item in recommendations_data:
            for index, skill in enumerate(item["missing_skills"]):
                weighted_gap = max(35, 88 - (index * 14) - int(item["skill_score"] * 0.15))
                gap_scores[skill] = max(gap_scores.get(skill, 0), weighted_gap)

        for skill, level in sorted(gap_scores.items(), key=lambda pair: pair[1], reverse=True)[:4]:
            gaps.append(
                {
                    "name": skill.replace("_", " ").title(),
                    "level": level,
                    "tag": "High" if level >= 70 else "Medium" if level >= 50 else "Low",
                }
            )

    return render_template(
        "candidate/recommendations.html",
        recommendations=recommendations_data[:6],
        latest_resume=latest_resume,
        overall=overall,
        gaps=gaps,
    )


@candidate_bp.route("/jobs")
@login_required
@role_required("candidate")
def jobs():
    latest_resume = ResumeModel.latest_for_user(current_user.id)
    profile = latest_resume["parsed_data"] if latest_resume else {}
    resume_scores = latest_resume.get("scores", {}) if latest_resume else {}
    search_query = sanitize_text(request.args.get("q", "") or "")
    jobs_data = []
    for job in JobModel.all_jobs():
        company_name = fetch_user_name(job.get("recruiter_id", ""))
        if not job_matches_search(job, company_name, search_query):
            continue

        if latest_resume:
            match = match_candidate_to_job(profile, job, latest_resume.get("scores", {}))
            breakdown = build_match_breakdown(match, resume_scores, profile)
            MatchScoreModel.upsert(
                current_user.id,
                str(job["_id"]),
                {
                    "fit_score": match["cfma"]["fit_score"],
                    "holistic_score": match["hcs"]["holistic_score"],
                    "breakdown": breakdown,
                    "explanation": match["ers"],
                },
            )
            jobs_data.append(
                {
                    "job": job,
                    "company": company_name,
                    "fit": match["cfma"],
                    "holistic_score": match["hcs"]["holistic_score"],
                    "breakdown": breakdown,
                }
            )
        else:
            jobs_data.append(
                {
                    "job": job,
                    "company": company_name,
                    "fit": {"fit_score": 0, "explanation": "Upload a resume to unlock personalized fit scoring."},
                    "holistic_score": 0,
                    "breakdown": {"skill": 0, "exp": 0, "project": 0, "cognitive": 0, "growth": 0, "context": 0},
                }
            )
    return render_template(
        "candidate/jobs.html",
        jobs_data=jobs_data,
        search_query=search_query,
        search_count=len(jobs_data),
    )


@candidate_bp.route("/job/<id>", methods=["GET", "POST"])
@login_required
@role_required("candidate")
def job_detail(id):
    job = JobModel.get_job(id)
    if not job:
        flash("Job not found.", "danger")
        return redirect(url_for("candidate.jobs"))
    latest_resume = ResumeModel.latest_for_user(current_user.id)
    match = match_candidate_to_job(latest_resume["parsed_data"], job, latest_resume.get("scores", {})) if latest_resume else None
    if request.method == "POST":
        if ApplicationModel.apply(current_user.id, id):
            MessageModel.create(job["recruiter_id"], current_user.id, f"Application received for {job['title']}.")
            NotificationModel.create(current_user.id, "Application submitted", f"You applied for {job['title']}.", "application")
            NotificationModel.create(job["recruiter_id"], "New application", f"{current_user.name} applied for {job['title']}.", "application")
            ActivityModel.log(current_user.id, "apply_job", {"job_id": id, "job_title": job["title"]})
            flash("Application submitted.", "success")
        else:
            flash("You already applied to this role.", "warning")
        return redirect(url_for("candidate.applications"))
    return render_template("candidate/job_detail.html", job=job, fit=match["cfma"] if match else None, match=match, recruiter_name=fetch_user_name(job["recruiter_id"]))


@candidate_bp.route("/applications")
@login_required
@role_required("candidate")
def applications():
    rows = []
    for application in ApplicationModel.candidate_applications(current_user.id):
        job = JobModel.get_job(application["job_id"])
        if job:
            recruiter_name = fetch_user_name(job.get("recruiter_id", ""))
            rows.append(
                {
                    "application": application,
                    "job": job,
                    "company": recruiter_name,
                    "location": job.get("parsed_data", {}).get("location") or job.get("experience_level") or "Location not specified",
                    "updated_at": application.get("updated_at") or application.get("created_at"),
                }
            )
    return render_template("candidate/applications.html", rows=rows)


@candidate_bp.route("/messages")
@login_required
@role_required("candidate")
def messages():
    search_query = sanitize_text(request.args.get("q", "") or "")
    selected_tab = sanitize_text(request.args.get("tab", "all") or "all").lower()
    if selected_tab not in {"all", "recruiters", "system"}:
        selected_tab = "all"

    chats, threads = build_message_threads(current_user.id, search_query, selected_tab)
    active_chat_id = sanitize_text(request.args.get("chat", "") or "")
    active_chat = next((chat for chat in chats if chat["id"] == active_chat_id), None)
    if not active_chat:
        active_chat = chats[0] if chats else None

    notifications = NotificationModel.for_user(current_user.id, unread_only=True)
    reply_form = MessageReplyForm()
    if active_chat and active_chat.get("reply_enabled"):
        reply_form.receiver_id.data = active_chat.get("reply_target_id", "")
        reply_form.chat_id.data = active_chat.get("id", "")

    return render_template(
        "candidate/messages.html",
        chats=chats,
        thread=threads.get(active_chat["id"], []) if active_chat else [],
        active_chat=active_chat,
        notifications=notifications,
        reply_form=reply_form,
        selected_tab=selected_tab,
        search_query=search_query,
    )


@candidate_bp.route("/messages/send", methods=["POST"])
@login_required
@role_required("candidate")
def send_message():
    form = MessageReplyForm()
    fallback_chat_id = sanitize_text(request.form.get("chat_id", "") or "")
    if not form.validate_on_submit():
        flash("Enter a message before sending.", "danger")
        return redirect(url_for("candidate.messages", chat=fallback_chat_id))

    receiver_id = form.receiver_id.data
    receiver = UserModel.get_by_id(receiver_id)
    if not receiver or receiver.role != "recruiter":
        flash("That conversation is not available for replies.", "danger")
        return redirect(url_for("candidate.messages", chat=fallback_chat_id))

    message_text = sanitize_text(form.message.data or "")
    if not message_text:
        flash("Enter a message before sending.", "danger")
        return redirect(url_for("candidate.messages", chat=fallback_chat_id))

    conversation_id = MessageModel.build_conversation_id(current_user.id, receiver_id)
    MessageModel.create(current_user.id, receiver_id, message_text)
    NotificationModel.create(receiver_id, "New candidate message", f"{current_user.name} sent you a new message.", "message")
    ActivityModel.log(current_user.id, "send_message", {"receiver_id": receiver_id, "conversation_id": conversation_id})
    flash("Message sent.", "success")
    return redirect(url_for("candidate.messages", chat=conversation_id))


@candidate_bp.route("/resumes")
@login_required
@role_required("candidate")
def resumes():
    resumes = ResumeModel.for_user(current_user.id)
    latest_resume_id = str(resumes[0]["_id"]) if resumes else None
    return render_template("candidate/resumes.html", resumes=resumes, latest_resume_id=latest_resume_id)


@candidate_bp.route("/settings", methods=["GET", "POST"])
@login_required
@role_required("candidate")
def settings():
    user_doc = UserModel.get_raw_by_id(current_user.id)
    profile = default_candidate_profile(user_doc)
    form = SettingsForm(data=profile)
    if form.validate_on_submit():
        image_path = save_profile_image(form.image.data)
        if form.image.data and form.image.data.filename:
            if image_path == "__storage_unavailable__":
                flash("Profile photo uploads are not persisted on this deployment yet.", "warning")
                image_path = None
            elif not image_path:
                flash("Profile photo must be PNG, JPG, JPEG, or WEBP.", "danger")
                return render_template("candidate/settings.html", form=form, profile=profile, latest_resume=ResumeModel.latest_for_user(current_user.id))

        user_payload = {
            "name": sanitize_text(form.name.data),
            "email": sanitize_text(form.email.data).lower(),
            "phone": sanitize_text(form.phone.data or ""),
            "location": sanitize_text(form.location.data or ""),
            "linkedin": sanitize_text(form.linkedin.data or ""),
            "headline": sanitize_text(form.role.data or ""),
            "preferred_role": sanitize_text(form.preferred_role.data or ""),
            "experience_level": sanitize_text(form.experience.data or ""),
            "skills": [item.strip() for item in (form.skills.data or "").split(",") if item.strip()],
            "salary_expectation": sanitize_text(form.salary.data or ""),
            "availability": sanitize_text(form.availability.data or ""),
        }
        if image_path:
            user_payload["profile_image"] = image_path

        settings_payload = {
            "theme": sanitize_text(form.theme.data or ""),
            "language": sanitize_text(form.language.data or ""),
            "timezone": sanitize_text(form.timezone.data or ""),
            "notifications": {
                "job_alerts": bool(form.job_alerts.data),
                "application_updates": bool(form.application_updates.data),
                "interview_reminders": bool(form.interview_reminders.data),
                "email_notifications": bool(form.email_notifications.data),
            },
        }

        UserModel.update_profile(current_user.id, user_payload)
        UserSettingsModel.upsert_for_user(current_user.id, settings_payload)
        ActivityModel.log(current_user.id, "update_settings", {})
        flash("Candidate settings updated successfully.", "success")
        return redirect(url_for("candidate.settings"))
    latest_resume = ResumeModel.latest_for_user(current_user.id)
    return render_template("candidate/settings.html", form=form, profile=profile, latest_resume=latest_resume)
