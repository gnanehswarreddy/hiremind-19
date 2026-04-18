from __future__ import annotations

import json
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from services.system_core import match_candidate_to_job

GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
GEMINI_ENDPOINT = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"


def _safe_round(value: float | int | None, digits: int = 1) -> float:
    return round(float(value or 0), digits)


def _score_label(score: float) -> str:
    if score >= 82:
        return "high"
    if score >= 65:
        return "moderate"
    return "developing"


def _normalize_skill(skill: str) -> str:
    return skill.replace("_", " ").title()


def _gemini_api_key() -> str:
    return os.environ.get("GEMINI_API_KEY", "").strip()


def _llm_available() -> bool:
    return bool(_gemini_api_key())


def _extract_response_text(payload: dict) -> str:
    for candidate in payload.get("candidates", []):
        content = candidate.get("content", {}) or {}
        for part in content.get("parts", []):
            text = (part.get("text") or "").strip()
            if text:
                return text
    return ""


def _call_gemini(prompt: str, *, temperature: float = 0.35, max_tokens: int = 700) -> str:
    api_key = _gemini_api_key()
    if not api_key:
        return ""

    request_payload = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": prompt}],
            }
        ],
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": max_tokens,
        },
    }

    request = Request(
        GEMINI_ENDPOINT,
        data=json.dumps(request_payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": api_key,
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=18) as response:
            payload = json.loads(response.read().decode("utf-8", errors="ignore"))
            return _extract_response_text(payload)
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError):
        return ""


def _extract_json_block(text: str) -> dict | None:
    cleaned = (text or "").strip()
    if not cleaned:
        return None

    candidates = [cleaned]
    if "```json" in cleaned:
        candidates.append(cleaned.split("```json", 1)[1].split("```", 1)[0].strip())
    if "```" in cleaned:
        fenced_parts = cleaned.split("```")
        for part in fenced_parts:
            part = part.strip()
            if part.startswith("{") and part.endswith("}"):
                candidates.append(part)

    first_brace = cleaned.find("{")
    last_brace = cleaned.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        candidates.append(cleaned[first_brace:last_brace + 1])

    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            continue
    return None


def _top_strengths(result: dict) -> list[str]:
    strengths = []
    scores = {
        "alignment": result.get("alignment", 0),
        "depth": result.get("depth", 0),
        "adaptability": result.get("adaptability", 0),
    }
    for key, value in sorted(scores.items(), key=lambda item: item[1], reverse=True):
        if value >= 65:
            strengths.append(key.title())
    meta_resume = (result.get("meta", {}) or {}).get("resume", {}) or result.get("resume_snapshot", {}) or (result.get("results", {}) or {}).get("meta", {}).get("resume", {})
    if meta_resume.get("skills"):
        strengths.append("Technical breadth")
    return strengths[:3] or ["Growth potential"]


def _top_weaknesses(result: dict) -> list[str]:
    weaknesses = []
    scores = {
        "alignment": result.get("alignment", 0),
        "depth": result.get("depth", 0),
        "adaptability": result.get("adaptability", 0),
    }
    for key, value in sorted(scores.items(), key=lambda item: item[1]):
        if value < 70:
            weaknesses.append(key.title())
    weaknesses.extend(_normalize_skill(skill) for skill in result.get("skill_gaps", [])[:2])
    return weaknesses[:4] or ["None significant"]


def _fallback_explanation(data: dict) -> dict:
    meta = data.get("meta", {}) or (data.get("results", {}) or {}).get("meta", {}) or {}
    job_snapshot = data.get("job_snapshot", {}) or meta.get("job", {})
    a3_score = _safe_round(data.get("a3_score", 0))
    hiring_probability = _safe_round(data.get("hiring_probability", 0))
    strengths = _top_strengths(data)
    weaknesses = _top_weaknesses(data)
    role_type = job_snapshot.get("role_type", "target role").replace("_", " ")
    top_gap = data.get("skill_gaps", [None])[0]

    summary = (
        f"This profile shows a {_score_label(a3_score)} fit for the {role_type} role with an A3 score of {a3_score}% "
        f"and an estimated hiring probability of {hiring_probability}%."
    )
    if top_gap:
        summary += f" The biggest gap is {top_gap.replace('_', ' ')}."

    detailed = (
        f"Alignment is {int(round(data.get('alignment', 0)))}%, depth is {int(round(data.get('depth', 0)))}%, "
        f"and adaptability is {int(round(data.get('adaptability', 0)))}%."
    )

    recruiter_brief = f"Best signals: {', '.join(strengths)}. Watchouts: {', '.join(weaknesses[:3])}."

    return {
        "summary": summary,
        "detailed": detailed,
        "strengths": strengths,
        "weaknesses": weaknesses,
        "recruiter_brief": recruiter_brief,
    }


def explain_score(data: dict) -> dict:
    fallback = _fallback_explanation(data)
    if not _llm_available():
        return fallback

    meta = data.get("meta", {}) or (data.get("results", {}) or {}).get("meta", {}) or {}
    job = data.get("job_snapshot", {}) or meta.get("job", {})
    prompt = (
        "You are HireMind AI. Explain this A3 resume comparison result in a practical, encouraging way. "
        "Return only valid JSON with keys: summary, detailed, strengths, weaknesses, recruiter_brief. "
        "Keep summary under 45 words, detailed under 70 words, strengths as 2-4 short strings, weaknesses as 2-4 short strings.\n\n"
        f"Role type: {job.get('role_type', 'target role')}\n"
        f"Experience level: {job.get('experience_level', 'not specified')}\n"
        f"A3 score: {data.get('a3_score', 0)}\n"
        f"Alignment: {data.get('alignment', 0)}\n"
        f"Depth: {data.get('depth', 0)}\n"
        f"Adaptability: {data.get('adaptability', 0)}\n"
        f"Hiring probability: {data.get('hiring_probability', 0)}\n"
        f"Skill gaps: {', '.join(data.get('skill_gaps', [])[:5]) or 'None'}\n"
        f"Suggestions: {'; '.join(data.get('suggestions', [])[:4]) or 'None'}"
    )
    response_text = _call_gemini(prompt, temperature=0.3, max_tokens=450)
    payload = _extract_json_block(response_text)
    if not payload:
        return fallback

    return {
        "summary": payload.get("summary") or fallback["summary"],
        "detailed": payload.get("detailed") or fallback["detailed"],
        "strengths": payload.get("strengths") or fallback["strengths"],
        "weaknesses": payload.get("weaknesses") or fallback["weaknesses"],
        "recruiter_brief": payload.get("recruiter_brief") or fallback["recruiter_brief"],
    }


def _fallback_resume_improvement(resume: dict, job: dict, comparison: dict | None = None) -> dict:
    comparison = comparison or {}
    resume_skills = resume.get("skills", []) or resume.get("parsed_data", {}).get("skills", [])
    job_skills = job.get("skills", [])
    missing = [skill for skill in job_skills if skill not in resume_skills][:4]
    projects = resume.get("projects", []) or []
    projects_text = "; ".join(projects[:2]) if projects else "Built user-facing and backend projects with measurable outcomes."

    optimized_summary = (
        f"Results-focused candidate with experience across {', '.join(resume_skills[:4]) or 'core software engineering'} "
        f"and a growing fit for {job.get('role_type', 'the target role')}. "
        f"Known for shipping production-ready work, collaborating across teams, and improving systems with measurable impact."
    )

    bullet_bank = [
        "Built and optimized production features with clear ownership, measurable delivery, and cross-functional collaboration.",
        "Designed scalable workflows and APIs, improving performance, maintainability, and delivery speed.",
        "Translated product requirements into practical implementations with strong debugging, iteration, and communication habits.",
    ]
    if missing:
        bullet_bank.append(f"Add a targeted project that demonstrates {', '.join(skill.title() for skill in missing[:2])} in a role-relevant context.")

    rewrite_notes = [
        "Move the most role-relevant skills into the top summary and skills block.",
        "Convert generic bullets into impact statements with metrics or business outcomes.",
        "Name tools, deployment environments, and architecture decisions explicitly.",
    ]

    return {
        "optimized_summary": optimized_summary,
        "bullet_bank": bullet_bank[:4],
        "rewrite_notes": rewrite_notes,
        "priority_skills": missing,
        "project_idea": (
            f"Build a portfolio project for {job.get('role_type', 'this role')} using {', '.join(missing[:2]).title()}"
            if missing
            else f"Expand {projects_text[:120]} into a stronger case-study style project section."
        ),
        "comparison_delta_hint": comparison.get("simulation", {}).get("headline"),
    }


def improve_resume(resume: dict, job: dict, comparison: dict | None = None) -> dict:
    fallback = _fallback_resume_improvement(resume, job, comparison)
    if not _llm_available():
        return fallback

    prompt = (
        "You are HireMind AI. Improve this resume for the target role. "
        "Return only valid JSON with keys: optimized_summary, bullet_bank, rewrite_notes, priority_skills, project_idea.\n\n"
        f"Target role: {job.get('role_type', 'target role')}\n"
        f"Job skills: {', '.join(job.get('skills', [])[:8]) or 'None'}\n"
        f"Resume skills: {', '.join(resume.get('skills', [])[:8]) or 'None'}\n"
        f"Resume projects: {'; '.join(resume.get('projects', [])[:3]) or 'None'}\n"
        f"Current suggestions: {'; '.join((comparison or {}).get('suggestions', [])[:4]) or 'None'}\n"
        "Requirements: optimized_summary under 70 words, bullet_bank as 3-4 strong bullet lines, "
        "rewrite_notes as 3 short actions, priority_skills as up to 4 strings, and project_idea as one concise sentence."
    )
    response_text = _call_gemini(prompt, temperature=0.4, max_tokens=550)
    payload = _extract_json_block(response_text)
    if not payload:
        return fallback

    return {
        "optimized_summary": payload.get("optimized_summary") or fallback["optimized_summary"],
        "bullet_bank": payload.get("bullet_bank") or fallback["bullet_bank"],
        "rewrite_notes": payload.get("rewrite_notes") or fallback["rewrite_notes"],
        "priority_skills": payload.get("priority_skills") or fallback["priority_skills"],
        "project_idea": payload.get("project_idea") or fallback["project_idea"],
        "comparison_delta_hint": fallback["comparison_delta_hint"],
    }


def _fallback_chat(query: str, context: dict | None = None) -> dict:
    context = context or {}
    lowered = (query or "").lower()
    explanation = context.get("explanation") or {}
    comparison = context.get("comparison") or {}
    suggestions = comparison.get("suggestions", [])
    gaps = comparison.get("skill_gaps", [])
    probability = int(round(comparison.get("hiring_probability", 0)))

    if not comparison:
        answer = "Run a resume comparison first, and I can explain your score, identify missing skills, and suggest the fastest improvements."
    elif any(term in lowered for term in ("why", "low", "score", "explain")):
        answer = explanation.get("summary") or "Your score is being pulled down by weaker alignment or depth signals."
        if explanation.get("detailed"):
            answer = f"{answer} {explanation['detailed']}"
    elif any(term in lowered for term in ("improve", "better", "increase", "fix", "correct")):
        top_actions = suggestions[:3] or ["Add measurable impact statements.", "Close the most important skill gaps."]
        answer = "The highest-leverage improvements are: " + "; ".join(top_actions)
    elif any(term in lowered for term in ("gap", "missing", "lack")):
        answer = "The main missing skills are: " + (", ".join(_normalize_skill(skill) for skill in gaps[:4]) if gaps else "no major gaps detected.")
    elif any(term in lowered for term in ("probability", "hire", "chance", "apply")):
        answer = f"Your current hiring probability is about {probability}%. " + (
            "This looks strong enough to apply now." if probability >= 70 else
            "You can still apply, but tightening a few gaps first should help." if probability >= 55 else
            "I would improve the resume before using this role as a priority application."
        )
    else:
        answer = (
            "I can explain your score, highlight the biggest gaps, suggest resume corrections, and help you decide whether this role is worth applying for."
        )

    return {
        "answer": answer,
        "follow_ups": [
            "Why is my score low?",
            "How can I improve this resume?",
            "Which missing skills matter most?",
        ],
    }


def chat(query: str, context: dict | None = None) -> dict:
    fallback = _fallback_chat(query, context)
    if not _llm_available():
        return fallback

    context = context or {}
    comparison = context.get("comparison") or {}
    explanation = context.get("explanation") or {}
    resume = context.get("resume") or {}

    prompt = (
        "You are HireMind AI, a practical career assistant. "
        "Answer the user's question clearly in 2-4 sentences. Be specific, actionable, and grounded only in the given comparison context. "
        "If the user asks for corrections or improvements, focus on the top few highest-impact fixes. "
        "Return only valid JSON with keys: answer, follow_ups.\n\n"
        f"User question: {query}\n"
        f"A3 score: {comparison.get('a3_score', 0)}\n"
        f"Alignment: {comparison.get('alignment', 0)}\n"
        f"Depth: {comparison.get('depth', 0)}\n"
        f"Adaptability: {comparison.get('adaptability', 0)}\n"
        f"Hiring probability: {comparison.get('hiring_probability', 0)}\n"
        f"Skill gaps: {', '.join(comparison.get('skill_gaps', [])[:6]) or 'None'}\n"
        f"Suggestions: {'; '.join(comparison.get('suggestions', [])[:5]) or 'None'}\n"
        f"Explanation summary: {explanation.get('summary', '')}\n"
        f"Resume skills: {', '.join(((resume.get('parsed_data', {}) or {}).get('skills', []) if isinstance(resume, dict) else [])[:8]) or 'Unknown'}"
    )
    response_text = _call_gemini(prompt, temperature=0.45, max_tokens=450)
    payload = _extract_json_block(response_text)
    if not payload:
        return fallback

    follow_ups = payload.get("follow_ups")
    if not isinstance(follow_ups, list) or not follow_ups:
        follow_ups = fallback["follow_ups"]

    return {
        "answer": payload.get("answer") or fallback["answer"],
        "follow_ups": follow_ups[:4],
    }


def _build_blind_profile(candidate: dict, resume_data: dict) -> dict:
    skills = resume_data.get("skills", [])[:5]
    return {
        "alias": f"Candidate-{str(candidate.get('_id', 'NA'))[-4:]}",
        "experience": resume_data.get("experience", "Not specified"),
        "skills": skills,
        "college_hidden": True,
        "name_hidden": True,
    }


def _fallback_generate_insights(candidate: dict, comparison: dict, job: dict | None = None) -> dict:
    explanation = explain_score(comparison)
    strengths = explanation["strengths"]
    weaknesses = explanation["weaknesses"]
    hiring_probability = _safe_round(comparison.get("hiring_probability", 0))
    shortlist = hiring_probability >= 72 or comparison.get("a3_score", 0) >= 78

    interview_questions = [
        "Walk me through a project where you made a technical tradeoff and why.",
        "Tell me about a time you improved performance, reliability, or delivery speed.",
        "How would you approach learning a required skill that is new to you?",
    ]
    if job and "system design" in job.get("skills", []):
        interview_questions.append("How would you design a service that scales reliably under increasing traffic?")

    return {
        "summary": explanation["recruiter_brief"],
        "strengths": strengths,
        "weaknesses": weaknesses,
        "shortlist_recommendation": "Shortlist" if shortlist else "Keep in review",
        "shortlist_reason": (
            "The candidate shows strong fit and enough practical depth to move forward."
            if shortlist
            else "The candidate has promising signals but still shows meaningful skill or depth gaps."
        ),
        "interview_questions": interview_questions[:5],
        "blind_profile": _build_blind_profile(candidate, comparison.get("meta", {}).get("resume", {})),
        "hiring_signal": "High confidence" if hiring_probability >= 78 else "Promising" if hiring_probability >= 58 else "Needs validation",
    }


def generate_insights(candidate: dict, comparison: dict, job: dict | None = None) -> dict:
    fallback = _fallback_generate_insights(candidate, comparison, job)
    if not _llm_available():
        return fallback

    prompt = (
        "You are HireMind AI for recruiters. "
        "Return only valid JSON with keys: summary, strengths, weaknesses, shortlist_recommendation, shortlist_reason, interview_questions, hiring_signal. "
        "Use short practical language.\n\n"
        f"Candidate alias: {fallback['blind_profile']['alias']}\n"
        f"Role title: {(job or {}).get('title', 'Role')}\n"
        f"A3 score: {comparison.get('a3_score', 0)}\n"
        f"Hiring probability: {comparison.get('hiring_probability', 0)}\n"
        f"Skill gaps: {', '.join(comparison.get('skill_gaps', [])[:5]) or 'None'}\n"
        f"Fallback strengths: {', '.join(fallback['strengths'])}\n"
        f"Fallback weaknesses: {', '.join(fallback['weaknesses'])}"
    )
    response_text = _call_gemini(prompt, temperature=0.3, max_tokens=500)
    payload = _extract_json_block(response_text)
    if not payload:
        return fallback

    return {
        "summary": payload.get("summary") or fallback["summary"],
        "strengths": payload.get("strengths") or fallback["strengths"],
        "weaknesses": payload.get("weaknesses") or fallback["weaknesses"],
        "shortlist_recommendation": payload.get("shortlist_recommendation") or fallback["shortlist_recommendation"],
        "shortlist_reason": payload.get("shortlist_reason") or fallback["shortlist_reason"],
        "interview_questions": payload.get("interview_questions") or fallback["interview_questions"],
        "blind_profile": fallback["blind_profile"],
        "hiring_signal": payload.get("hiring_signal") or fallback["hiring_signal"],
    }


def recommend_jobs(user_profile: dict, jobs: list[dict]) -> list[dict]:
    ranked = []
    for job in jobs:
        match = match_candidate_to_job(user_profile, job, {"final_score": user_profile.get("profile_completeness", 65)})
        ranked.append(
            {
                "job_id": str(job.get("_id", "")),
                "title": job.get("title", "Role"),
                "experience_level": job.get("experience_level", ""),
                "skills": job.get("skills", [])[:4],
                "fit_score": round(match["cfma"]["fit_score"], 1),
                "holistic_score": round(match["hcs"]["holistic_score"], 1),
                "reason": match["ers"],
            }
        )
    ranked.sort(key=lambda item: (item["holistic_score"], item["fit_score"]), reverse=True)
    return ranked[:6]


def simulate_improvement(resume: dict, job: dict, comparison: dict | None = None) -> dict:
    comparison = comparison or {}
    base_score = _safe_round(comparison.get("a3_score", 0))
    base_probability = _safe_round(comparison.get("hiring_probability", 0))
    missing = comparison.get("skill_gaps", [])[:2]
    bonus = 0
    if missing:
        bonus += 6 * len(missing)
    if not (resume.get("projects") or resume.get("parsed_data", {}).get("projects")):
        bonus += 4
    projected_score = min(100.0, base_score + bonus)
    projected_probability = min(100.0, base_probability + max(5.0, bonus * 0.9))

    return {
        "headline": (
            f"Adding {', '.join(_normalize_skill(skill) for skill in missing)} and stronger impact bullets could raise your score."
            if missing
            else "Adding quantified impact and stronger project detail could raise your score."
        ),
        "projected_a3_score": round(projected_score, 1),
        "projected_hiring_probability": round(projected_probability, 1),
        "recommended_changes": [
            "Add one role-matching portfolio project.",
            "Include measurable results in experience bullets.",
            *[f"Show practical exposure to {_normalize_skill(skill)}." for skill in missing],
        ][:4],
    }


def llm_enabled() -> bool:
    return _llm_available()


def provider_status() -> dict[str, Any]:
    return {
        "llm_enabled": llm_enabled(),
        "mode": "gemini-rest" if llm_enabled() else "hybrid-fallback",
        "provider": "gemini" if llm_enabled() else "fallback",
        "model": GEMINI_MODEL if llm_enabled() else None,
    }
