import re
from collections import Counter

import docx2txt
from PyPDF2 import PdfReader


KNOWN_SKILLS = {
    "python",
    "flask",
    "django",
    "javascript",
    "typescript",
    "react",
    "node",
    "sql",
    "mongodb",
    "postgresql",
    "aws",
    "docker",
    "kubernetes",
    "git",
    "rest",
    "api",
    "html",
    "css",
    "machine learning",
    "data analysis",
    "nlp",
    "communication",
    "leadership",
    "problem solving",
}

KNOWN_EDUCATION = {
    "b.tech",
    "bachelor",
    "master",
    "mca",
    "bca",
    "mba",
    "phd",
    "computer science",
    "information technology",
}


def read_resume_file(file_path: str) -> str:
    if file_path.lower().endswith(".pdf"):
        reader = PdfReader(file_path)
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    if file_path.lower().endswith((".doc", ".docx")):
        try:
            return docx2txt.process(file_path)
        except Exception:
            with open(file_path, "rb") as document_file:
                return document_file.read().decode("utf-8", errors="ignore")
    return ""


def extract_skills(text: str) -> list[str]:
    lowered = text.lower()
    found = [skill for skill in KNOWN_SKILLS if skill in lowered]
    return sorted(found)


def extract_experience(text: str) -> str:
    match = re.search(r"(\d+)\+?\s+years", text.lower())
    if not match:
        return "0-1 years"
    years = int(match.group(1))
    if years < 2:
        return "0-1 years"
    if years < 5:
        return "2-4 years"
    return "5+ years"


def extract_traits(text: str) -> list[str]:
    tokens = re.findall(r"[a-zA-Z]+", text.lower())
    counts = Counter(tokens)
    traits = []
    mapping = {
        "analytical": ["analysis", "analyze", "data", "logic"],
        "collaborative": ["team", "collaborate", "mentor", "support"],
        "adaptive": ["learn", "adapt", "change", "iterate"],
        "ownership": ["lead", "own", "drive", "deliver"],
    }
    for trait, keywords in mapping.items():
        if any(counts.get(keyword, 0) for keyword in keywords):
            traits.append(trait)
    return traits or ["adaptive"]


def extract_education(text: str) -> list[str]:
    lowered = text.lower()
    education = [item for item in KNOWN_EDUCATION if item in lowered]
    return sorted(education)


def extract_sections(text: str) -> dict:
    lowered = text.lower()
    return {
        "has_summary": any(keyword in lowered for keyword in ["summary", "profile", "objective"]),
        "has_skills": "skill" in lowered,
        "has_experience": any(keyword in lowered for keyword in ["experience", "employment", "work history"]),
        "has_education": "education" in lowered,
        "has_projects": "project" in lowered,
    }


def resume_semantic_extractor(text: str) -> dict:
    normalized = re.sub(r"\s+", " ", text).strip()
    return {
        "skills": extract_skills(normalized),
        "experience": extract_experience(normalized),
        "cognitive_traits": extract_traits(normalized),
        "education": extract_education(normalized),
        "sections": extract_sections(normalized),
        "summary": normalized[:300] + ("..." if len(normalized) > 300 else ""),
        "raw_text_length": len(normalized),
    }


def parse_resume_text(text: str) -> dict:
    return resume_semantic_extractor(text)
