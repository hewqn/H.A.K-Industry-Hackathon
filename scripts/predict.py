"""Batch inference for baseline-only JSON: {patient_id: {all eleven feature values}}.

Example: python scripts/predict.py --input patients.json --output predictions.json
No outcome labels or follow-up time are accepted; this command never fits a model.
"""

import argparse
import json
from pathlib import Path

from hf_followup.config import ROOT
from hf_followup.ml.inference import RiskPredictor


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, default=ROOT / "runtime/ml-models")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.input.resolve() == args.output.resolve():
        parser.error("Input and output paths must differ")
    patients = json.loads(args.input.read_text())
    if not isinstance(patients, dict):
        parser.error("Input must be a patient-ID-to-baseline-facts JSON object")
    predictions = RiskPredictor(args.bundle).predict_many(patients)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(predictions, indent=2, allow_nan=False) + "\n")
    print(f"Scored {len(predictions)} patients; saved {args.output}")


if __name__ == "__main__":
    main()
