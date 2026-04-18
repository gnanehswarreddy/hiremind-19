def score_relevance(resume_text: str, benchmark_skills: list[str] | None = None) -> int:
    benchmark_skills = benchmark_skills or ["python", "flask", "mongodb", "communication", "problem solving"]
    lowered = resume_text.lower()
    matched = sum(1 for skill in benchmark_skills if skill.lower() in lowered)
    return min(100, int((matched / max(len(benchmark_skills), 1)) * 100))


def score_representation(parsed_data: dict) -> int:
    checks = [
        bool(parsed_data.get("skills")),
        bool(parsed_data.get("experience")),
        bool(parsed_data.get("summary")),
        bool(parsed_data.get("cognitive_traits")),
    ]
    return int((sum(checks) / len(checks)) * 100)


def score_readability(resume_text: str) -> int:
    words = resume_text.split()
    sentences = [s for s in resume_text.replace("\n", " ").split(".") if s.strip()]
    if not words:
        return 20
    avg_sentence_len = len(words) / max(len(sentences), 1)
    bonus = 15 if 8 <= avg_sentence_len <= 22 else 0
    punctuation_bonus = 10 if "," in resume_text or ";" in resume_text else 0
    length_score = 45 if 150 <= len(words) <= 900 else 25
    return min(100, 30 + bonus + punctuation_bonus + length_score)


def calculate_r3_scores(resume_text: str, parsed_data: dict, benchmark_skills: list[str] | None = None) -> dict:
    relevance = score_relevance(resume_text, benchmark_skills)
    representation = score_representation(parsed_data)
    readability = score_readability(resume_text)
    final = round((relevance * 0.45) + (representation * 0.25) + (readability * 0.30), 2)
    return {
        "relevance_score": relevance,
        "representation_score": representation,
        "readability_score": readability,
        "final_score": final,
    }
