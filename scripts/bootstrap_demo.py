"""Inspect ingestion + benchmark and export one safe API example for team integration."""

import json

from hf_followup.config import ROOT, Settings
from hf_followup.data.ingest import ingest_csv
from hf_followup.evaluation.benchmark import case_benchmark
from hf_followup.services.application import ApplicationService

if __name__ == "__main__":
    ingested = ingest_csv(ROOT / "data/heart_failure_clinical_records.csv")
    report = case_benchmark(ingested.cohort, ingested.outcomes)
    service = ApplicationService(ingested.cohort, report, Settings())
    sample = service.patient("HF-0001", service.default_snapshot["snapshot_id"])
    target = ROOT / "contracts/examples/patient.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(sample, indent=2) + "\n")
    print(
        f"Accepted {ingested.cohort.manifest['accepted_count']} records; missing rows/cells: {ingested.cohort.manifest['missing_rows']}/{ingested.cohort.manifest['missing_cells']}"
    )
    print({method: values["captured_outcomes"] for method, values in report["metrics"].items()})
