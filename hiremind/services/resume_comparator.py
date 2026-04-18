import math
import os
import re
from collections import Counter
from tempfile import NamedTemporaryFile
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from flask import current_app

from services.embeddings import EMBEDDING_DIMENSION, generate_embedding
from services.parser import extract_experience, read_resume_file

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

try:
    import spacy
except ImportError:
    spacy = None


CANONICAL_SKILLS = {
    "python": ["python", "py"],
    "flask": ["flask"],
    "django": ["django"],
    "fastapi": ["fastapi"],
    "javascript": ["javascript", "js"],
    "typescript": ["typescript", "ts"],
    "react": ["react", "reactjs"],
    "angular": ["angular"],
    "vue": ["vue"],
    "node.js": ["node", "nodejs", "node.js"],
    "express": ["express", "expressjs"],
    "java": ["java"],
    "spring boot": ["spring", "spring boot"],
    "c++": ["c++", "cpp"],
    "c#": ["c#", ".net", "dotnet", "asp.net"],
    "sql": ["sql"],
    "mysql": ["mysql"],
    "postgresql": ["postgresql", "postgres", "psql"],
    "mongodb": ["mongodb", "mongo"],
    "redis": ["redis"],
    "aws": ["aws", "amazon web services"],
    "gcp": ["gcp", "google cloud"],
    "azure": ["azure"],
    "docker": ["docker", "containerization"],
    "kubernetes": ["kubernetes", "k8s"],
    "terraform": ["terraform"],
    "git": ["git", "github", "gitlab"],
    "rest api": ["rest", "rest api", "restful"],
    "graphql": ["graphql"],
    "microservices": ["microservices", "microservice"],
    "system design": ["system design", "scalable systems", "distributed systems"],
    "data structures": ["data structures", "algorithms", "dsa"],
    "machine learning": ["machine learning", "ml"],
    "deep learning": ["deep learning"],
    "nlp": ["nlp", "natural language processing"],
    "computer vision": ["computer vision"],
    "pandas": ["pandas"],
    "numpy": ["numpy"],
    "scikit-learn": ["scikit-learn", "sklearn"],
    "tensorflow": ["tensorflow"],
    "pytorch": ["pytorch"],
    "html": ["html", "html5"],
    "css": ["css", "css3"],
    "tailwind css": ["tailwind", "tailwindcss", "tailwind css"],
    "bootstrap": ["bootstrap"],
    "figma": ["figma"],
    "testing": ["testing", "pytest", "jest", "unit testing"],
    "ci/cd": ["ci/cd", "cicd", "continuous integration", "continuous deployment"],
    "linux": ["linux"],
}

RELATED_SKILL_CLUSTERS = [
    {"react", "angular", "vue"},
    {"python", "django", "flask", "fastapi"},
    {"node.js", "express", "javascript", "typescript"},
    {"aws", "gcp", "azure"},
    {"docker", "kubernetes", "terraform", "ci/cd"},
    {"machine learning", "deep learning", "nlp", "computer vision", "pytorch", "tensorflow", "scikit-learn"},
    {"sql", "postgresql", "mysql", "mongodb", "redis"},
    {"html", "css", "tailwind css", "bootstrap", "figma"},
]

ACTION_VERBS = {
    "built",
    "developed",
    "designed",
    "implemented",
    "optimized",
    "scaled",
    "led",
    "launched",
    "improved",
    "automated",
    "deployed",
    "engineered",
    "created",
    "owned",
    "delivered",
    "reduced",
    "increased",
}

COMPLEXITY_KEYWORDS = {
    "architecture",
    "distributed",
    "microservices",
    "real-time",
    "scalable",
    "scaling",
    "pipeline",
    "integration",
    "production",
    "deployment",
    "orchestration",
    "optimization",
}

IMPACT_KEYWORDS = {
    "%",
    "latency",
    "throughput",
    "revenue",
    "users",
    "customer",
    "customers",
    "performance",
    "uptime",
    "efficiency",
}

LEARNING_SIGNALS = {
    "learned",
    "learning",
    "transitioned",
    "adapted",
    "explored",
    "certified",
    "course",
    "bootcamp",
    "self-taught",
}

ROLE_KEYWORDS = {
    "data scientist": ["data scientist", "machine learning engineer", "ml engineer"],
    "backend engineer": ["backend", "backend engineer", "software engineer", "api developer"],
    "frontend engineer": ["frontend", "frontend engineer", "ui engineer", "web developer"],
    "full stack engineer": ["full stack", "full-stack", "software engineer"],
    "devops engineer": ["devops", "site reliability", "sre", "platform engineer"],
    "mobile developer": ["android", "ios", "mobile developer", "react native", "flutter"],
}

EXPERIENCE_PATTERNS = [
    ("senior", ["senior", "lead", "staff", "principal", "architect"]),
    ("mid", ["mid", "intermediate", "2+ years", "3+ years", "4+ years"]),
    ("junior", ["junior", "entry", "fresher", "graduate", "intern", "0-1", "1+ years"]),
]

HTML_BLOCK_PATTERNS = [
    re.compile(r"<script.*?</script>", re.IGNORECASE | re.DOTALL),
    re.compile(r"<style.*?</style>", re.IGNORECASE | re.DOTALL),
]


def _clamp(value: float, low: float = 0, high: float = 100) -> float:
    return round(max(low, min(high, value)), 2)


def _load_nlp():
    if spacy is None:
        return None
    for model_name in ("en_core_web_sm",):
        try:
            return spacy.load(model_name)
        except OSError:
            continue
    return None


NLP = _load_nlp()


def _normalize_text(text: str) -> str:
    cleaned = text or ""
    for pattern in HTML_BLOCK_PATTERNS:
        cleaned = pattern.sub(" ", cleaned)
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def _html_to_text(html: str) -> str:
    if BeautifulSoup is not None:
        return re.sub(r"\s+", " ", BeautifulSoup(html, "html.parser").get_text(" ", strip=True)).strip()
    return _normalize_text(html)


def _fetch_job_page(job_url: str) -> str:
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; HireMind/1.0; +https://hiremind.local)",
        "Accept-Language": "en-US,en;q=0.9",
    }
    request = Request(job_url, headers=headers)
    with urlopen(request, timeout=10) as response:
        content_type = response.headers.get("Content-Type", "")
        raw = response.read().decode("utf-8", errors="ignore")
        if "text/html" in content_type.lower() or "<html" in raw.lower():
            return raw
        return f"<html><body>{raw}</body></html>"


def _extract_role_type(text: str) -> str:
    lowered = text.lower()
    for role_type, phrases in ROLE_KEYWORDS.items():
        if any(phrase in lowered for phrase in phrases):
            return role_type
    return "generalist"


def _extract_experience_level(text: str) -> str:
    lowered = text.lower()
    for label, patterns in EXPERIENCE_PATTERNS:
        if any(pattern in lowered for pattern in patterns):
            return label
    years_match = re.search(r"(\d+)\+?\s+years", lowered)
    if years_match:
        years = int(years_match.group(1))
        if years >= 5:
            return "senior"
        if years >= 2:
            return "mid"
    return "junior"


def _extract_skill_mentions(text: str) -> list[str]:
    lowered = f" {text.lower()} "
    matches = set()
    for canonical, aliases in CANONICAL_SKILLS.items():
        for alias in aliases:
            alias_pattern = re.escape(alias.lower())
            if re.search(rf"(?<!\w){alias_pattern}(?!\w)", lowered):
                matches.add(canonical)
                break
    return sorted(matches)


def _extract_projects(text: str) -> list[str]:
    project_lines = []
    for line in re.split(r"[\r\n]+", text):
        normalized = re.sub(r"\s+", " ", line).strip(" -*\t")
        if not normalized:
            continue
        lowered = normalized.lower()
        if any(keyword in lowered for keyword in ("project", "built", "developed", "created", "implemented")):
            project_lines.append(normalized)
    return project_lines[:6]


def _extract_experience_bullets(text: str) -> list[str]:
    bullets = []
    for line in re.split(r"[\r\n]+", text):
        normalized = re.sub(r"\s+", " ", line).strip(" -*\t")
        if not normalized:
            continue
        if any(verb in normalized.lower() for verb in ACTION_VERBS):
            bullets.append(normalized)
    return bullets[:8]


def _extract_entities(text: str) -> dict:
    if NLP is None:
        return {"orgs": [], "products": []}
    doc = NLP(text[:150000])
    orgs = sorted({entity.text.strip() for entity in doc.ents if entity.label_ == "ORG" and entity.text.strip()})
    products = sorted({entity.text.strip() for entity in doc.ents if entity.label_ in {"PRODUCT", "WORK_OF_ART"} and entity.text.strip()})
    return {"orgs": orgs[:10], "products": products[:10]}


def parse_job_from_url(job_url: str) -> dict:
    try:
        html = _fetch_job_page(job_url)
    except (ValueError, HTTPError, URLError, TimeoutError) as exc:
        raise ValueError(f"Unable to fetch job posting from URL: {exc}") from exc

    text = _html_to_text(html)
    text = _normalize_text(text)
    if len(text) < 80:
        raise ValueError("The job URL did not contain enough readable job description content.")

    skills = _extract_skill_mentions(text)
    entities = _extract_entities(text)
    lines = [line.strip() for line in re.split(r"(?<=[.!?])\s+", text) if line.strip()]
    summary = " ".join(lines[:8])[:1600]
    title = entities["products"][0] if entities["products"] else ""

    return {
        "job_url": job_url,
        "description": text,
        "summary": summary,
        "skills": skills,
        "role_type": _extract_role_type(text),
        "experience_level": _extract_experience_level(text),
        "title": title or "Role from external posting",
        "entities": entities,
    }


def parse_resume_document(file_storage) -> dict:
    filename = file_storage.filename or "resume"
    suffix = os.path.splitext(filename)[1] or ".pdf"
    upload_dir = current_app.config.get("UPLOAD_FOLDER")
    with NamedTemporaryFile(delete=False, suffix=suffix, dir=upload_dir) as temp_file:
        file_storage.save(temp_file.name)
        temp_path = temp_file.name

    try:
        raw_text = read_resume_file(temp_path)
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)

    text = _normalize_text(raw_text)
    if len(text) < 40:
        raise ValueError("We could not extract enough text from the uploaded resume.")

    return {
        "filename": filename,
        "text": text,
        "skills": _extract_skill_mentions(text),
        "projects": _extract_projects(raw_text),
        "experience": extract_experience(text),
        "experience_bullets": _extract_experience_bullets(raw_text),
        "entities": _extract_entities(text),
        "learning_signals": sorted({signal for signal in LEARNING_SIGNALS if signal in text.lower()}),
        "summary": text[:1400],
    }


def normalize_job_payload(job_payload: dict) -> dict:
    description = _normalize_text(job_payload.get("description", "") or job_payload.get("summary", ""))
    combined_text = " ".join(
        part
        for part in [
            job_payload.get("title", ""),
            description,
            " ".join(job_payload.get("skills", [])),
            job_payload.get("experience_level", ""),
            job_payload.get("role_type", ""),
        ]
        if part
    )
    skills = sorted(set(job_payload.get("skills", []) or _extract_skill_mentions(combined_text)))
    return {
        "job_url": job_payload.get("job_url", ""),
        "description": description or combined_text,
        "summary": job_payload.get("summary", description[:1600] if description else combined_text[:1600]),
        "skills": skills,
        "role_type": job_payload.get("role_type") or _extract_role_type(combined_text),
        "experience_level": job_payload.get("experience_level") or _extract_experience_level(combined_text),
        "title": job_payload.get("title", "Role"),
        "entities": job_payload.get("entities", {}),
    }


def normalize_resume_payload(resume_payload: dict) -> dict:
    parsed_data = resume_payload.get("parsed_data", {}) or {}
    text = _normalize_text(resume_payload.get("text", "") or resume_payload.get("content", "") or parsed_data.get("summary", ""))
    raw_projects = resume_payload.get("projects")
    if raw_projects is None:
        raw_projects = parsed_data.get("projects")
    projects = raw_projects if isinstance(raw_projects, list) else _extract_projects(text)
    skills = resume_payload.get("skills") or parsed_data.get("skills") or _extract_skill_mentions(text)
    experience_bullets = resume_payload.get("experience_bullets") or _extract_experience_bullets(resume_payload.get("content", "") or text)
    return {
        "filename": resume_payload.get("filename", "resume"),
        "text": text,
        "skills": sorted(set(skills)),
        "projects": projects[:6] if isinstance(projects, list) else [],
        "experience": resume_payload.get("experience") or parsed_data.get("experience") or extract_experience(text),
        "experience_bullets": experience_bullets[:8] if isinstance(experience_bullets, list) else [],
        "entities": resume_payload.get("entities") or _extract_entities(text),
        "learning_signals": sorted({signal for signal in LEARNING_SIGNALS if signal in text.lower()}),
        "summary": resume_payload.get("summary") or parsed_data.get("summary") or text[:1400],
    }


def _cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    if not vec_a or not vec_b:
        return 0.0
    size = min(len(vec_a), len(vec_b), EMBEDDING_DIMENSION)
    dot = sum(vec_a[index] * vec_b[index] for index in range(size))
    norm_a = math.sqrt(sum(vec_a[index] * vec_a[index] for index in range(size))) or 1.0
    norm_b = math.sqrt(sum(vec_b[index] * vec_b[index] for index in range(size))) or 1.0
    return dot / (norm_a * norm_b)


def _semantic_match(job_skills: list[str], resume_skills: list[str]) -> tuple[float, list[dict]]:
    if not job_skills:
        return 0.0, []
    if not resume_skills:
        return 0.0, [{"job_skill": skill, "resume_skill": None, "similarity": 0.0} for skill in job_skills]

    resume_embeddings = {skill: generate_embedding(skill) for skill in resume_skills}
    matches = []
    weighted_total = 0.0
    total_weight = 0.0

    for index, job_skill in enumerate(job_skills):
        weight = max(1.0, len(job_skills) - index)
        job_embedding = generate_embedding(job_skill)
        best_resume_skill = None
        best_similarity = 0.0
        for resume_skill, resume_embedding in resume_embeddings.items():
            similarity = _cosine_similarity(job_embedding, resume_embedding)
            if similarity > best_similarity:
                best_similarity = similarity
                best_resume_skill = resume_skill
        weighted_total += max(0.0, best_similarity) * weight
        total_weight += weight
        matches.append(
            {
                "job_skill": job_skill,
                "resume_skill": best_resume_skill,
                "similarity": round(max(0.0, best_similarity) * 100, 2),
                "weight": round(weight, 2),
            }
        )

    score = (weighted_total / max(total_weight, 1.0)) * 100
    return _clamp(score), matches


def _count_occurrences(text: str, keywords: set[str]) -> int:
    lowered = text.lower()
    return sum(lowered.count(keyword) for keyword in keywords)


def _depth_score(resume_data: dict) -> tuple[float, dict]:
    text = resume_data.get("text", "")
    action_hits = _count_occurrences(text, ACTION_VERBS)
    complexity_hits = _count_occurrences(text, COMPLEXITY_KEYWORDS)
    impact_hits = _count_occurrences(text, IMPACT_KEYWORDS) + len(re.findall(r"\b\d+%|\b\d+\+?\s*(users|clients|apis|services|ms|seconds|hours)\b", text.lower()))
    project_bonus = len(resume_data.get("projects", [])) * 6

    impact_score = min(100, (impact_hits * 12) + project_bonus)
    complexity_score = min(100, (complexity_hits * 14) + (len(resume_data.get("projects", [])) * 8))
    context_score = min(100, (action_hits * 9) + (len(resume_data.get("experience_bullets", [])) * 6))

    depth = (impact_score + complexity_score + context_score) / 3
    return _clamp(depth), {
        "impact_score": _clamp(impact_score),
        "complexity_score": _clamp(complexity_score),
        "context_score": _clamp(context_score),
    }


def _adaptability_score(job_skills: list[str], resume_data: dict, semantic_matches: list[dict]) -> tuple[float, dict]:
    resume_skills = set(resume_data.get("skills", []))
    transferable_hits = 0
    cluster_hits = []

    for job_skill in job_skills:
        if job_skill in resume_skills:
            continue
        for cluster in RELATED_SKILL_CLUSTERS:
            if job_skill in cluster and resume_skills.intersection(cluster):
                transferable_hits += 1
                cluster_hits.append(
                    {
                        "target": job_skill,
                        "transferable_from": sorted(resume_skills.intersection(cluster)),
                    }
                )
                break

    semantic_transfer_hits = len([match for match in semantic_matches if 58 <= match["similarity"] < 80 and match.get("resume_skill")])
    learning_signal_hits = len(resume_data.get("learning_signals", []))
    transferable_score = min(100, (transferable_hits * 20) + (semantic_transfer_hits * 8))
    learning_score = min(100, 38 + (learning_signal_hits * 15) + (len(resume_data.get("projects", [])) * 5))
    adaptability = (transferable_score + learning_score) / 2
    return _clamp(adaptability), {
        "cluster_hits": cluster_hits[:6],
        "learning_score": _clamp(learning_score),
        "transferable_score": _clamp(transferable_score),
    }


def _dynamic_weights(role_type: str, experience_level: str) -> tuple[float, float, float]:
    alignment, depth, adaptability = 0.4, 0.35, 0.25

    if experience_level == "junior":
        adaptability += 0.05
        depth -= 0.03
        alignment -= 0.02
    elif experience_level == "senior":
        depth += 0.06
        adaptability -= 0.03
        alignment -= 0.03

    if role_type in {"backend engineer", "frontend engineer", "full stack engineer", "data scientist", "devops engineer"}:
        alignment += 0.04
        adaptability -= 0.02
        depth -= 0.02

    total = alignment + depth + adaptability
    return alignment / total, depth / total, adaptability / total


def _sigmoid_probability(a3_score: float, threshold: float) -> float:
    shifted = (a3_score - threshold) / 12
    probability = 1 / (1 + math.exp(-shifted))
    return _clamp(probability * 100)


def _rank_skill_gaps(job_data: dict, resume_data: dict, semantic_matches: list[dict]) -> list[dict]:
    matched_by_job_skill = {item["job_skill"]: item for item in semantic_matches}
    gaps = []
    for index, skill in enumerate(job_data.get("skills", [])):
        match = matched_by_job_skill.get(skill, {})
        similarity = match.get("similarity", 0)
        if similarity >= 78:
            continue
        importance = max(40, 96 - (index * 7))
        role_bonus = 8 if skill in {"system design", "aws", "docker", "kubernetes", "rest api"} else 0
        gaps.append(
            {
                "skill": skill,
                "importance": _clamp(importance + role_bonus),
                "current_similarity": _clamp(similarity),
            }
        )
    gaps.sort(key=lambda item: (item["importance"], -item["current_similarity"]), reverse=True)
    return gaps[:6]


def _build_suggestions(job_data: dict, resume_data: dict, gap_rows: list[dict], depth_breakdown: dict) -> list[str]:
    suggestions = []
    if gap_rows:
        top_gap_names = ", ".join(item["skill"].title() for item in gap_rows[:3])
        suggestions.append(f"Prioritize closing the top gaps: {top_gap_names}.")
    if depth_breakdown.get("impact_score", 0) < 65:
        suggestions.append("Add quantified outcomes to your resume bullets, such as latency improvements, revenue lift, or user growth.")
    if depth_breakdown.get("complexity_score", 0) < 60:
        suggestions.append("Show more technical depth by highlighting architecture choices, integrations, deployment, or scale challenges.")
    if len(resume_data.get("projects", [])) < 2:
        role_type = job_data.get("role_type", "target role")
        suggestions.append(f"Add a portfolio project tailored to a {role_type} role to demonstrate practical ownership.")
    if "system design" in {item["skill"] for item in gap_rows}:
        suggestions.append("Include a scalable backend or system design project with tradeoffs, APIs, and deployment notes.")
    if any(skill in {"aws", "gcp", "azure"} for skill in {item["skill"] for item in gap_rows}):
        suggestions.append("Add cloud deployment exposure and mention the exact services you used so recruiters can see production readiness.")
    return suggestions[:5]


def _build_simulation(result: dict, gap_rows: list[dict]) -> dict:
    gain = 0
    for gap in gap_rows[:2]:
        gain += 4 if gap["importance"] < 75 else 6
    projected = _clamp(result["a3_score"] + gain)
    probability_gain = _clamp(result["hiring_probability"] + max(5, gain * 0.9))
    return {
        "projected_a3_score": projected,
        "projected_hiring_probability": probability_gain,
        "headline": f"Closing the top {min(2, len(gap_rows))} gaps could lift your A³ score by about {int(round(projected - result['a3_score']))} points.",
    }


def compare_resume_to_job(job_url: str, file_storage) -> dict:
    job_data = parse_job_from_url(job_url)
    resume_data = parse_resume_document(file_storage)
    return compare_parsed_job_and_resume(job_data, resume_data)


def compare_parsed_job_and_resume(job_data: dict, resume_data: dict) -> dict:
    job_data = normalize_job_payload(job_data)
    resume_data = normalize_resume_payload(resume_data)

    alignment, semantic_matches = _semantic_match(job_data.get("skills", []), resume_data.get("skills", []))
    depth, depth_breakdown = _depth_score(resume_data)
    adaptability, adaptability_breakdown = _adaptability_score(job_data.get("skills", []), resume_data, semantic_matches)

    alignment_weight, depth_weight, adaptability_weight = _dynamic_weights(
        job_data.get("role_type", "generalist"),
        job_data.get("experience_level", "junior"),
    )
    a3_score = _clamp(
        (alignment * alignment_weight)
        + (depth * depth_weight)
        + (adaptability * adaptability_weight)
    )

    threshold = 64 if job_data.get("experience_level") == "junior" else 70 if job_data.get("experience_level") == "mid" else 76
    hiring_probability = _sigmoid_probability(a3_score, threshold)
    gap_rows = _rank_skill_gaps(job_data, resume_data, semantic_matches)
    suggestions = _build_suggestions(job_data, resume_data, gap_rows, depth_breakdown)

    result = {
        "a3_score": a3_score,
        "alignment": alignment,
        "depth": depth,
        "adaptability": adaptability,
        "hiring_probability": hiring_probability,
        "skill_gaps": [item["skill"] for item in gap_rows],
        "suggestions": suggestions,
        "simulation": {},
        "meta": {
            "weights": {
                "alignment": round(alignment_weight, 3),
                "depth": round(depth_weight, 3),
                "adaptability": round(adaptability_weight, 3),
            },
            "semantic_matches": semantic_matches[:10],
            "depth_breakdown": depth_breakdown,
            "adaptability_breakdown": adaptability_breakdown,
            "job": {
                "title": job_data.get("title"),
                "role_type": job_data.get("role_type"),
                "experience_level": job_data.get("experience_level"),
                "skills": job_data.get("skills", []),
                "summary": job_data.get("summary"),
            },
            "resume": {
                "filename": resume_data.get("filename"),
                "skills": resume_data.get("skills", []),
                "projects": resume_data.get("projects", []),
                "experience": resume_data.get("experience"),
            },
        },
    }
    result["simulation"] = _build_simulation(result, gap_rows)
    return result
