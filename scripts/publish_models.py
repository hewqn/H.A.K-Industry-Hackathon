"""Freeze the notebook's selected models into the app's local read/inference bundle."""

import argparse
from pathlib import Path

from hf_followup.config import ROOT
from hf_followup.data.ingest import ingest_csv
from hf_followup.ml.publishing import publish_experiment


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment-dir", type=Path, default=ROOT / "runtime/ml-experiments")
    parser.add_argument("--output-root", type=Path, default=ROOT / "runtime/ml-models")
    args = parser.parse_args()
    cohort = ingest_csv(ROOT / "data/heart_failure_clinical_records.csv").cohort
    try:
        directory = publish_experiment(args.experiment_dir, args.output_root, cohort)
    except ValueError as exc:
        parser.exit(
            1,
            f"Publication failed: {exc}\nIf the notebook used different library versions, run make train to refit the frozen selections with the pinned dependencies.\n",
        )
    print(f"Published {directory}; restart the API to activate its prediction cache.")


if __name__ == "__main__":
    main()
