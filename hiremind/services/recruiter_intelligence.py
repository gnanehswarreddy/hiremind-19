from services.job_models import job_representation_model


def job_profile_representation(job: dict) -> dict:
    return job_representation_model(job)


def candidate_fit_ranker(candidates: list[dict]) -> list[dict]:
    return sorted(candidates, key=lambda item: item.get("fit_score", 0), reverse=True)


def explainable_ranking_system(candidate_name: str, fit_data: dict, job_profile: dict) -> str:
    top_skills = ", ".join(job_profile.get("skills", [])[:3]) or "core requirements"
    return (
        f"{candidate_name} scored {fit_data.get('fit_score', 0)} based on weighted skill overlap, "
        f"trait alignment, and experience fit against {top_skills}. "
        f"{fit_data.get('explanation', '')}"
    )
