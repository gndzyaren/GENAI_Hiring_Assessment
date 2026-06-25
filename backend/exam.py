from sqlalchemy.orm import Session
from models import ExamSession, Response

SECTIONS = ["aptitude", "coding"]

NO_OF_QUESTIONS = {
    "aptitude": 6,
    "coding": 1,
}


def next_difficulty(current: int, is_correct: bool) -> int:
    if is_correct:
        return min(current + 1, 5)
    return max(current - 1, 1)

def get_section_scores(responses: list[Response]) -> dict[str, float]:
    scores = {}
    for section in SECTIONS:
        answered = [r for r in responses if r.section == section and r.score is not None]
        scores[section] = sum(r.score for r in answered) / len(answered) if answered else 0.0
    return scores

def advance_session(session: ExamSession, is_correct: bool, db: Session) -> dict:
    session.current_difficulty = next_difficulty(session.current_difficulty, is_correct)
    session.section_question_count += 1

    section_complete = session.section_question_count >= NO_OF_QUESTIONS[session.current_section]
    exam_complete = False

    if section_complete:
        idx = SECTIONS.index(session.current_section)
        if idx + 1 >= len(SECTIONS):
            session.status = "completed"
            exam_complete = True
        else:
            session.current_section = SECTIONS[idx + 1]
            session.section_question_count = 0
            session.current_difficulty = 3

    db.commit()
    return {"section_complete": section_complete, "exam_complete": exam_complete}

