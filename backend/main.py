from dotenv import load_dotenv
load_dotenv()

import threading
from datetime import datetime, timedelta

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func
from sqlalchemy.orm import Session

import database
import exam
import llm
import models
import schemas

models.Base.metadata.create_all(bind=database.engine)

app = FastAPI(title="Intelligent Assessment", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_bank_difficulty(adaptive: int) -> int:
    """Map adaptive difficulty (1-5) to bank tier (1, 3, or 5)."""
    if adaptive <= 2:
        return 1
    if adaptive == 3:
        return 3
    return 5


def _generate_more_for_tier(job_id: str, difficulty: int) -> None:
    """Background thread: add 30 more questions to an exhausted bank tier."""
    db = next(database.get_db())
    try:
        job = db.query(models.Job).filter(models.Job.id == job_id).first()
        if not job:
            return
        questions = llm.generate_question_bank(job.job_context or {}, difficulty, count=30)
        for q in questions:
            bq = models.BankQuestion(
                job_id=job_id,
                section="screening",
                difficulty=difficulty,
                topic=q.get("topic"),
                question_text=q["question_text"],
                options=q.get("options"),
                correct_answer=q["correct_answer"],
            )
            db.add(bq)
        db.commit()
    except Exception:
        pass
    finally:
        db.close()


def _select_from_bank(
    db: Session,
    job_id: str,
    adaptive_difficulty: int,
    asked_ids: set[str],
) -> models.BankQuestion | None:
    tier = _to_bank_difficulty(adaptive_difficulty)
    q = (
        db.query(models.BankQuestion)
        .filter(
            models.BankQuestion.job_id == job_id,
            models.BankQuestion.section == "screening",
            models.BankQuestion.difficulty == tier,
            ~models.BankQuestion.id.in_(asked_ids) if asked_ids else True,
        )
        .order_by(func.random())
        .first()
    )
    if q is None and asked_ids:
        # Tier exhausted — generate more in background, fall back for this request
        threading.Thread(
            target=_generate_more_for_tier, args=(job_id, tier), daemon=True
        ).start()
        q = (
            db.query(models.BankQuestion)
            .filter(
                models.BankQuestion.job_id == job_id,
                models.BankQuestion.section == "screening",
                models.BankQuestion.difficulty == tier,
            )
            .order_by(func.random())
            .first()
        )
    return q


def _pending_question(db: Session, session_id: str) -> models.Response:
    row = (
        db.query(models.Response)
        .filter(
            models.Response.session_id == session_id,
            models.Response.candidate_answer == None,  # noqa: E711
        )
        .order_by(models.Response.created_at.asc())
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



def _analyze_screening_topics_from_bank(
    screening_responses: list[models.Response], db: Session
) -> tuple[str, str]:
    """Derive strongest and weakest areas from bank question topics."""
    topic_scores: dict[str, list[float]] = {}
    for r in screening_responses:
        if r.bank_question_id:
            bq = db.query(models.BankQuestion).filter(
                models.BankQuestion.id == r.bank_question_id
            ).first()
            topic = bq.topic if bq and bq.topic else "general"
        else:
            topic = "general"
        topic_scores.setdefault(topic, []).append(r.score or 0.0)

    if len(topic_scores) < 2:
        return "core technical skills", "foundational concepts"

    avgs = {t: sum(s) / len(s) for t, s in topic_scores.items()}
    ranked = sorted(avgs.items(), key=lambda x: x[1], reverse=True)
    return ranked[0][0], ranked[-1][0]


def _transition_to_coding(session: models.ExamSession, db: Session) -> None:
    """Generate 2 tailored coding questions and pre-load them as unanswered Responses."""
    screening_responses = db.query(models.Response).filter(
        models.Response.session_id == session.id,
        models.Response.section == "screening",
        models.Response.score != None,  # noqa: E711
    ).all()

    section_score = (
        sum(r.score for r in screening_responses) / len(screening_responses)
        if screening_responses else 0.5
    )
    coding_difficulty = exam.section1_score_to_difficulty(section_score)

    strongest, weakest = _analyze_screening_topics_from_bank(screening_responses, db)

    coding_qs = llm.generate_coding_questions(
        job_context=session.job_context or {},
        strongest_area=strongest,
        weakest_area=weakest,
        difficulty=coding_difficulty,
    )

    # Pre-load coding questions with staggered timestamps so ordering is stable
    base_time = datetime.utcnow()
    for i, q in enumerate(coding_qs):
        row = models.Response(
            session_id=session.id,
            section="coding",
            difficulty=coding_difficulty,
            question_text=q["question_text"],
            options=None,
            correct_answer=q.get("correct_answer", ""),
            created_at=base_time + timedelta(seconds=i),
        )
        db.add(row)
    db.flush()


# ---------------------------------------------------------------------------
# Background tasks
# ---------------------------------------------------------------------------

def _generate_bank(job_id: str) -> None:
    """Background: generate 30 questions × 3 difficulty tiers, store in bank."""
    db = next(database.get_db())
    try:
        job = db.query(models.Job).filter(models.Job.id == job_id).first()
        if not job:
            return
        job_context = job.job_context or {}

        for difficulty in [1, 3, 5]:
            questions = llm.generate_question_bank(job_context, difficulty, count=30)
            for q in questions:
                bq = models.BankQuestion(
                    job_id=job_id,
                    section="screening",
                    difficulty=difficulty,
                    topic=q.get("topic"),
                    question_text=q["question_text"],
                    options=q.get("options"),
                    correct_answer=q["correct_answer"],
                )
                db.add(bq)
            db.commit()

        job.bank_status = "ready"
        db.commit()
    except Exception:
        job = db.query(models.Job).filter(models.Job.id == job_id).first()
        if job:
            job.bank_status = "error"
            db.commit()
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Recruiter routes
# ---------------------------------------------------------------------------

@app.get("/recruiter/jobs", response_model=list[schemas.RecruiterJobItem])
def list_recruiter_jobs(db: Session = Depends(database.get_db)):
    jobs = db.query(models.Job).order_by(models.Job.created_at.desc()).all()
    return [
        schemas.RecruiterJobItem(
            job_id=j.id,
            title=j.title,
            status=j.status,
            bank_status=j.bank_status,
            include_coding=j.include_coding,
            candidate_count=len(j.candidates),
            created_at=j.created_at.isoformat(),
        )
        for j in jobs
    ]


@app.get("/jobs", response_model=list[schemas.JobListItem])
def list_jobs(db: Session = Depends(database.get_db)):
    jobs = (
        db.query(models.Job)
        .filter(models.Job.status == "open", models.Job.bank_status == "ready")
        .order_by(models.Job.created_at.desc())
        .all()
    )
    return [
        schemas.JobListItem(
            job_id=j.id,
            title=j.title,
            include_coding=j.include_coding,
            created_at=j.created_at.isoformat(),
        )
        for j in jobs
    ]


@app.post("/jobs", response_model=schemas.JobOut)
def create_job(
    request: schemas.CreateJobRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(database.get_db),
):
    job_context = llm.parse_job_description(request.job_description)
    job = models.Job(
        title=request.title,
        job_description=request.job_description,
        job_context=job_context,
        recruiter_email=request.recruiter_email,
        include_coding=request.include_coding,
        bank_status="generating",
    )
    db.add(job)
    db.commit()
    background_tasks.add_task(_generate_bank, job.id)
    return schemas.JobOut(
        job_id=job.id,
        title=job.title,
        recruiter_email=job.recruiter_email,
        status=job.status,
        include_coding=job.include_coding,
        bank_status=job.bank_status,
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
        include_coding=job.include_coding,
        bank_status=job.bank_status,
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
            feedback_summary=session.feedback_summary if session else None,
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
    if job.bank_status != "ready":
        raise HTTPException(status_code=503, detail="Question bank is still generating, please try again shortly")

    candidate = models.Candidate(
        job_id=job_id,
        name=request.name,
        email=request.email,
    )
    db.add(candidate)
    db.flush()

    session = models.ExamSession(
        candidate_id=candidate.id,
        job_id=job_id,
        job_context=job.job_context,
        candidate_name=request.name,
        include_coding=job.include_coding,
        current_section="screening",
        current_difficulty=3,
    )
    db.add(session)
    db.flush()

    bq = _select_from_bank(db, job_id, session.current_difficulty, set())
    if not bq:
        raise HTTPException(status_code=500, detail="No questions available in bank")

    first_q = models.Response(
        session_id=session.id,
        bank_question_id=bq.id,
        section=session.current_section,
        difficulty=session.current_difficulty,
        question_text=bq.question_text,
        options=bq.options,
        correct_answer=bq.correct_answer,
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

    # Score the answer
    if session.current_section == "coding" or (session.current_section == "screening" and not pending.options):
        # Coding or numerical — LLM evaluation
        result = llm.evaluate_coding_answer(
            question_text=pending.question_text,
            correct_answer=pending.correct_answer,
            candidate_answer=request.answer,
        )
        is_correct = result["is_correct"]
        score = result["score"]
        feedback = result["feedback"]
    else:
        # MCQ — exact letter match
        submitted = request.answer.strip().upper()[:1]
        is_correct = submitted == pending.correct_answer.strip().upper()
        score = 1.0 if is_correct else 0.0
        if is_correct:
            feedback = "Correct!"
        else:
            topic = "this topic"
            if pending.bank_question_id:
                bq = db.query(models.BankQuestion).filter(
                    models.BankQuestion.id == pending.bank_question_id
                ).first()
                if bq and bq.topic:
                    topic = bq.topic
            chosen_option = request.answer
            if pending.options:
                for opt in pending.options:
                    if opt.strip().upper().startswith(submitted):
                        chosen_option = opt
                        break
            feedback = llm.generate_incorrect_feedback(
                pending.question_text, chosen_option, topic
            )

    pending.candidate_answer = request.answer
    pending.is_correct = is_correct
    pending.score = score
    pending.feedback = feedback
    db.flush()

    state = exam.advance_session(session, is_correct, db, include_coding=session.include_coding)

    # If we just completed the screening section, generate coding questions
    if state["section_complete"] and not state["exam_complete"] and session.current_section == "coding":
        _transition_to_coding(session, db)
        db.commit()

        # Return next question (first coding question)
        all_responses = db.query(models.Response).filter(
            models.Response.session_id == session_id
        ).all()
        next_pending = _pending_question(db, session_id)
        answered_count = sum(1 for r in all_responses if r.candidate_answer is not None)
        return schemas.AnswerResponse(
            is_correct=is_correct,
            score=score,
            feedback=feedback,
            next_question=_question_out(next_pending, answered_count + 1),
            section_complete=True,
            exam_complete=False,
        )

    if state["exam_complete"]:
        all_responses = db.query(models.Response).filter(
            models.Response.session_id == session_id,
            models.Response.score != None,  # noqa: E711
        ).all()
        session.feedback_summary = llm.generate_candidate_feedback([
            {"section": r.section, "score": r.score, "question_text": r.question_text}
            for r in all_responses
        ])
        db.commit()
        return schemas.AnswerResponse(
            is_correct=is_correct,
            score=score,
            feedback=feedback,
            section_complete=True,
            exam_complete=True,
        )

    # Still in screening — pick next question from bank
    all_responses = db.query(models.Response).filter(
        models.Response.session_id == session_id
    ).all()
    asked_ids = {r.bank_question_id for r in all_responses if r.bank_question_id}

    bq = _select_from_bank(db, session.job_id, session.current_difficulty, asked_ids)
    if not bq:
        raise HTTPException(status_code=500, detail="No questions available in bank")

    answered_count = sum(1 for r in all_responses if r.candidate_answer is not None)
    next_q = models.Response(
        session_id=session.id,
        bank_question_id=bq.id,
        section=session.current_section,
        difficulty=session.current_difficulty,
        question_text=bq.question_text,
        options=bq.options,
        correct_answer=bq.correct_answer,
    )
    db.add(next_q)
    db.commit()

    return schemas.AnswerResponse(
        is_correct=is_correct,
        score=score,
        feedback=feedback,
        next_question=_question_out(next_q, answered_count + 1),
        section_complete=state["section_complete"],
        exam_complete=False,
    )


@app.get("/exam/{session_id}/transcript", response_model=schemas.TranscriptOut)
def get_transcript(session_id: str, db: Session = Depends(database.get_db)):
    session = db.query(models.ExamSession).filter(models.ExamSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    rows = (
        db.query(models.Response)
        .filter(models.Response.session_id == session_id)
        .order_by(models.Response.created_at.asc())
        .all()
    )

    responses = [
        schemas.ResponseOut(
            question_number=i + 1,
            section=r.section,
            difficulty=r.difficulty,
            question_text=r.question_text,
            options=r.options,
            candidate_answer=r.candidate_answer,
            correct_answer=r.correct_answer,
            is_correct=r.is_correct,
            score=r.score,
            feedback=r.feedback,
        )
        for i, r in enumerate(rows)
        if r.candidate_answer is not None
    ]

    return schemas.TranscriptOut(
        session_id=session_id,
        candidate_name=session.candidate_name,
        responses=responses,
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
        feedback_summary=session.feedback_summary,
    )
