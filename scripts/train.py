"""Prepare the ML owner's fixed split. Does not fit, select, or publish a model."""

import json
from pathlib import Path

from hf_followup.config import ROOT
from hf_followup.data.ingest import ingest_csv
from hf_followup.ml.training import candidate_pipelines, fixed_split

if __name__ == "__main__":
    ingested = ingest_csv(ROOT / "data/heart_failure_clinical_records.csv")
    split = fixed_split(ingested.cohort, ingested.outcomes)
    output = Path("runtime/split_manifest.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(split, indent=2) + "\n")
    print(
        f"Prepared {len(split['development_ids'])} development / {len(split['test_ids'])} test IDs."
    )
    print(
        f"Candidate constructors: {', '.join(candidate_pipelines())}; evaluation/logging remain TODO in notebooks."
    )
