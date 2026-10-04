"""Descriptive historical benchmark, separate from supervised model validation."""

from hf_followup.domain.ranking import build_ranking


def evaluate_queue(ranking: dict, outcomes: dict) -> dict:
    captured = sum(outcomes[row["patient_id"]]["DEATH_EVENT"] for row in ranking["queue"])
    total = sum(row["DEATH_EVENT"] for row in outcomes.values())
    selected = ranking["selected_count"]
    precision = captured / selected if selected else 0
    prevalence = total / len(outcomes) if outcomes else 0
    return {
        "n": len(outcomes),
        "k": selected,
        "captured_outcomes": captured,
        "precision_at_k": precision,
        "capture_at_k": captured / total if total else 0,
        "lift": precision / prevalence if prevalence else None,
    }


def case_benchmark(cohort, outcomes: dict) -> dict:
    snapshots = {
        method: build_ranking(cohort.features, {}, {}, method, 25, mode="benchmark")
        for method in ("oldest_first", "points_v1", "points_heart3")
    }
    metrics = {method: evaluate_queue(snapshot, outcomes) for method, snapshot in snapshots.items()}
    base, candidate = snapshots["points_v1"], snapshots["points_heart3"]
    base_ids = {row["patient_id"] for row in base["queue"]}
    candidate_ids = {row["patient_id"] for row in candidate["queue"]}
    base_rows = {row["patient_id"]: row for row in base["rows"]}
    moves = []
    for row in candidate["rows"]:
        pid = row["patient_id"]
        before = base_rows[pid]
        if pid in base_ids | candidate_ids:
            moves.append(
                {
                    "patient_id": pid,
                    "baseline_rank": before["call_rank"],
                    "candidate_rank": row["call_rank"],
                    "rank_delta": before["call_rank"] - row["call_rank"],
                    "membership": "entered"
                    if pid not in base_ids
                    else "left"
                    if pid not in candidate_ids
                    else "retained",
                    "score_delta": row["score"]["value"] - before["score"]["value"],
                    "reason": "EF < 35% adds one heart point; kidney weight stays 2"
                    if row["facts"]["ejection_fraction"] < 35
                    else "No added heart point; position changes relative to other patients",
                }
            )
    retained = (
        metrics["points_heart3"]["captured_outcomes"] > metrics["points_v1"]["captured_outcomes"]
    )
    return {
        "report_id": "case-benchmark-v1",
        "cohort_id": cohort.manifest["cohort_id"],
        "source_hash": cohort.manifest["source_hash"],
        "evaluation_mode": "descriptive_full_cohort",
        "tie_policy": base["tie_policy"],
        "metrics": metrics,
        "overlap_count": len(base_ids & candidate_ids),
        "overlap_fraction": len(base_ids & candidate_ids) / 25,
        "decision": "retain_candidate" if retained else "reject_candidate",
        "reason": "Retain only with strictly greater historical capture; equal or worse keeps the incumbent.",
        "movements": moves,
        "policies": {
            "baseline": {"heart_weight": 2, "kidney_weight": 2},
            "candidate": {"heart_weight": 3, "kidney_weight": 2},
        },
        "limitations": [
            "Retrospective sensitivity experiment, not independent model validation.",
            "Historical capture does not show a benefit from calling patients.",
        ],
    }
