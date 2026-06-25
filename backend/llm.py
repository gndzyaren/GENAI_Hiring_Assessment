import json
import re
import anthropic

client = anthropic.Anthropic()


def _parse_json(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text.strip())
    return json.loads(text)


_DIFFICULTY_LABEL = {
    1: "very basic, entry-level",
    2: "basic, junior-level",
    3: "intermediate, mid-level",
    4: "advanced, senior-level",
    5: "expert, staff/principal-level",
}

_PARSE_SYSTEM = """\
You analyze job descriptions and extract structured hiring context.
Return ONLY valid JSON — no markdown, no extra text:
{
  "role": "...",
  "domain": "...",
  "required_skills": ["..."],
  "behavioral_focus": ["..."],
  "technical_depth": "..."
}"""

_MC_SYSTEM = """\
You generate multiple-choice exam questions for job candidates.
Return ONLY valid JSON — no markdown, no extra text:
{
  "question_text": "...",
  "options": ["A) ...", "B) ...", "C) ...", "D) ..."],
  "correct_answer": "A",
  "explanation": "..."
}"""

_CODING_SYSTEM = """\
You generate coding assessment questions for job candidates.
Return ONLY valid JSON — no markdown, no extra text:
{
  "question_text": "...",
  "correct_answer": "...",
  "explanation": "..."
}
correct_answer should describe the key criteria / model solution."""

_EVAL_SYSTEM = """\
You evaluate a candidate's written coding answer.
Return ONLY valid JSON — no markdown, no extra text:
{
  "is_correct": true,
  "score": 0.85,
  "feedback": "brief constructive feedback"
}
score is 0.0–1.0. Set is_correct=true when score >= 0.6."""


def parse_job_description(job_description: str) -> dict:
    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=512,
        system=_PARSE_SYSTEM,
        messages=[{"role": "user", "content": job_description}],
    )
    return _parse_json(message.content[0].text)


def generate_question(
    job_context: dict,
    section: str,
    difficulty: int,
    previous_questions: list[str],
    question_type: str | None = None,
) -> dict:
    diff_label = _DIFFICULTY_LABEL[difficulty]
    prev_block = "\n".join(f"- {q}" for q in previous_questions) if previous_questions else "None"

    context_block = (
        f"Role: {job_context.get('role', 'N/A')}\n"
        f"Domain: {job_context.get('domain', 'N/A')}\n"
        f"Required skills: {', '.join(job_context.get('required_skills', []))}\n"
        f"Technical depth: {job_context.get('technical_depth', 'N/A')}"
    )

    if section == "coding":
        prompt = f"""Role context:
{context_block}

Generate a {diff_label} coding question relevant to this role.
The candidate will write code as free text (not executed).

Previously asked (do not repeat):
{prev_block}

Return JSON only."""
        system = _CODING_SYSTEM
    else:
        # screening section alternates behavioral and technical via question_type
        if question_type == "technical":
            focus = "technical skills and knowledge"
            extras = f"Skills to draw from: {', '.join(job_context.get('required_skills', []))}"
        else:
            focus = "behavioral / soft skills"
            extras = f"Behavioral themes: {', '.join(job_context.get('behavioral_focus', []))}"

        prompt = f"""Role context:
{context_block}
{extras}

Generate a {diff_label} {focus} multiple-choice question.
Exactly 4 options (A–D), one clearly correct answer.

Previously asked (do not repeat):
{prev_block}

Return JSON only."""
        system = _MC_SYSTEM

    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    return _parse_json(message.content[0].text)


def evaluate_coding_answer(question_text: str, correct_answer: str, candidate_answer: str) -> dict:
    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=512,
        system=_EVAL_SYSTEM,
        messages=[{
            "role": "user",
            "content": (
                f"Question:\n{question_text}\n\n"
                f"Key criteria / model answer:\n{correct_answer}\n\n"
                f"Candidate's answer:\n{candidate_answer}"
            ),
        }],
    )
    return _parse_json(message.content[0].text)
