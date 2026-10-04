"""Grounded deterministic summaries and a strict future-generator boundary (PRD §18).

The current generator is a template, visibly labelled. Add an LLM adapter only with
structured output and semantic fact verification; schema validity alone is insufficient.
"""

from hf_followup.domain.errors import DomainError
from hf_followup.repositories.bundle import digest

PROMPT_VERSION = "factual-overview-v1"
GENERATOR_VERSION = "template-v1"


def template_summary(patient: dict) -> dict:
    facts = patient["facts"]
    conditions = [
        name.replace("_", " ")
        for name in ("anaemia", "diabetes", "high_blood_pressure")
        if facts[name]
    ]
    conditions_text = ", ".join(conditions) or "none of the three points-policy condition flags"
    score = patient["score"]
    method_text = (
        f"The {patient['method_id']} method gives a score of {score['value']:g} {score['label']}."
    )
    if score["kind"] == "model_output" and patient["method_id"] != "oldest_first":
        method_text = "The active model orders follow-up using an uncalibrated score; it does not provide a validated clinical risk percentage."
    text = (
        f"{patient['patient_id']} has recorded ejection fraction {facts['ejection_fraction']:g}% and serum creatinine {facts['serum_creatinine']:g} mg/dL. "
        f"Age is {facts['age']:g} years; recorded conditions include {conditions_text}. "
        f"{method_text} The displayed organ indicators use prototype measurement thresholds. "
        "This overview supports follow-up review and does not establish a new diagnosis or recommend treatment."
    )
    return {
        "patient_id": patient["patient_id"],
        "evidence_digest": patient["evidence_digest"],
        "text": text,
        "evidence_ids": [item["id"] for item in patient["evidence"]],
        "limitations": ["Historical measurements; symptoms, medicines, and contacts unavailable."],
        "status": "template",
        "prompt_version": PROMPT_VERSION,
        "generator_version": GENERATOR_VERSION,
    }


def cache_key(patient: dict) -> str:
    return digest(
        [patient["patient_id"], patient["evidence_digest"], PROMPT_VERSION, GENERATOR_VERSION]
    )


def validate_summary(candidate: dict, patient: dict) -> dict:
    # Until a reviewed semantic validator exists, only the exact factual template is
    # accepted. This fails closed on invented free-form statements or wrong numbers.
    expected = template_summary(patient)
    if any(
        candidate.get(key) != expected[key]
        for key in ("patient_id", "evidence_digest", "text", "evidence_ids")
    ):
        raise DomainError(
            "summary_grounding_failed", "Summary did not match verified patient evidence."
        )
    if len(candidate["text"].split()) > 100:
        raise DomainError("summary_too_long", "Summary exceeds 100 words.")
    return candidate
