"""Original command preserved; all calculations now use PRD-correct shared modules.

The original shared HI constant changed both organs, and the missing counter counted
cells rather than rows. Independent heart weight and fixed kidney weight now apply.
Install requirements first, then run this from any directory.
"""

from pathlib import Path

from hf_followup.data.ingest import ingest_csv
from hf_followup.evaluation.benchmark import case_benchmark


def main():
    ingestion = ingest_csv(Path(__file__).parent / "data/heart_failure_clinical_records.csv")
    manifest = ingestion.cohort.manifest
    report = case_benchmark(ingestion.cohort, ingestion.outcomes)
    print(
        f"Dropped {manifest['missing_rows']} rows with {manifest['missing_cells']} missing cells; accepted {manifest['accepted_count']} records."
    )
    for method, metrics in report["metrics"].items():
        print(
            f"{method:20s} recorded outcomes in top 25 = {metrics['captured_outcomes']}; precision = {metrics['precision_at_k']:.0%}"
        )
    print(f"Points queue overlap: {report['overlap_count']}/25; decision: {report['decision']}")
    print(report["reason"])


if __name__ == "__main__":
    main()
