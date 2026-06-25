import json
import random
import re
from dotenv import load_dotenv
load_dotenv()

from openai import OpenAI

client = OpenAI(
    base_url="https://router.huggingface.co/v1",
    api_key="your hf-token"  # huggingface.co/settings/tokens
)

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
    """Randomly reorder MC options and update correct_answer to match."""
    options = data.get("options", [])
    correct_letter = data.get("correct_answer", "A").strip().upper()
    correct_index = _LETTERS.index(correct_letter) if correct_letter in _LETTERS else 0
    correct_text = options[correct_index] if correct_index < len(options) else options[0]

    shuffled = options[:]
    random.shuffle(shuffled)
    new_letter = _LETTERS[shuffled.index(correct_text)]
    relabelled = [f"{_LETTERS[i]}) {opt.split(') ', 1)[-1]}" for i, opt in enumerate(shuffled)]

    return {
        **data,
        "options": relabelled,
        "correct_answer": new_letter,
        "correct_answer_text": data.get("correct_answer_text", ""),  # passes through from LLM
    }


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

_BATCH_MC_SYSTEM = """\
You generate multiple-choice exam questions for job candidates.
Return ONLY a valid JSON array of exactly {count} questions — no markdown, 
return correct_answer_text to describe the of the right answer when wrong choice selected, 
no extra text:
[
  {{
    "topic": "concise topic label (2-4 words)",
    "question_text": "...",
    "options": ["A) ...", "B) ...", "C) ...", "D) ..."],
    "correct_answer": "A",
    "correct_answer_text": "Explanation of why this answer is correct and why the others are wrong."
  }}
]
Requirements:
- Vary topics broadly — no two questions should test the same concept
- Difficulty should match the specified level throughout
- Each question must have exactly one clearly correct answer
- correct_answer_text should be 1-3 sentences, educational and constructive"""

_CODING_BATCH_SYSTEM = """\
You generate coding assessment questions for job candidates.
Return ONLY a valid JSON array of exactly 2 questions — no markdown, no extra text:
[
  {
    "focus": "strongest_area",
    "question_text": "Full coding problem description with example if helpful",
    "correct_answer": "Key criteria and model solution approach"
  },
  {
    "focus": "weakest_area",
    "question_text": "...",
    "correct_answer": "..."
  }
]
The candidate will write code as free text (not executed)."""

_EVAL_SYSTEM = """\
You evaluate a candidate's written coding answer.
Return ONLY valid JSON — no markdown, no extra text:
{
  "is_correct": true,
  "score": 0.85,
  "feedback": "brief constructive feedback"
}
score is 0.0–1.0. Set is_correct=true when score >= 0.6."""

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
        model="meta-llama/Llama-3.3-70B-Instruct",
        max_tokens=512,
        messages=[
            {"role": "system", "content": _PARSE_SYSTEM},
            {"role": "user", "content": job_description},
        ],
    )
    return _parse_json(response.choices[0].message.content)


def generate_question_bank(job_context: dict, difficulty: int, count: int = 30) -> list[dict]:
    """Generate a batch of MC questions at a given difficulty for a job's bank."""
    diff_label = _DIFFICULTY_LABEL[difficulty]
    context_block = (
        f"Role: {job_context.get('role', 'N/A')}\n"
        f"Domain: {job_context.get('domain', 'N/A')}\n"
        f"Required skills: {', '.join(job_context.get('required_skills', []))}\n"
        f"Behavioral focus: {', '.join(job_context.get('behavioral_focus', []))}\n"
        f"Technical depth: {job_context.get('technical_depth', 'N/A')}"
    )
    prompt = (
        f"Generate {count} diverse screening questions (mix of behavioral and technical) "
        f"at {diff_label} difficulty for this role:\n\n{context_block}\n\n"
        f"Cover a wide range of topics relevant to the role. Return JSON array only."
    )
    system = _BATCH_MC_SYSTEM.format(count=count)
    response = client.chat.completions.create(
        model="meta-llama/Llama-3.3-70B-Instruct",
        max_tokens=8000,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
    )
    questions = _parse_json_array(response.choices[0].message.content)
    return [_shuffle_options(q) for q in questions]

def explain_answer(question_text, options, correct_answer):
    prompt = f"""
                Question:
                {question_text}

                Options:
                {options}

                Correct answer:
                {correct_answer}

                Explain in 2-3 sentences why this answer is correct.
                """

    response = client.chat.completions.create(
        model="meta-llama/Llama-3.3-70B-Instruct",
        messages=[{"role":"user","content":prompt}]
    )

    return response.choices[0].message.content

def generate_coding_questions(
    job_context: dict,
    strongest_area: str,
    weakest_area: str,
    difficulty: int,
) -> list[dict]:
    """Generate 2 coding questions targeting the candidate's strongest and weakest areas."""
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
        f"Return JSON array only."
    )
    response = client.chat.completions.create(
        model="meta-llama/Llama-3.3-70B-Instruct",
        max_tokens=2000,
        messages=[
            {"role": "system", "content": _CODING_BATCH_SYSTEM},
            {"role": "user", "content": prompt},
        ],
    )
    return _parse_json_array(response.choices[0].message.content)


def evaluate_coding_answer(question_text: str, correct_answer: str, candidate_answer: str) -> dict:
    response = client.chat.completions.create(
        model="meta-llama/Llama-3.3-70B-Instruct",
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
        model="meta-llama/Llama-3.3-70B-Instruct",
        max_tokens=512,
        messages=[
            {"role": "system", "content": _FEEDBACK_SYSTEM},
            {"role": "user", "content": f"Candidate performance:\n\n" + "\n".join(lines)},
        ],
    )
    return _parse_json(response.choices[0].message.content)
