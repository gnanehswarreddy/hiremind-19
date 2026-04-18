from app import create_app
from services.job_models import job_parsing_model, job_representation_model
from models.job_model import JobModel
from models.resume_model import ResumeModel
from models.user_model import UserModel
from services.r3_engine import calculate_r3_scores
from utils.security import hash_password


def seed():
    app = create_app()
    with app.app_context():
        UserModel.create_indexes()
        if not UserModel.get_raw_by_email("candidate@hiremind.dev"):
            candidate_id = UserModel.create_user("Asha Candidate", "candidate@hiremind.dev", hash_password("Password123"), "candidate")
            parsed = {
                "skills": ["python", "flask", "mongodb", "communication"],
                "experience": "2-4 years",
                "cognitive_traits": ["analytical", "adaptive"],
                "summary": "Full-stack engineer with strong API and data handling experience.",
            }
            content = "Python Flask MongoDB communication 3 years building APIs and data workflows."
            ResumeModel.create_resume(candidate_id, "sample_resume.docx", content, parsed, calculate_r3_scores(content, parsed))

        if not UserModel.get_raw_by_email("recruiter@hiremind.dev"):
            recruiter_id = UserModel.create_user("Nexa Talent", "recruiter@hiremind.dev", hash_password("Password123"), "recruiter")
            parsed_job = job_parsing_model(
                title="AI Product Engineer",
                job_description="Build candidate-facing workflows, analytics, and scalable backend services.",
                seed_skills=["python", "flask", "mongodb", "communication"],
                seed_traits=["analytical", "ownership"],
                experience_level="2-4 years",
            )
            JobModel.create_job(
                recruiter_id=recruiter_id,
                title=parsed_job["title"],
                description=parsed_job["description"],
                skills=parsed_job["skills"],
                cognitive_traits=parsed_job["cognitive_traits"],
                experience_level=parsed_job["experience_level"],
                parsed_data=parsed_job,
                representation=job_representation_model(parsed_job),
            )


if __name__ == "__main__":
    seed()
