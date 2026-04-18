import re
from collections import Counter

from services.data_models import data_normalization_model, feature_engineering_model
from services.parser import KNOWN_SKILLS, extract_experience


KNOWN_JOB_TRAITS = {
    "analytical": ["analyze", "data", "insight", "problem"],
    "collaborative": ["team", "collaborate", "cross-functional", "partner"],
    "ownership": ["own", "ownership", "drive", "deliver"],
    "adaptive": ["adapt", "fast-paced", "iterate", "learn"],
    "leadership": ["lead", "mentor", "manage", "influence"],
}


def job_parsing_model(job_description: str, title: str = "", seed_skills: list[str] | None = None, seed_traits: list[str] | None = None, experience_level: str | None = None) -> dict:
    text = f"{title} {job_description}".lower()
    tokens = Counter(re.findall(r"[a-zA-Z\-]+", text))
    parsed_skills = sorted(set(seed_skills or []) | {skill for skill in KNOWN_SKILLS if skill in text})
    parsed_traits = sorted(
        set(seed_traits or [])
        | {
            trait
            for trait, keywords in KNOWN_JOB_TRAITS.items()
            if any(tokens.get(keyword, 0) or keyword in text for keyword in keywords)
        }
    )
    return data_normalization_model(
        {
            "title": title,
            "description": job_description,
            "skills": parsed_skills,
            "cognitive_traits": parsed_traits or ["adaptive"],
            "experience_level": experience_level or extract_experience(text),
        }
    )


def job_representation_model(parsed_job: dict) -> dict:
    normalized = data_normalization_model(parsed_job)
    features = feature_engineering_model(normalized)
    return {
        **normalized,
        "feature_vector": features,
        "priority_weights": {
            "skills": 0.55,
            "cognitive_traits": 0.20,
            "experience": 0.25,
        },
    }
