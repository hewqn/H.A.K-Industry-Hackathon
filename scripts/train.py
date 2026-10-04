"""Refit the three frozen selections and publish their app-ready prediction bundle.

Experimentation stays in the notebook. This entry point does not run another search
or change the agreed model families, parameters, thresholds or band boundaries.
"""

import argparse
import json
from pathlib import Path

from hf_followup.config import ROOT
from hf_followup.data.ingest import ingest_csv
from hf_followup.ml.publishing import publish_experiment
from hf_followup.ml.training import train_frozen_selection


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection", type=Path, default=ROOT / "configs/ml_selection.json")
    parser.add_argument("--experiment-dir", type=Path, default=ROOT / "runtime/frozen-training")
    parser.add_argument("--output-root", type=Path, default=ROOT / "runtime/ml-models")
    args = parser.parse_args()
    ingestion = ingest_csv(ROOT / "data/heart_failure_clinical_records.csv")
    train_frozen_selection(ingestion, json.loads(args.selection.read_text()), args.experiment_dir)
    directory = publish_experiment(args.experiment_dir, args.output_root, ingestion.cohort)
    print(f"Published {directory}; restart the API to load the frozen scores.")


if __name__ == "__main__":
    main()
