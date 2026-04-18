from services.cfma import calculate_fit, cognitive_fit_matching_algorithm
from services.candidate_intelligence import candidate_profiling_system, cognitive_inference_system, data_structuring_system
from services.cognitive_models import behavioral_pattern_model, cognitive_matching_model
from services.data_models import data_normalization_model, feature_engineering_model
from services.improvement_engine import learning_path_system, resume_improvement_engine, skill_gap_analyzer
from services.job_models import job_parsing_model
from services.parser import resume_semantic_extractor
from services.r3_engine import calculate_r3_scores
from services.recruiter_intelligence import candidate_fit_ranker, explainable_ranking_system, job_profile_representation


def weighted_skill_matching_system(candidate_profile: dict, job_profile: dict) -> dict:
    candidate_skills = set(candidate_profile.get("skills", []))
    job_skills = set(job_profile.get("skills", []))
    matched = sorted(candidate_skills & job_skills)
    score = round((len(matched) / max(len(job_skills), 1)) * 100, 2)
    return {"matched_skills": matched, "skill_score": score}


def experience_alignment_score(candidate_profile: dict, job_profile: dict) -> dict:
    mapping = {"0-1 years": 1, "2-4 years": 3, "5+ years": 5}
    candidate_value = mapping.get(candidate_profile.get("experience", "0-1 years"), 1)
    job_value = mapping.get(job_profile.get("experience_level", "0-1 years"), 1)
    score = max(0, 100 - (abs(candidate_value - job_value) * 20))
    return {"experience_score": score}


def holistic_candidate_score(r3_scores: dict, fit_data: dict, profile_data: dict) -> dict:
    holistic = round(
        (r3_scores.get("final_score", 0) * 0.40)
        + (fit_data.get("fit_score", 0) * 0.45)
        + (profile_data.get("profile_completeness", 0) * 0.15),
        2,
    )
    return {"holistic_score": holistic}


def scoring_engine_system(resume_text: str, benchmark_skills: list[str] | None = None) -> dict:
    rpm_output = resume_semantic_extractor(resume_text)
    dnm_output = data_normalization_model(rpm_output)
    cps_profile = candidate_profiling_system(resume_text)
    cis_profile = cognitive_inference_system(resume_text, cps_profile)
    bpm_output = behavioral_pattern_model(resume_text)
    dss_profile = data_structuring_system(cps_profile, cis_profile)
    fem_output = feature_engineering_model(dss_profile)
    enriched_profile = {**dss_profile, "behavioral_profile": bpm_output, "feature_vector": fem_output}
    r3_scores = calculate_r3_scores(resume_text, enriched_profile, benchmark_skills)
    return {
        "rpm": rpm_output,
        "dnm": dnm_output,
        "cps": cps_profile,
        "cis": cis_profile,
        "bpm": bpm_output,
        "dss": enriched_profile,
        "fem": fem_output,
        "r3_scores": r3_scores,
    }


def analyze_resume_with_ses(resume_text: str, benchmark_skills: list[str] | None = None) -> dict:
    scored = scoring_engine_system(resume_text, benchmark_skills)
    suggestions = resume_improvement_engine(scored["dss"], scored["r3_scores"])
    return {
        "parsed_data": scored["dss"],
        "scores": scored["r3_scores"],
        "algorithm_outputs": {
            "RPM": scored["rpm"],
            "RSE": scored["rpm"],
            "DNM": scored["dnm"],
            "CPS": scored["cps"],
            "CIS": scored["cis"],
            "BPM": scored["bpm"],
            "DSS": scored["dss"],
            "FEM": scored["fem"],
            "RIE": suggestions,
        },
    }


def match_candidate_to_job(candidate_profile: dict, job: dict, resume_scores: dict | None = None) -> dict:
    jpm = job_parsing_model(
        job_description=job.get("description", ""),
        title=job.get("title", ""),
        seed_skills=job.get("skills", []),
        seed_traits=job.get("cognitive_traits", []),
        experience_level=job.get("experience_level", ""),
    )
    job_profile = job_profile_representation({**job, **jpm})
    wsms = weighted_skill_matching_system(candidate_profile, job_profile)
    eas = experience_alignment_score(candidate_profile, job_profile)
    cmm = cognitive_matching_model(candidate_profile, job_profile)
    cfma_baseline = calculate_fit(candidate_profile, job_profile)
    cfma = cognitive_fit_matching_algorithm(wsms["skill_score"], eas["experience_score"], cmm["cognitive_fit_score"])
    cfma["baseline_explanation"] = cfma_baseline["explanation"]
    hcs = holistic_candidate_score(resume_scores or {}, cfma, candidate_profile)
    ers = explainable_ranking_system(candidate_profile.get("summary", "Candidate"), cfma, job_profile)
    sga = skill_gap_analyzer(candidate_profile, job_profile)
    lps = learning_path_system(sga["missing_skills"])
    return {
        "jpm": jpm,
        "job_profile": job_profile,
        "wsms": wsms,
        "eas": eas,
        "cmm": cmm,
        "cfma": cfma,
        "hcs": hcs,
        "ers": ers,
        "sga": sga,
        "lps": lps,
    }


def rank_candidates_for_job(candidates: list[dict], job: dict) -> list[dict]:
    ranked_rows = []
    for candidate in candidates:
        match = match_candidate_to_job(
            candidate_profile=candidate.get("profile", {}),
            job=job,
            resume_scores=candidate.get("resume", {}).get("scores", {}),
        )
        ranked_rows.append(
            {
                **candidate,
                "fit_score": match["cfma"]["fit_score"],
                "holistic_score": match["hcs"]["holistic_score"],
                "explanation": match["ers"],
                "algorithm_breakdown": match,
            }
        )
    return candidate_fit_ranker(ranked_rows)
