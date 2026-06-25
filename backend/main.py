from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy.orm import Session

import database
import exam
import llm
import models
import schemas

models.Base.metadata.create_all(bind=database.engine)

app = FastAPI(title="Intelligent Assessment — MVP", version="0.1.0")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _prev_questions(responses: list[models.Response], section: str) -> list[str]:
    return [r.question_text for r in responses if r.section == section]


def _screening_type(section_question_count: int) -> str:
    """Alternate behavioral / technical within the screening section."""
    return "technical" if section_question_count % 2 == 1 else "behavioral"


def _pending_question(db: Session, session_id: str) -> models.Response:
    row = (
        db.query(models.Response)
        .filter(
            models.Response.session_id == session_id,
            models.Response.candidate_answer == None,  # noqa: E711
        )
        .order_by(models.Response.created_at.desc())
        .first()
    )
    if not row:
        raise HTTPException(status_code=400, detail="No pending question found")
    return row


def _question_out(response: models.Response, number: int) -> schemas.QuestionOut:
    return schemas.QuestionOut(
        question_id=response.id,
        section=response.section,
        difficulty=response.difficulty,
        question_text=response.question_text,
        options=response.options,
        question_number=number,
    )


def _session_score(session_id: str, db: Session) -> float | None:
    answered = db.query(models.Response).filter(
        models.Response.session_id == session_id,
        models.Response.score != None,  # noqa: E711
    ).all()
    if not answered:
        return None
    section_scores = exam.get_section_scores(answered)
    return round(sum(section_scores.values()) / len(section_scores), 3)


# ---------------------------------------------------------------------------
# Recruiter routes
# ---------------------------------------------------------------------------

@app.post("/jobs", response_model=schemas.JobOut)
def create_job(request: schemas.CreateJobRequest, db: Session = Depends(database.get_db)):
    job_context = llm.parse_job_description(request.job_description)
    job = models.Job(
        title=request.title,
        job_description=request.job_description,
        job_context=job_context,
        recruiter_email=request.recruiter_email,
    )
    db.add(job)
    db.commit()
    return schemas.JobOut(
        job_id=job.id,
        title=job.title,
        recruiter_email=job.recruiter_email,
        status=job.status,
        created_at=job.created_at.isoformat(),
    )


@app.get("/jobs/{job_id}", response_model=schemas.JobOut)
def get_job(job_id: str, db: Session = Depends(database.get_db)):
    job = db.query(models.Job).filter(models.Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return schemas.JobOut(
        job_id=job.id,
        title=job.title,
        recruiter_email=job.recruiter_email,
        status=job.status,
        created_at=job.created_at.isoformat(),
    )


@app.get("/jobs/{job_id}/results", response_model=schemas.JobResultsOut)
def get_job_results(job_id: str, db: Session = Depends(database.get_db)):
    job = db.query(models.Job).filter(models.Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    candidates = db.query(models.Candidate).filter(models.Candidate.job_id == job_id).all()

    summaries = []
    for c in candidates:
        session = (
            db.query(models.ExamSession)
            .filter(models.ExamSession.candidate_id == c.id)
            .order_by(models.ExamSession.created_at.desc())
            .first()
        )
        summaries.append(schemas.CandidateSummary(
            candidate_id=c.id,
            name=c.name,
            email=c.email,
            session_id=session.id if session else None,
            total_score=_session_score(session.id, db) if session else None,
            status=session.status if session else "not_started",
            applied_at=c.created_at.isoformat(),
        ))

    summaries.sort(key=lambda s: s.total_score if s.total_score is not None else -1, reverse=True)

    return schemas.JobResultsOut(
        job_id=job.id,
        title=job.title,
        recruiter_email=job.recruiter_email,
        candidates=summaries,
    )


@app.patch("/jobs/{job_id}/close")
def close_job(job_id: str, db: Session = Depends(database.get_db)):
    job = db.query(models.Job).filter(models.Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    job.status = "closed"
    db.commit()
    return {"job_id": job_id, "status": "closed"}


# ---------------------------------------------------------------------------
# Candidate routes
# ---------------------------------------------------------------------------

@app.post("/jobs/{job_id}/apply", response_model=schemas.ApplyResponse)
def apply(
    job_id: str,
    request: schemas.ApplyRequest,
    db: Session = Depends(database.get_db),
):
    job = db.query(models.Job).filter(models.Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status == "closed":
        raise HTTPException(status_code=400, detail="This job is no longer accepting applications")

    candidate = models.Candidate(
        job_id=job_id,
        name=request.name,
        email=request.email,
    )
    db.add(candidate)
    db.flush()

    session = models.ExamSession(
        candidate_id=candidate.id,
        job_context=job.job_context,
        candidate_name=request.name,
    )
    db.add(session)
    db.flush()

    q_data = llm.generate_question(
        job_context=job.job_context,
        section=session.current_section,
        difficulty=session.current_difficulty,
        previous_questions=[],
        question_type=_screening_type(0),
    )
    first_q = models.Response(
        session_id=session.id,
        section=session.current_section,
        difficulty=session.current_difficulty,
        question_text=q_data["question_text"],
        options=q_data.get("options"),
        correct_answer=q_data["correct_answer"],
    )
    db.add(first_q)
    db.commit()

    return schemas.ApplyResponse(
        candidate_id=candidate.id,
        session_id=session.id,
        question=_question_out(first_q, 1),
    )


# ---------------------------------------------------------------------------
# Exam routes
# ---------------------------------------------------------------------------

@app.get("/exam/{session_id}/question", response_model=schemas.QuestionOut)
def get_current_question(session_id: str, db: Session = Depends(database.get_db)):
    session = db.query(models.ExamSession).filter(models.ExamSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.status == "completed":
        raise HTTPException(status_code=400, detail="Exam already completed")
    pending = _pending_question(db, session_id)
    answered_count = (
        db.query(models.Response)
        .filter(
            models.Response.session_id == session_id,
            models.Response.candidate_answer != None,  # noqa: E711
        )
        .count()
    )
    return _question_out(pending, answered_count + 1)


@app.post("/exam/{session_id}/answer", response_model=schemas.AnswerResponse)
def submit_answer(
    session_id: str,
    request: schemas.AnswerRequest,
    db: Session = Depends(database.get_db),
):
    session = db.query(models.ExamSession).filter(models.ExamSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.status == "completed":
        raise HTTPException(status_code=400, detail="Exam already completed")

    pending = _pending_question(db, session_id)

    if session.current_section == "coding":
        result = llm.evaluate_coding_answer(
            question_text=pending.question_text,
            correct_answer=pending.correct_answer,
            candidate_answer=request.answer,
        )
        is_correct = result["is_correct"]
        score = result["score"]
        feedback = result["feedback"]
    else:
        submitted = request.answer.strip().upper()[:1]
        is_correct = submitted == pending.correct_answer.strip().upper()
        score = 1.0 if is_correct else 0.0
        feedback = (
            f"Correct! The answer is {pending.correct_answer}."
            if is_correct
            else f"Incorrect. The correct answer is {pending.correct_answer}."
        )

    pending.candidate_answer = request.answer
    pending.is_correct = is_correct
    pending.score = score
    pending.feedback = feedback
    db.flush()

    state = exam.advance_session(session, is_correct, db)

    if state["exam_complete"]:
        return schemas.AnswerResponse(
            is_correct=is_correct,
            score=score,
            feedback=feedback,
            section_complete=True,
            exam_complete=True,
        )

    all_responses = db.query(models.Response).filter(models.Response.session_id == session_id).all()
    prev_qs = _prev_questions(all_responses, session.current_section)

    q_data = llm.generate_question(
        job_context=session.job_context,
        section=session.current_section,
        difficulty=session.current_difficulty,
        previous_questions=prev_qs,
        question_type=_screening_type(session.section_question_count),
    )
    next_q = models.Response(
        session_id=session.id,
        section=session.current_section,
        difficulty=session.current_difficulty,
        question_text=q_data["question_text"],
        options=q_data.get("options"),
        correct_answer=q_data["correct_answer"],
    )
    db.add(next_q)
    db.commit()

    return schemas.AnswerResponse(
        is_correct=is_correct,
        score=score,
        feedback=feedback,
        next_question=_question_out(next_q, len(all_responses) + 1),
        section_complete=state["section_complete"],
        exam_complete=False,
    )


@app.get("/exam/{session_id}/results", response_model=schemas.ExamResults)
def get_results(session_id: str, db: Session = Depends(database.get_db)):
    session = db.query(models.ExamSession).filter(models.ExamSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    answered = db.query(models.Response).filter(
        models.Response.session_id == session_id,
        models.Response.score != None,  # noqa: E711
    ).all()

    section_scores = exam.get_section_scores(answered)
    total_score = sum(section_scores.values()) / len(section_scores) if section_scores else 0.0

    return schemas.ExamResults(
        session_id=session_id,
        candidate_name=session.candidate_name,
        total_questions=len(answered),
        total_score=round(total_score, 3),
        section_scores={k: round(v, 3) for k, v in section_scores.items()},
        status=session.status,
    )
