def _experience_to_value(level: str) -> int:
    mapping = {"0-1 years": 1, "2-4 years": 3, "5+ years": 5}
    return mapping.get(level, 1)


def calculate_fit(candidate_profile: dict, job: dict) -> dict:
    candidate_skills = set(candidate_profile.get("skills", []))
    job_skills = set(job.get("skills", []))
    skill_overlap = len(candidate_skills & job_skills)
    skill_score = (skill_overlap / max(len(job_skills), 1)) * 100

    candidate_traits = set(candidate_profile.get("cognitive_traits", []))
    job_traits = set(job.get("cognitive_traits", []))
    trait_overlap = len(candidate_traits & job_traits)
    trait_score = (trait_overlap / max(len(job_traits), 1)) * 100

    experience_gap = abs(_experience_to_value(candidate_profile.get("experience", "")) - _experience_to_value(job.get("experience_level", "")))
    experience_score = max(0, 100 - (experience_gap * 20))

    fit_score = round((skill_score * 0.55) + (trait_score * 0.20) + (experience_score * 0.25), 2)
    explanation = (
        f"Matched {skill_overlap} of {max(len(job_skills), 1)} required skills, "
        f"aligned on {trait_overlap} cognitive traits, and showed {experience_score:.0f}% experience alignment."
    )
    return {"fit_score": fit_score, "explanation": explanation}


def cognitive_fit_matching_algorithm(skill_score: float, experience_score: float, cognitive_fit_score: float) -> dict:
    fit_score = round((skill_score * 0.55) + (cognitive_fit_score * 0.20) + (experience_score * 0.25), 2)
    explanation = (
        f"Final fit combines skill match at {skill_score:.0f}%, "
        f"cognitive alignment at {cognitive_fit_score:.0f}%, and experience alignment at {experience_score:.0f}%."
    )
    return {"fit_score": fit_score, "explanation": explanation}


def rank_candidates(candidates: list[dict], job: dict) -> list[dict]:
    ranked = []
    for candidate in candidates:
        fit = calculate_fit(candidate.get("profile", {}), job)
        ranked.append({**candidate, **fit})
    return sorted(ranked, key=lambda item: item["fit_score"], reverse=True)
