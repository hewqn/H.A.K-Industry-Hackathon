# Databricks notebook source
# MAGIC %md
# MAGIC # Publish and synchronize — backend + ML owners
# MAGIC Frozen model/cache publication is implemented below. Cloud writes are gated
# MAGIC until the owner configures an approved Volume and catalog/schema.

# COMMAND ----------
import re
from pathlib import Path

from hf_followup.config import ROOT
from hf_followup.data.ingest import ingest_csv
from hf_followup.domain.predictions import RISK_TASKS
from hf_followup.ml.publishing import publish_experiment
from hf_followup.repositories.predictions import file_hash, resolve_bundle

# Use the full repo and the same environment that fitted the notebook artifacts.
# A permitted /Volumes/... export root also lets Spark read delta_predictions.jsonl.
EXPERIMENT_DIR = ROOT / "runtime/ml-experiments"
EXPORT_ROOT = ROOT / "runtime/ml-models"  # OWNER: change to an approved Volume for Delta.
PUBLISH_LOCAL = False  # Enable deliberately after notebook completion.
if PUBLISH_LOCAL:
    cohort = ingest_csv(ROOT / "data/heart_failure_clinical_records.csv").cohort
    bundle_directory = publish_experiment(EXPERIMENT_DIR, EXPORT_ROOT, cohort)
    print(f"Frozen publication ready: {bundle_directory}")


# COMMAND ----------
def publish_prediction_tables(spark_session, bundle_root: Path, namespace: str):
    """Write only this immutable version; reruns replace its partition, not other runs.

    This is an owner-run integration entry point, not a verified cloud deployment.
    Features/outcomes are owned by 01_ingest. Event tables are never touched here.
    """
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*", namespace):
        raise ValueError("Configure an approved simple catalog.schema identifier")
    directory, metadata = resolve_bundle(bundle_root)
    if not str(directory).startswith("/Volumes/"):
        raise ValueError("Use an approved Volume path readable by both Python and Spark")
    path = directory / "delta_predictions.jsonl"
    if file_hash(path) != metadata["file_hashes"][path.name]:
        raise ValueError("Delta prediction export checksum mismatch")
    report = (directory / "evaluation_report.json").read_text()
    if (
        file_hash(directory / "evaluation_report.json")
        != metadata["file_hashes"]["evaluation_report.json"]
    ):
        raise ValueError("Evaluation export checksum mismatch")
    schema = "cohort_id STRING, model_id STRING, patient_id STRING, model_version STRING, score DOUBLE, prediction_json STRING, model_metadata_json STRING"
    rows = spark_session.read.schema(schema).json(str(path))
    # Version writes are individually idempotent, not atomic across tables. The backend
    # must reject incomplete bundles; rerun the same immutable version after failure.
    for task in RISK_TASKS:
        version = metadata["models"][task]["model_version"]
        if version != f"{metadata['bundle_id']}/{task}":
            raise ValueError("Unexpected immutable model version")
        (
            rows.where(rows.model_id == task)
            .write.format("delta")
            .mode("overwrite")
            .option("replaceWhere", f"model_version = '{version}'")
            .saveAsTable(f"{namespace}.model_predictions")
        )
    reports = spark_session.createDataFrame(
        [(metadata["cohort_id"], metadata["bundle_id"], "exploratory_held_out_test", report)],
        "cohort_id STRING, report_id STRING, report_kind STRING, report_json STRING",
    )
    (
        reports.write.format("delta")
        .mode("overwrite")
        .option("replaceWhere", f"report_id = '{metadata['bundle_id']}'")
        .saveAsTable(f"{namespace}.evaluation_reports")
    )
    # TODO(ML-02): log trusted pipelines/metadata to the approved MLflow experiment
    # and retain actual run URLs. This local/Delta export does not claim MLflow logging.


PUBLISH_TO_DELTA = False  # OWNER: verify Volume/table permissions before enabling.
APPROVED_NAMESPACE = ""  # OWNER: permitted catalog.schema, never an arbitrary SQL fragment.
if PUBLISH_TO_DELTA:
    publish_prediction_tables(spark, EXPORT_ROOT, APPROVED_NAMESPACE)  # noqa: F821

# COMMAND ----------
# TODO(DB-02): choose live SQL OR restricted export/import with backend owner.
# Validate command bundle checksum. Replay command IDs in session order; check prior
# command and expected revision; append one complete state/snapshot event; read back
# by command ID, then emit a checksummed receipt. Query ambiguous commits before retry.
# Stop on conflicts. New offline writes are pending_sync, not Databricks commits.
# Events stay append-only. Do not truncate application_events for a demo reset.

# COMMAND ----------
# TODO(EVIDENCE): real prediction read/export checksum, durable event, restart recovery,
# duplicate replay prevention and one conflicting-revision drill. See docs/databricks.md.
