from services.cognitive_models import behavioral_pattern_model
from services.data_models import data_normalization_model, feature_engineering_model
from services.parser import resume_semantic_extractor


def candidate_profiling_system(resume_text: str) -> dict:
    extracted = resume_semantic_extractor(resume_text)
    return {
        "skills": extracted.get("skills", []),
        "experience": extracted.get("experience", "0-1 years"),
        "education": extracted.get("education", []),
        "summary": extracted.get("summary", ""),
        "sections": extracted.get("sections", {}),
        "cognitive_traits": extracted.get("cognitive_traits", []),
    }


def cognitive_inference_system(resume_text: str, extracted_data: dict | None = None) -> dict:
    extracted_data = extracted_data or resume_semantic_extractor(resume_text)
    if "cognitive_traits" not in extracted_data:
        extracted_data = {**extracted_data, **resume_semantic_extractor(resume_text)}
    traits = extracted_data.get("cognitive_traits", [])
    indicators = {
        "communication": "communication" in resume_text.lower() or "presentation" in resume_text.lower(),
        "leadership": "leadership" in resume_text.lower() or "led" in resume_text.lower(),
        "problem_solving": "problem solving" in resume_text.lower() or "solved" in resume_text.lower(),
        "collaboration": "team" in resume_text.lower() or "collaborate" in resume_text.lower(),
    }
    strength = round((sum(1 for value in indicators.values() if value) / max(len(indicators), 1)) * 100, 2)
    return {
        "cognitive_traits": traits,
        "soft_skills": [key for key, value in indicators.items() if value],
        "inference_score": strength,
    }


def data_structuring_system(profile_data: dict, cognitive_data: dict) -> dict:
    structured = {
        "skills": sorted(set(profile_data.get("skills", []))),
        "experience": profile_data.get("experience", "0-1 years"),
        "education": sorted(set(profile_data.get("education", []))),
        "summary": profile_data.get("summary", ""),
        "sections": profile_data.get("sections", {}),
        "cognitive_traits": sorted(set(cognitive_data.get("cognitive_traits", []))),
        "soft_skills": sorted(set(cognitive_data.get("soft_skills", []))),
        "profile_completeness": round(
            (
                int(bool(profile_data.get("skills")))
                + int(bool(profile_data.get("summary")))
                + int(bool(profile_data.get("education")))
                + int(bool(cognitive_data.get("soft_skills")))
            )
            / 4
            * 100,
            2,
        ),
    }
    return data_normalization_model(structured)


def build_candidate_profile(resume_text: str) -> dict:
    profile = candidate_profiling_system(resume_text)
    cognition = cognitive_inference_system(resume_text, profile)
    structured = data_structuring_system(profile, cognition)
    return {
        **structured,
        "behavioral_profile": behavioral_pattern_model(resume_text),
        "feature_vector": feature_engineering_model(structured),
    }
