from typing import Optional
from pydantic import BaseModel, EmailStr


class CreateJobRequest(BaseModel):
    title: str
    job_description: str
    recruiter_email: EmailStr


class JobOut(BaseModel):
    job_id: str
    title: str
    recruiter_email: str
    status: str
    created_at: str


class CandidateSummary(BaseModel):
    candidate_id: str
    name: str
    email: str
    session_id: Optional[str]
    total_score: Optional[float]
    status: str
    applied_at: str


class JobResultsOut(BaseModel):
    job_id: str
    title: str
    recruiter_email: str
    candidates: list[CandidateSummary]


class ApplyRequest(BaseModel):
    name: str
    email: EmailStr


class ApplyResponse(BaseModel):
    candidate_id: str
    session_id: str
    question: "QuestionOut"


class QuestionOut(BaseModel):
    question_id: str
    section: str
    difficulty: int
    question_text: str
    options: Optional[list[str]] = None
    question_number: int


class AnswerRequest(BaseModel):
    answer: str


class AnswerResponse(BaseModel):
    is_correct: bool
    score: float
    feedback: str
    next_question: Optional[QuestionOut] = None
    section_complete: bool = False
    exam_complete: bool = False


class ExamResults(BaseModel):
    session_id: str
    candidate_name: Optional[str]
    total_questions: int
    total_score: float
    section_scores: dict[str, float]
    status: str


ApplyResponse.model_rebuild()
