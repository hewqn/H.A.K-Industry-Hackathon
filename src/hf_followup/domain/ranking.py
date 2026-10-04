"""Deterministic scoring and queue assembly. Outcome labels never enter this module."""

import hashlib

from hf_followup.domain.constants import METHODS, POINTS_POLICY, TIE_POLICY
from hf_followup.domain.errors import DomainError


def tie_key(record: dict) -> tuple[str, str]:
    return hashlib.sha256(f"patient-{record['source_row']}".encode()).hexdigest(), record[
        "patient_id"
    ]


def points_evidence(facts: dict, heart_weight: int = 2) -> list[dict]:
    # Required revision changes EF alone. Kidney weight remains 2.
    predicates = [
        (
            "ef_flag",
            "ejection_fraction",
            facts["ejection_fraction"] < 35,
            heart_weight,
            "%",
            "EF < 35%",
        ),
        (
            "creatinine_flag",
            "serum_creatinine",
            facts["serum_creatinine"] > 1.5,
            2,
            "mg/dL",
            "creatinine > 1.5 mg/dL",
        ),
        ("anaemia_flag", "anaemia", facts["anaemia"], 1, None, "recorded anaemia"),
        ("diabetes_flag", "diabetes", facts["diabetes"], 1, None, "recorded diabetes"),
        (
            "bp_flag",
            "high_blood_pressure",
            facts["high_blood_pressure"],
            1,
            None,
            "recorded high blood pressure",
        ),
        ("age_flag", "age", facts["age"] >= 70, 1, "years", "age ≥ 70"),
    ]
    return [
        {
            "id": eid,
            "field": field,
            "value": facts[field],
            "unit": unit,
            "predicate": predicate,
            "points": weight,
            "scale": "additive_points",
        }
        for eid, field, active, weight, unit, predicate in predicates
        if active
    ]


def score_record(record: dict, method_id: str, predictions: dict) -> dict:
    facts = record["facts"]
    if method_id == "oldest_first":
        return {
            "value": facts["age"],
            "kind": "model_output",
            "label": "age ordering (years)",
            "evidence": [
                {
                    "id": "age_order",
                    "field": "age",
                    "value": facts["age"],
                    "unit": "years",
                    "predicate": "older age first",
                    "scale": "years",
                }
            ],
            "explanation_method": "age_baseline",
            "version": "age-v1",
        }
    if method_id in {"points_v1", "points_heart3"}:
        evidence = points_evidence(facts, 3 if method_id == "points_heart3" else 2)
        return {
            "value": sum(item["points"] for item in evidence),
            "kind": "points",
            "label": "points",
            "evidence": evidence,
            "explanation_method": "additive_points",
            "version": POINTS_POLICY,
        }
    if (
        method_id not in predictions
        or record["patient_id"] not in predictions[method_id]["patients"]
    ):
        raise DomainError("model_unavailable", "Model predictions have not been published.", 503)
    model = predictions[method_id]
    prediction = model["patients"][record["patient_id"]]
    return {
        "value": prediction["score"],
        "kind": "model_output",
        "label": "uncalibrated model score",
        "evidence": prediction["evidence"],
        "explanation_method": model["explanation_method"],
        "version": model["model_version"],
        "prediction_provenance": prediction["prediction_provenance"],
        "intercept": model.get("intercept"),
        "calibration_status": "not_calibrated",
    }


def build_ranking(
    features: dict,
    workflow: dict,
    overrides: dict,
    method_id: str,
    capacity: int,
    *,
    mode: str = "operational",
    predictions: dict | None = None,
) -> dict:
    if not 1 <= capacity <= 50:
        raise DomainError("invalid_capacity", "Capacity must be between 1 and 50.")
    if mode == "benchmark" and capacity != 25:
        raise DomainError("benchmark_capacity", "The case benchmark fixes capacity at 25.")
    if method_id not in METHODS and method_id not in (predictions or {}):
        raise DomainError("unknown_method", "Choose a registered ranking method.")
    eligible = [
        record
        for pid, record in features.items()
        if mode == "benchmark"
        or (
            workflow.get(pid, "pending") != "contacted"
            and overrides.get(pid, {}).get("action") != "defer"
        )
    ]
    scored = {
        record["patient_id"]: score_record(record, method_id, predictions or {})
        for record in eligible
    }
    ordered = sorted(
        eligible, key=lambda record: (-scored[record["patient_id"]]["value"], *tie_key(record))
    )
    model_ranks = {record["patient_id"]: rank for rank, record in enumerate(ordered, 1)}
    pins = sorted(
        [
            pid
            for pid in model_ranks
            if mode != "benchmark" and overrides.get(pid, {}).get("action") == "pin"
        ],
        key=lambda pid: overrides[pid]["sequence"],
    )
    if len(pins) > capacity:
        raise DomainError(
            "pin_capacity_conflict", "Capacity cannot be smaller than the active pin count.", 409
        )
    call_order = pins + [
        record["patient_id"] for record in ordered if record["patient_id"] not in pins
    ]
    rows = []
    for rank, pid in enumerate(call_order, 1):
        evidence = scored[pid]["evidence"]
        rows.append(
            {
                "patient_id": pid,
                "model_rank": model_ranks[pid],
                "call_rank": rank,
                "in_queue": rank <= capacity,
                "priority_band": "higher"
                if rank <= capacity
                else "elevated"
                if rank <= 3 * capacity
                else "lower",
                "score": scored[pid],
                "facts": features[pid]["facts"],
                "reason": "; ".join(item["predicate"] for item in evidence[:3])
                or "No points predicates activated",
                "workflow_state": workflow.get(pid, "pending")
                if mode != "benchmark"
                else "pending",
                "override": overrides.get(pid) if mode != "benchmark" else None,
            }
        )
    return {
        "method_id": method_id,
        "capacity": capacity,
        "mode": mode,
        "eligible_count": len(rows),
        "selected_count": min(capacity, len(rows)),
        "tie_policy": TIE_POLICY,
        "rows": rows,
        "queue": rows[:capacity],
    }
