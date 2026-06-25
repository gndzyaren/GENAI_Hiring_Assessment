from sqlalchemy.orm import Session
from models import ExamSession, Response

SECTIONS = ["screening", "coding"]

NO_OF_QUESTIONS = {
    "screening": 5,
    "coding": 2,
}


def next_difficulty(current: int, is_correct: bool) -> int:
    if is_correct:
        return min(current + 1, 5)
    return max(current - 1, 1)


def section1_score_to_difficulty(score: float) -> int:
    """Map a 0-1 section score to a bank difficulty tier (1, 3, or 5)."""
    if score >= 0.7:
        return 5
    if score >= 0.4:
        return 3
    return 1


def get_section_scores(responses: list[Response]) -> dict[str, float]:
    scores = {}
    for section in SECTIONS:
        answered = [r for r in responses if r.section == section and r.score is not None]
        scores[section] = sum(r.score for r in answered) / len(answered) if answered else 0.0
    return scores


def advance_session(session: ExamSession, is_correct: bool, db: Session, include_coding: bool = True) -> dict:
    session.current_difficulty = next_difficulty(session.current_difficulty, is_correct)
    session.section_question_count += 1

    active_sections = SECTIONS if include_coding else ["screening"]
    section_complete = session.section_question_count >= NO_OF_QUESTIONS[session.current_section]
    exam_complete = False

    if section_complete:
        idx = active_sections.index(session.current_section)
        if idx + 1 >= len(active_sections):
            session.status = "completed"
            exam_complete = True
        else:
            session.current_section = active_sections[idx + 1]
            session.section_question_count = 0
            session.current_difficulty = 3

    db.commit()
    return {"section_complete": section_complete, "exam_complete": exam_complete}
