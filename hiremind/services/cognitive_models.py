from services.data_models import feature_engineering_model


def behavioral_pattern_model(resume_text: str) -> dict:
    lowered = resume_text.lower()
    patterns = {
        "initiative": any(token in lowered for token in ["initiated", "launched", "built", "started"]),
        "ownership": any(token in lowered for token in ["owned", "drove", "delivered", "led"]),
        "collaboration": any(token in lowered for token in ["team", "collaborated", "partnered"]),
        "resilience": any(token in lowered for token in ["improved", "resolved", "optimized", "recovered"]),
    }
    score = round((sum(1 for value in patterns.values() if value) / len(patterns)) * 100, 2)
    return {"behavior_indicators": patterns, "behavior_score": score}


def cognitive_matching_model(candidate_profile: dict, job_profile: dict) -> dict:
    candidate_features = feature_engineering_model(candidate_profile)
    job_features = feature_engineering_model(job_profile)
    candidate_traits = set(candidate_features.get("traits_vector", {}).keys())
    job_traits = set(job_features.get("traits_vector", {}).keys())
    shared_traits = sorted(candidate_traits & job_traits)
    score = round((len(shared_traits) / max(len(job_traits), 1)) * 100, 2)
    return {
        "shared_traits": shared_traits,
        "cognitive_fit_score": score,
    }
