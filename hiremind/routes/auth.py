import json
import os
import secrets
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user
from flask_wtf import FlaskForm
from pymongo.errors import DuplicateKeyError
from wtforms import BooleanField, EmailField, PasswordField, SelectField, StringField, SubmitField
from wtforms.validators import DataRequired, EqualTo, Length

from models.activity_model import ActivityModel
from models.auth_session_model import AuthSessionModel
from models.job_model import ApplicationModel, JobModel
from models.notification_model import NotificationModel
from models.resume_model import ResumeModel
from models.settings_model import UserSettingsModel
from models.user_model import UserModel
from utils.security import hash_password, sanitize_text, valid_email, valid_password, verify_password

auth_bp = Blueprint("auth", __name__)
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
LINKEDIN_AUTH_URL = "https://www.linkedin.com/oauth/v2/authorization"
LINKEDIN_TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
LINKEDIN_USERINFO_URL = "https://api.linkedin.com/v2/userinfo"


class LoginForm(FlaskForm):
    email = EmailField("Email", validators=[DataRequired(), Length(max=120)])
    password = PasswordField("Password", validators=[DataRequired()])
    remember = BooleanField("Remember me")
    submit = SubmitField("Login")


class SignupForm(FlaskForm):
    name = StringField("Full name", validators=[DataRequired(), Length(min=2, max=80)])
    email = EmailField("Email", validators=[DataRequired(), Length(max=120)])
    password = PasswordField("Password", validators=[DataRequired(), Length(min=8, max=128)])
    confirm_password = PasswordField(
        "Confirm password",
        validators=[DataRequired(), EqualTo("password", message="Passwords must match.")],
    )
    role = SelectField("Role", choices=[("candidate", "Candidate"), ("recruiter", "Recruiter")], validators=[DataRequired()])
    submit = SubmitField("Create account")


class CompleteSocialSignupForm(FlaskForm):
    role = SelectField("Role", choices=[("candidate", "Candidate"), ("recruiter", "Recruiter")], validators=[DataRequired()])
    submit = SubmitField("Complete signup")


class ForgotPasswordForm(FlaskForm):
    email = EmailField("Email", validators=[DataRequired(), Length(max=120)])
    password = PasswordField("New password", validators=[DataRequired(), Length(min=8, max=128)])
    confirm_password = PasswordField(
        "Confirm new password",
        validators=[DataRequired(), EqualTo("password", message="Passwords must match.")],
    )
    submit = SubmitField("Reset password")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return _redirect_by_role(current_user.role)

    form = LoginForm()
    if form.validate_on_submit():
        email = sanitize_text(form.email.data)
        password = form.password.data
        user = UserModel.get_raw_by_email(email)
        if not user or not verify_password(password, user["password"]):
            flash("Invalid email or password.", "danger")
        else:
            login_user(UserModel.get_by_id(str(user["_id"])), remember=form.remember.data)
            auth_session_id = AuthSessionModel.create_session(str(user["_id"]))
            session["auth_session_id"] = auth_session_id
            ActivityModel.log(str(user["_id"]), "login", {"role": user["role"]})
            flash("Welcome back.", "success")
            return _redirect_by_role(user["role"])
    return render_template("login.html", form=form)


@auth_bp.route("/signup", methods=["GET", "POST"])
def signup():
    if current_user.is_authenticated:
        return _redirect_by_role(current_user.role)

    form = SignupForm()
    if form.validate_on_submit():
        name = sanitize_text(form.name.data)
        email = sanitize_text(form.email.data).lower()
        password = form.password.data
        role = form.role.data

        if not valid_email(email):
            flash("Enter a valid email address.", "danger")
        elif not valid_password(password):
            flash("Password must be at least 8 characters and include letters and numbers.", "danger")
        else:
            try:
                user_id = UserModel.create_user(name, email, hash_password(password), role)
                UserSettingsModel.upsert_for_user(
                    user_id,
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
                NotificationModel.create(user_id, "Welcome to HireMind", "Your account is ready and connected to MongoDB.", "system")
                ActivityModel.log(user_id, "signup", {"role": role})
                login_user(UserModel.get_by_id(user_id))
                session["auth_session_id"] = AuthSessionModel.create_session(user_id)
                flash("Your account is ready.", "success")
                return _redirect_by_role(role)
            except DuplicateKeyError:
                flash("An account with that email already exists.", "danger")
    return render_template("signup.html", form=form)


@auth_bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if current_user.is_authenticated:
        return _redirect_by_role(current_user.role)

    form = ForgotPasswordForm()
    if form.validate_on_submit():
        email = sanitize_text(form.email.data).lower()
        password = form.password.data
        user = UserModel.get_raw_by_email(email)

        if not valid_email(email):
            flash("Enter a valid email address.", "danger")
        elif not user:
            flash("No account was found for that email.", "danger")
        elif not valid_password(password):
            flash("Password must be at least 8 characters and include letters and numbers.", "danger")
        else:
            UserModel.update_password_by_email(email, hash_password(password))
            ActivityModel.log(str(user["_id"]), "password_reset", {})
            flash("Password updated successfully. You can log in now.", "success")
            return redirect(url_for("auth.login"))

    return render_template("forgot_password.html", form=form)


@auth_bp.route("/auth/google/start")
def google_start():
    if current_user.is_authenticated:
        return _redirect_by_role(current_user.role)
    if not current_app.config["GOOGLE_CLIENT_ID"] or not current_app.config["GOOGLE_CLIENT_SECRET"]:
        flash("Google login is not configured yet. Add Google OAuth environment variables first.", "warning")
        return redirect(url_for("auth.login"))

    session["oauth_origin"] = sanitize_text(request.args.get("origin", "login") or "login")

    state = secrets.token_urlsafe(24)
    session["google_oauth_state"] = state
    query = urlencode(
        {
            "client_id": current_app.config["GOOGLE_CLIENT_ID"],
            "redirect_uri": current_app.config["GOOGLE_REDIRECT_URI"],
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "access_type": "online",
            "prompt": "select_account",
        }
    )
    return redirect(f"{GOOGLE_AUTH_URL}?{query}")


@auth_bp.route("/auth/google/callback")
def google_callback():
    if request.args.get("state") != session.pop("google_oauth_state", None):
        flash("Google login could not be verified. Please try again.", "danger")
        return redirect(url_for("auth.login"))
    code = request.args.get("code")
    if not code:
        flash("Google login was cancelled or failed.", "danger")
        return redirect(url_for("auth.login"))

    try:
        token_data = _post_form(
            GOOGLE_TOKEN_URL,
            {
                "code": code,
                "client_id": current_app.config["GOOGLE_CLIENT_ID"],
                "client_secret": current_app.config["GOOGLE_CLIENT_SECRET"],
                "redirect_uri": current_app.config["GOOGLE_REDIRECT_URI"],
                "grant_type": "authorization_code",
            },
        )
        userinfo = _get_json(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {token_data['access_token']}"},
        )
        return _login_oauth_user(
            email=userinfo.get("email", ""),
            name=userinfo.get("name") or userinfo.get("given_name") or "Google User",
            provider="google",
        )
    except Exception:
        flash("Google login failed. Check your OAuth credentials and callback URL.", "danger")
        return redirect(url_for("auth.login"))


@auth_bp.route("/auth/complete-social-signup", methods=["GET", "POST"])
def complete_social_signup():
    if current_user.is_authenticated:
        return _redirect_by_role(current_user.role)

    pending_signup = session.get("pending_oauth_signup")
    if not pending_signup:
        flash("Your Google signup session expired. Please try again.", "warning")
        return redirect(url_for("auth.signup"))

    form = CompleteSocialSignupForm()
    if form.validate_on_submit():
        email = pending_signup.get("email", "")
        name = pending_signup.get("name", "HireMind User")
        provider = pending_signup.get("provider", "google")
        role = form.role.data

        existing_user = UserModel.get_raw_by_email(email)
        if existing_user:
            session.pop("pending_oauth_signup", None)
            login_user(UserModel.get_by_id(str(existing_user["_id"])))
            session["auth_session_id"] = AuthSessionModel.create_session(str(existing_user["_id"]), auth_provider=provider)
            flash("Account already exists. Signed you in instead.", "info")
            return _redirect_by_role(existing_user["role"])

        user_id = UserModel.create_social_user(
            name=name,
            email=email,
            password_hash=hash_password(secrets.token_urlsafe(24)),
            role=role,
            provider=provider,
        )
        UserSettingsModel.upsert_for_user(
            user_id,
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
        NotificationModel.create(user_id, "Welcome to HireMind", f"Your {provider.title()} account is ready.", "system")
        ActivityModel.log(user_id, "signup", {"role": role, "provider": provider})
        session.pop("pending_oauth_signup", None)
        login_user(UserModel.get_by_id(user_id))
        session["auth_session_id"] = AuthSessionModel.create_session(user_id, auth_provider=provider)
        flash(f"Signed up with {provider.title()}.", "success")
        return _redirect_by_role(role)

    return render_template(
        "complete_social_signup.html",
        form=form,
        pending_signup=pending_signup,
    )


@auth_bp.route("/auth/linkedin/start")
def linkedin_start():
    if current_user.is_authenticated:
        return _redirect_by_role(current_user.role)
    if not current_app.config["LINKEDIN_CLIENT_ID"] or not current_app.config["LINKEDIN_CLIENT_SECRET"]:
        flash("LinkedIn login is not configured yet. Add LinkedIn OAuth environment variables first.", "warning")
        return redirect(url_for("auth.login"))

    state = secrets.token_urlsafe(24)
    session["linkedin_oauth_state"] = state
    query = urlencode(
        {
            "response_type": "code",
            "client_id": current_app.config["LINKEDIN_CLIENT_ID"],
            "redirect_uri": current_app.config["LINKEDIN_REDIRECT_URI"],
            "state": state,
            "scope": "openid profile email",
        }
    )
    return redirect(f"{LINKEDIN_AUTH_URL}?{query}")


@auth_bp.route("/auth/linkedin/callback")
def linkedin_callback():
    if request.args.get("state") != session.pop("linkedin_oauth_state", None):
        flash("LinkedIn login could not be verified. Please try again.", "danger")
        return redirect(url_for("auth.login"))
    code = request.args.get("code")
    if not code:
        flash("LinkedIn login was cancelled or failed.", "danger")
        return redirect(url_for("auth.login"))

    try:
        token_data = _post_form(
            LINKEDIN_TOKEN_URL,
            {
                "code": code,
                "client_id": current_app.config["LINKEDIN_CLIENT_ID"],
                "client_secret": current_app.config["LINKEDIN_CLIENT_SECRET"],
                "redirect_uri": current_app.config["LINKEDIN_REDIRECT_URI"],
                "grant_type": "authorization_code",
            },
        )
        userinfo = _get_json(
            LINKEDIN_USERINFO_URL,
            headers={"Authorization": f"Bearer {token_data['access_token']}"},
        )
        return _login_oauth_user(
            email=userinfo.get("email", ""),
            name=userinfo.get("name") or userinfo.get("given_name") or "LinkedIn User",
            provider="linkedin",
        )
    except Exception:
        flash("LinkedIn login failed. Check your OAuth credentials and callback URL.", "danger")
        return redirect(url_for("auth.login"))


@auth_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    auth_session_id = session.pop("auth_session_id", None)
    if auth_session_id:
        AuthSessionModel.close_session(auth_session_id)
    ActivityModel.log(current_user.id, "logout", {})
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("landing"))


@auth_bp.route("/delete-account", methods=["POST"])
@login_required
def delete_account():
    user_id = current_user.id
    user_role = current_user.role
    auth_session_id = session.pop("auth_session_id", None)
    if auth_session_id:
        AuthSessionModel.close_session(auth_session_id)

    _delete_user_account(user_id, user_role)
    logout_user()
    flash("Your account has been deleted.", "info")
    return redirect(url_for("landing"))


def _redirect_by_role(role: str):
    if role == "recruiter":
        return redirect(url_for("recruiter.dashboard"))
    return redirect(url_for("candidate.dashboard"))


def _post_form(url: str, payload: dict) -> dict:
    data = urlencode(payload).encode("utf-8")
    request_obj = Request(url, data=data, headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urlopen(request_obj, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


def _get_json(url: str, headers: dict | None = None) -> dict:
    request_obj = Request(url, headers=headers or {})
    with urlopen(request_obj, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


def _login_oauth_user(email: str, name: str, provider: str):
    email = sanitize_text(email).lower()
    name = sanitize_text(name) or "HireMind User"
    oauth_origin = session.pop("oauth_origin", "login")
    if not valid_email(email):
        flash(f"{provider.title()} did not return a valid email address.", "danger")
        return redirect(url_for("auth.login"))

    user = UserModel.get_raw_by_email(email)
    if not user and oauth_origin == "signup":
        session["pending_oauth_signup"] = {
            "email": email,
            "name": name,
            "provider": provider,
        }
        flash("Choose how you want to use HireMind to finish your signup.", "info")
        return redirect(url_for("auth.complete_social_signup"))
    if not user:
        flash("No account is linked to that Google login yet. Please sign up first.", "warning")
        return redirect(url_for("auth.signup"))

    login_user(UserModel.get_by_id(str(user["_id"])))
    session["auth_session_id"] = AuthSessionModel.create_session(str(user["_id"]), auth_provider=provider)
    ActivityModel.log(str(user["_id"]), "oauth_login", {"provider": provider})
    flash(f"Signed in with {provider.title()}.", "success")
    return _redirect_by_role(user["role"])


def _delete_user_account(user_id: str, role: str):
    user_doc = UserModel.get_raw_by_id(user_id) or {}
    profile_image = user_doc.get("profile_image")

    for resume in ResumeModel.for_user(user_id):
        ResumeModel.delete_resume(str(resume["_id"]))

    if role == "candidate":
        for application in ApplicationModel.candidate_applications(user_id):
            ApplicationModel.delete(str(application["_id"]))

    if role == "recruiter":
        recruiter_jobs = JobModel.jobs_for_recruiter(user_id)
        recruiter_job_ids = [str(job["_id"]) for job in recruiter_jobs]
        for application in ApplicationModel.recruiter_applications(user_id):
            ApplicationModel.delete(str(application["_id"]))
        for job in recruiter_jobs:
            JobModel.delete_job(str(job["_id"]))
        current_app.db["match_scores"].delete_many({"job_id": {"$in": recruiter_job_ids}})

    current_app.db["messages"].delete_many({"participants": user_id})
    current_app.db["notifications"].delete_many({"user_id": user_id})
    current_app.db["user_settings"].delete_many({"user_id": user_id})
    current_app.db["auth_sessions"].delete_many({"user_id": user_id})
    current_app.db["activity_logs"].delete_many({"user_id": user_id})
    current_app.db["ai_results"].delete_many({"user_id": user_id})
    current_app.db["recommendations"].delete_many({"user_id": user_id})
    current_app.db["match_scores"].delete_many({"user_id": user_id})

    if user_doc:
        current_app.db["users"].delete_one({"_id": user_doc["_id"]})

    if profile_image:
        image_path = os.path.join(current_app.static_folder, profile_image)
        if os.path.exists(image_path):
            try:
                os.remove(image_path)
            except OSError:
                pass
