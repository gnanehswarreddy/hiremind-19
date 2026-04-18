COURSE_LIBRARY = {
    "python": "Build a Flask API and deploy it with Gunicorn.",
    "flask": "Create a multi-blueprint Flask app with authentication.",
    "mongodb": "Design document schemas and aggregation pipelines in MongoDB.",
    "communication": "Practice concise project case studies and stakeholder updates.",
    "leadership": "Lead a small project sprint and document outcomes.",
    "problem solving": "Solve debugging and system-design exercises weekly.",
}


def skill_gap_analyzer(candidate_profile: dict, job: dict) -> dict:
    candidate_skills = set(candidate_profile.get("skills", []))
    required_skills = set(job.get("skills", []))
    missing_skills = sorted(required_skills - candidate_skills)
    matched_skills = sorted(required_skills & candidate_skills)
    return {
        "missing_skills": missing_skills,
        "matched_skills": matched_skills,
        "gap_score": round((len(missing_skills) / max(len(required_skills), 1)) * 100, 2),
    }


def resume_improvement_engine(candidate_profile: dict, scores: dict) -> list[str]:
    suggestions = []
    if scores.get("relevance_score", 0) < 70:
        suggestions.append("Add more role-specific skills and quantified achievements near the top of the resume.")
    if scores.get("representation_score", 0) < 75:
        suggestions.append("Include clearly labeled sections for summary, skills, experience, and education.")
    if scores.get("readability_score", 0) < 75:
        suggestions.append("Shorten dense sentences and use concise bullet points with measurable results.")
    if not candidate_profile.get("education"):
        suggestions.append("Add education or certification details to strengthen profile completeness.")
    return suggestions or ["Your resume is in strong shape. Keep tailoring it to each role."]


def learning_path_system(missing_skills: list[str]) -> list[str]:
    return [COURSE_LIBRARY.get(skill, f"Build a portfolio project demonstrating {skill}.") for skill in missing_skills[:4]]
