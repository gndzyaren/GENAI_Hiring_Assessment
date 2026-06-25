import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import relationship

from database import Base


def _uuid():
    return str(uuid.uuid4())


class Job(Base):
    __tablename__ = "jobs"

    id = Column(String, primary_key=True, default=_uuid)
    title = Column(String, nullable=False)
    job_description = Column(Text, nullable=False)
    job_context = Column(JSON, nullable=True)
    recruiter_email = Column(String, nullable=False)
    status = Column(String, default="open")
    include_coding = Column(Boolean, default=True)
    bank_status = Column(String, default="generating")  # generating | ready | error
    created_at = Column(DateTime, default=datetime.utcnow)

    candidates = relationship("Candidate", back_populates="job")
    bank_questions = relationship("BankQuestion", back_populates="job")


class BankQuestion(Base):
    __tablename__ = "bank_questions"

    id = Column(String, primary_key=True, default=_uuid)
    job_id = Column(String, ForeignKey("jobs.id"), nullable=False)
    section = Column(String, nullable=False)       # "screening"
    difficulty = Column(Integer, nullable=False)   # 1, 3, or 5
    topic = Column(String, nullable=True)
    question_text = Column(Text, nullable=False)
    options = Column(JSON, nullable=True)
    correct_answer = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    job = relationship("Job", back_populates="bank_questions")


class Candidate(Base):
    __tablename__ = "candidates"

    id = Column(String, primary_key=True, default=_uuid)
    job_id = Column(String, ForeignKey("jobs.id"), nullable=False)
    name = Column(String, nullable=False)
    email = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    job = relationship("Job", back_populates="candidates")
    sessions = relationship("ExamSession", back_populates="candidate")


class ExamSession(Base):
    __tablename__ = "exam_sessions"

    id = Column(String, primary_key=True, default=_uuid)
    candidate_id = Column(String, ForeignKey("candidates.id"), nullable=True)
    job_id = Column(String, ForeignKey("jobs.id"), nullable=True)
    job_context = Column(JSON, nullable=True)
    candidate_name = Column(String, nullable=True)
    include_coding = Column(Boolean, default=True)
    current_section = Column(String, default="screening")
    current_difficulty = Column(Integer, default=3)
    section_question_count = Column(Integer, default=0)
    status = Column(String, default="in_progress")
    feedback_summary = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    candidate = relationship("Candidate", back_populates="sessions")
    responses = relationship("Response", back_populates="session")


class Response(Base):
    __tablename__ = "responses"

    id = Column(String, primary_key=True, default=_uuid)
    session_id = Column(String, ForeignKey("exam_sessions.id"), nullable=False)
    bank_question_id = Column(String, ForeignKey("bank_questions.id"), nullable=True)
    section = Column(String, nullable=False)
    difficulty = Column(Integer, nullable=False)
    question_text = Column(Text, nullable=False)
    options = Column(JSON, nullable=True)
    correct_answer = Column(Text, nullable=False)
    candidate_answer = Column(Text, nullable=True)
    is_correct = Column(Boolean, nullable=True)
    score = Column(Float, nullable=True)
    feedback = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    session = relationship("ExamSession", back_populates="responses")
