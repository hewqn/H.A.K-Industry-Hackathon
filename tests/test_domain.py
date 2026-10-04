"""Meaningful PRD acceptance checks for implemented numerical and schema boundaries."""

import csv
import json

import pytest

from hf_followup.config import ROOT
from hf_followup.data.ingest import ingest_csv
from hf_followup.domain.constants import FEATURES, SOURCE_HASH
from hf_followup.domain.errors import DomainError
from hf_followup.domain.indicators import organ_indicators
from hf_followup.domain.ranking import build_ranking, points_evidence
from hf_followup.evaluation.benchmark import case_benchmark
from hf_followup.ml.training import candidate_pipelines, fixed_split, training_frame


def test_bundled_lineage_and_no_leakage(ingested):
    manifest = ingested.cohort.manifest
    assert manifest["accepted_count"] == 299
    assert manifest["source_hash"] == SOURCE_HASH
    assert manifest["missing_rows"] == manifest["missing_cells"] == 0
    assert sum(outcome["DEATH_EVENT"] for outcome in ingested.outcomes.values()) == 96
    assert list(ingested.cohort.features)[0] == "HF-0001"
    assert set(ingested.cohort.features["HF-0001"]["facts"]) == set(FEATURES)


def test_missing_rows_cells_and_identity_survive_cleaning(tmp_path):
    with (ROOT / "data/heart_failure_clinical_records.csv").open() as handle:
        reader = csv.DictReader(handle)
        header, rows = reader.fieldnames, list(reader)[:3]
    rows[0]["age"] = rows[0]["diabetes"] = ""
    rows[1]["serum_creatinine"] = ""
    path = tmp_path / "fixture.csv"
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=header)
        writer.writeheader()
        writer.writerows(rows)
    result = ingest_csv(path, verify_bundled=False)
    assert result.cohort.manifest["missing_rows"] == 2
    assert result.cohort.manifest["missing_cells"] == 3
    assert list(result.cohort.features) == ["HF-0003"]


def test_invalid_record_is_quarantined(tmp_path):
    original = (ROOT / "data/heart_failure_clinical_records.csv").read_text()
    lines = original.splitlines()
    invalid = lines[1].split(",")
    invalid[1] = "2"  # Invalid anaemia encoding, not a truthy Boolean conversion.
    path = tmp_path / "invalid.csv"
    path.write_text(lines[0] + "\n" + ",".join(invalid) + "\n" + lines[2] + "\n")
    result = ingest_csv(path, verify_bundled=False)
    assert list(result.cohort.features) == ["HF-0002"]
    assert result.cohort.manifest["exclusions"][0]["reason"] == "invalid_record"


def test_required_threshold_boundaries_and_heart_only_revision(ingested):
    facts = dict(ingested.cohort.features["HF-0001"]["facts"])
    facts.update(
        ejection_fraction=35,
        serum_creatinine=1.5,
        age=70,
        anaemia=False,
        diabetes=False,
        high_blood_pressure=False,
    )
    assert [item["id"] for item in points_evidence(facts)] == ["age_flag"]
    for record in ingested.cohort.features.values():
        baseline, revised = points_evidence(record["facts"]), points_evidence(record["facts"], 3)
        assert sum(item["points"] for item in revised) - sum(
            item["points"] for item in baseline
        ) == int(record["facts"]["ejection_fraction"] < 35)
        assert [item for item in revised if item["id"] == "creatinine_flag"] == [
            item for item in baseline if item["id"] == "creatinine_flag"
        ]


def test_prd_benchmark_and_patient_rank(ingested):
    report = case_benchmark(ingested.cohort, ingested.outcomes)
    assert [
        report["metrics"][method]["captured_outcomes"]
        for method in ("oldest_first", "points_v1", "points_heart3")
    ] == [18, 21, 19]
    assert report["overlap_count"] == 22
    assert report["decision"] == "reject_candidate"
    ranking = build_ranking(ingested.cohort.features, {}, {}, "points_v1", 25)
    first = next(row for row in ranking["queue"] if row["patient_id"] == "HF-0001")
    assert first["call_rank"] == 14
    assert first["score"]["value"] == 6


def test_operational_population_does_not_change_benchmark(ingested):
    cohort = ingested.cohort
    initial = build_ranking(cohort.features, {}, {}, "points_v1", 25)
    contacted = initial["queue"][0]["patient_id"]
    operational = build_ranking(cohort.features, {contacted: "contacted"}, {}, "points_v1", 25)
    assert contacted not in {row["patient_id"] for row in operational["queue"]}
    assert len({row["patient_id"] for row in operational["queue"]}) == 25
    benchmark = build_ranking(
        cohort.features, {contacted: "contacted"}, {}, "points_v1", 25, mode="benchmark"
    )
    assert benchmark["queue"] == initial["queue"]


def test_pin_capacity_rejected(ingested):
    overrides = {
        "HF-0001": {"action": "pin", "sequence": 1},
        "HF-0002": {"action": "pin", "sequence": 2},
    }
    with pytest.raises(DomainError, match="active pin count"):
        build_ranking(ingested.cohort.features, {}, overrides, "points_v1", 1)


def test_shared_kidney_and_unknown_indicators():
    organs = organ_indicators({"ejection_fraction": 20, "serum_creatinine": 1.9})
    assert organs["heart"]["state"] == "flagged"
    assert organs["kidney_left"] == organs["kidney_right"]
    assert organ_indicators({})["heart"]["state"] == "unknown"


def test_ml_entry_points_are_leakage_safe(ingested):
    split = fixed_split(ingested.cohort, ingested.outcomes)
    assert len(split["development_ids"]) == 239 and len(split["test_ids"]) == 60
    assert not set(split["development_ids"]) & set(split["test_ids"])
    x, _ = training_frame(ingested.cohort, ingested.outcomes)
    assert list(x.columns) == list(FEATURES)
    assert "scale" in candidate_pipelines()["logistic_regression"].named_steps
    assert "DEATH_EVENT" not in json.dumps(ingested.cohort.features)
