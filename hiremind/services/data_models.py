import re


def data_normalization_model(payload: dict) -> dict:
    normalized = {}
    for key, value in payload.items():
        if isinstance(value, str):
            normalized[key] = re.sub(r"\s+", " ", value).strip()
        elif isinstance(value, list):
            cleaned = [re.sub(r"\s+", " ", str(item)).strip().lower() for item in value if str(item).strip()]
            normalized[key] = sorted(set(cleaned))
        elif isinstance(value, dict):
            normalized[key] = data_normalization_model(value)
        else:
            normalized[key] = value
    return normalized


def feature_engineering_model(candidate_or_job_data: dict) -> dict:
    skills = candidate_or_job_data.get("skills", [])
    traits = candidate_or_job_data.get("cognitive_traits", [])
    sections = candidate_or_job_data.get("sections", {})
    return {
        "skill_count": len(skills),
        "trait_count": len(traits),
        "has_education": int(bool(candidate_or_job_data.get("education"))),
        "has_summary": int(bool(candidate_or_job_data.get("summary"))),
        "section_count": sum(1 for value in sections.values() if value) if isinstance(sections, dict) else 0,
        "skills_vector": {skill: 1 for skill in skills},
        "traits_vector": {trait: 1 for trait in traits},
    }
