import json
import random
import re
from openai import OpenAI

client = OpenAI()

# ---- Helpers ---------------------------------------------------------------

_LETTERS = ["A", "B", "C", "D"]

_DIFFICULTY_LABEL = {
    1: "very basic, entry-level",
    2: "basic, junior-level",
    3: "intermediate, mid-level",
    4: "advanced, senior-level",
    5: "expert, staff/principal-level",
}


def _parse_json(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text.strip())
    return json.loads(text)


def _parse_json_array(text: str) -> list:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text.strip())
    return json.loads(text)


def _shuffle_options(data: dict) -> dict:
    """Randomly reorder MC options and update correct_answer to match. No-op for non-MCQ."""
    options = data.get("options")
    if not options:
        return data
    correct_letter = data.get("correct_answer", "A").strip().upper()
    correct_index = _LETTERS.index(correct_letter) if correct_letter in _LETTERS else 0
    correct_text = options[correct_index] if correct_index < len(options) else options[0]

    shuffled = options[:]
    random.shuffle(shuffled)
    new_letter = _LETTERS[shuffled.index(correct_text)]
    relabelled = [f"{_LETTERS[i]}) {opt.split(') ', 1)[-1]}" for i, opt in enumerate(shuffled)]

    return {**data, "options": relabelled, "correct_answer": new_letter}


# ---- Prompts ---------------------------------------------------------------

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

_BATCH_QUESTION_SYSTEM = """\
You generate screening exam questions for job candidates — a mix of multiple-choice and numerical/calculation questions.
Return ONLY a valid JSON array of exactly {count} questions — no markdown, no extra text.

Each question must follow one of these two formats:

MCQ format (use for ~70% of questions):
{{
  "topic": "concise topic label (2-4 words)",
  "question_text": "...",
  "options": ["A) ...", "B) ...", "C) ...", "D) ..."],
  "correct_answer": "A"
}}

Numerical format (use for ~30% — calculations, estimates, or short exact answers):
{{
  "topic": "concise topic label (2-4 words)",
  "question_text": "...",
  "options": null,
  "correct_answer": "the exact expected answer, e.g. 42 or O(n log n)"
}}

Requirements:
- Vary topics broadly — no two questions should test the same concept
- Difficulty must match the specified level throughout
- MCQ: exactly one clearly correct answer among the four options
- Numerical: one unambiguous correct answer (number, expression, or brief term)"""

_CODING_BATCH_SYSTEM = """\
You generate coding assessment questions for job candidates.
Return ONLY a valid JSON array of exactly 2 questions — no markdown, no extra text.
These are open-ended coding problems — do NOT include multiple-choice options under any circumstances.

[
  {
    "focus": "strongest_area",
    "question_text": "Full coding problem description with example if helpful",
    "correct_answer": "Key evaluation criteria and model solution approach"
  },
  {
    "focus": "weakest_area",
    "question_text": "...",
    "correct_answer": "..."
  }
]
The candidate writes code as free text. Never add an options field."""

_EVAL_SYSTEM = """\
You evaluate a candidate's written coding or numerical answer.
Return ONLY valid JSON — no markdown, no extra text:
{
  "is_correct": true,
  "score": 0.85,
  "feedback": "brief constructive feedback — do NOT reveal the correct answer"
}
score is 0.0–1.0. Set is_correct=true when score >= 0.6."""

_WRONG_FEEDBACK_SYSTEM = """\
You give brief feedback to a candidate who answered a screening question incorrectly.
Explain why their chosen answer is wrong and what concept they may have misunderstood.
Do NOT reveal or hint at the correct answer.
Keep it to 1-2 sentences. Return plain text only — no JSON, no markdown."""

_FEEDBACK_SYSTEM = """\
You analyze a candidate's exam performance and identify their strong and weak areas.
Return ONLY valid JSON — no markdown, no extra text:
{
  "strong_areas": ["area 1", "area 2"],
  "weak_areas": ["area 1", "area 2"]
}
Keep each area concise (2-5 words). List 2-4 items per category based on evidence from the answers."""


# ---- API calls -------------------------------------------------------------

def parse_job_description(job_description: str) -> dict:
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        max_tokens=512,
        messages=[
            {"role": "system", "content": _PARSE_SYSTEM},
            {"role": "user", "content": job_description},
        ],
    )
    return _parse_json(response.choices[0].message.content)


def generate_question_bank(job_context: dict, difficulty: int, count: int = 30) -> list[dict]:
    """Generate a batch of mixed MCQ/numerical questions at a given difficulty tier."""
    diff_label = _DIFFICULTY_LABEL[difficulty]
    context_block = (
        f"Role: {job_context.get('role', 'N/A')}\n"
        f"Domain: {job_context.get('domain', 'N/A')}\n"
        f"Required skills: {', '.join(job_context.get('required_skills', []))}\n"
        f"Behavioral focus: {', '.join(job_context.get('behavioral_focus', []))}\n"
        f"Technical depth: {job_context.get('technical_depth', 'N/A')}"
    )
    prompt = (
        f"Generate {count} diverse screening questions (mix of behavioral, technical, and calculation) "
        f"at {diff_label} difficulty for this role:\n\n{context_block}\n\n"
        f"Cover a wide range of topics. Include ~{count * 3 // 10} numerical/calculation questions. "
        f"Return JSON array only."
    )
    system = _BATCH_QUESTION_SYSTEM.format(count=count)
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        max_tokens=8000,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
    )
    questions = _parse_json_array(response.choices[0].message.content)
    return [_shuffle_options(q) for q in questions]


def generate_coding_questions(
    job_context: dict,
    strongest_area: str,
    weakest_area: str,
    difficulty: int,
) -> list[dict]:
    """Generate 2 open-ended coding questions targeting strongest and weakest areas."""
    diff_label = _DIFFICULTY_LABEL[difficulty]
    context_block = (
        f"Role: {job_context.get('role', 'N/A')}\n"
        f"Domain: {job_context.get('domain', 'N/A')}\n"
        f"Required skills: {', '.join(job_context.get('required_skills', []))}"
    )
    prompt = (
        f"Generate 2 coding questions at {diff_label} difficulty for this role:\n\n"
        f"{context_block}\n\n"
        f"Question 1 (focus=strongest_area): Test '{strongest_area}' — the candidate's strongest area. "
        f"Push them further in what they know.\n"
        f"Question 2 (focus=weakest_area): Test '{weakest_area}' — the candidate's weakest area. "
        f"Probe this gap directly.\n\n"
        f"Return JSON array only. No options fields — these are free-text coding problems."
    )
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        max_tokens=2000,
        messages=[
            {"role": "system", "content": _CODING_BATCH_SYSTEM},
            {"role": "user", "content": prompt},
        ],
    )
    questions = _parse_json_array(response.choices[0].message.content)
    # Strip options defensively — coding questions must never be MCQ
    return [{**q, "options": None} for q in questions]


def generate_incorrect_feedback(question_text: str, chosen_answer: str, topic: str) -> str:
    """Explain why the chosen answer is wrong without revealing the correct one."""
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        max_tokens=120,
        messages=[
            {"role": "system", "content": _WRONG_FEEDBACK_SYSTEM},
            {
                "role": "user",
                "content": (
                    f"Topic: {topic}\n"
                    f"Question: {question_text}\n"
                    f"Candidate's answer: {chosen_answer}"
                ),
            },
        ],
    )
    return response.choices[0].message.content.strip()


def evaluate_coding_answer(question_text: str, correct_answer: str, candidate_answer: str) -> dict:
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        max_tokens=512,
        messages=[
            {"role": "system", "content": _EVAL_SYSTEM},
            {
                "role": "user",
                "content": (
                    f"Question:\n{question_text}\n\n"
                    f"Key criteria / model answer:\n{correct_answer}\n\n"
                    f"Candidate's answer:\n{candidate_answer}"
                ),
            },
        ],
    )
    return _parse_json(response.choices[0].message.content)


def generate_candidate_feedback(responses: list[dict]) -> dict:
    lines = [
        f"Section: {r['section']} | Score: {r['score']:.0%} | Question: {r['question_text'][:120]}"
        for r in responses
    ]
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        max_tokens=512,
        messages=[
            {"role": "system", "content": _FEEDBACK_SYSTEM},
            {"role": "user", "content": "Candidate performance:\n\n" + "\n".join(lines)},
        ],
    )
    return _parse_json(response.choices[0].message.content)
