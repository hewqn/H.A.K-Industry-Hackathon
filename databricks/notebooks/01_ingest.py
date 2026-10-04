# Databricks notebook source
# MAGIC %md
# MAGIC # Ingest — ML/data + backend owners
# MAGIC Creates Delta tables and loads the validated CSV into patient_features and
# MAGIC cohort_manifests. Evaluation outcomes go to a separate restricted table.
# MAGIC
# MAGIC **Before running:** import or clone the repository into your workspace so that
# MAGIC `hf_followup` is importable. Update CATALOG, SCHEMA, and SOURCE_CSV below to
# MAGIC match your workspace.

# COMMAND ----------
# Configuration — update these for your workspace.
CATALOG = "hive_metastore"  # Or your Unity Catalog name.
SCHEMA = "hf_hackathon"
SOURCE_CSV = "/Workspace/Repos/TEAM/REPOSITORY/data/heart_failure_clinical_records.csv"

# COMMAND ----------
# MAGIC %md
# MAGIC ## 1. Create the database/schema if it doesn't exist

# COMMAND ----------
spark.sql(f"CREATE DATABASE IF NOT EXISTS {CATALOG}.{SCHEMA}")

# COMMAND ----------
# MAGIC %md
# MAGIC ## 2. Create Delta tables
# MAGIC These match `databricks/sql/001_tables.sql` exactly.

# COMMAND ----------
TABLE_DEFINITIONS = [
    (
        "raw_clinical_records",
        "cohort_id STRING, patient_id STRING, source_row BIGINT, "
        "source_hash STRING, raw_json STRING",
    ),
    (
        "patient_features",
        "cohort_id STRING, patient_id STRING, source_row BIGINT, features_json STRING",
    ),
    (
        "evaluation_outcomes",
        "cohort_id STRING, patient_id STRING, DEATH_EVENT BIGINT, follow_up_days DOUBLE",
    ),
    (
        "cohort_manifests",
        "cohort_id STRING, source_hash STRING, manifest_json STRING",
    ),
    (
        "model_predictions",
        "cohort_id STRING, model_id STRING, patient_id STRING, model_version STRING, "
        "score DOUBLE, prediction_json STRING, model_metadata_json STRING",
    ),
    (
        "evaluation_reports",
        "cohort_id STRING, report_id STRING, report_kind STRING, report_json STRING",
    ),
    (
        "application_events",
        "command_id STRING, session_id STRING, revision BIGINT, expected_revision BIGINT, "
        "command_digest STRING, payload_json STRING, created_at STRING",
    ),
    (
        "summary_cache",
        "cache_key STRING, patient_id STRING, evidence_digest STRING, payload_json STRING",
    ),
]

for table_name, columns in TABLE_DEFINITIONS:
    fqn = f"{CATALOG}.{SCHEMA}.{table_name}"
    spark.sql(f"CREATE TABLE IF NOT EXISTS {fqn} ({columns}) USING DELTA")
    print(f"OK {fqn}")

# COMMAND ----------
# MAGIC %md
# MAGIC ## 3. Validate and ingest the CSV
# MAGIC Uses the shared ingestion module to validate the CSV, assign stable patient IDs,
# MAGIC and separate features from evaluation outcomes.

# COMMAND ----------
import json
from pathlib import Path

from hf_followup.data.ingest import ingest_csv
from hf_followup.repositories.bundle import canonical

ingestion = ingest_csv(Path(SOURCE_CSV))
cohort = ingestion.cohort
manifest = cohort.manifest
cohort_id = manifest["cohort_id"]
source_hash = manifest["source_hash"]

print(f"Cohort: {cohort_id}")
print(f"Accepted: {manifest['accepted_count']}, Excluded: {manifest['excluded_count']}")
print(f"Source hash: {source_hash}")

# COMMAND ----------
# MAGIC %md
# MAGIC ## 4. Write cohort manifest

# COMMAND ----------
from pyspark.sql import Row

manifest_row = Row(
    cohort_id=cohort_id,
    source_hash=source_hash,
    manifest_json=canonical(manifest),
)
spark.createDataFrame([manifest_row]).write.format("delta").mode("overwrite").option(
    "replaceWhere", f"cohort_id = '{cohort_id}'"
).saveAsTable(f"{CATALOG}.{SCHEMA}.cohort_manifests")
print(f"OK Wrote manifest for {cohort_id}")

# COMMAND ----------
# MAGIC %md
# MAGIC ## 5. Write patient features
# MAGIC Features only — no outcomes, no raw CSV values beyond the allowlist.

# COMMAND ----------
feature_rows = [
    Row(
        cohort_id=cohort_id,
        patient_id=pid,
        source_row=record["source_row"],
        features_json=canonical(record["facts"]),
    )
    for pid, record in cohort.features.items()
]
spark.createDataFrame(feature_rows).write.format("delta").mode("overwrite").option(
    "replaceWhere", f"cohort_id = '{cohort_id}'"
).saveAsTable(f"{CATALOG}.{SCHEMA}.patient_features")
print(f"OK Wrote {len(feature_rows)} patient feature records")

# COMMAND ----------
# MAGIC %md
# MAGIC ## 6. Write raw clinical records (for audit trail)

# COMMAND ----------
import csv

raw_rows = []
with open(SOURCE_CSV, newline="", encoding="utf-8-sig") as handle:
    reader = csv.DictReader(handle)
    for row_number, row in enumerate(reader, 1):
        patient_id = f"HF-{row_number:04d}"
        raw_rows.append(
            Row(
                cohort_id=cohort_id,
                patient_id=patient_id,
                source_row=row_number,
                source_hash=source_hash,
                raw_json=json.dumps(row, sort_keys=True),
            )
        )
spark.createDataFrame(raw_rows).write.format("delta").mode("overwrite").option(
    "replaceWhere", f"cohort_id = '{cohort_id}'"
).saveAsTable(f"{CATALOG}.{SCHEMA}.raw_clinical_records")
print(f"OK Wrote {len(raw_rows)} raw clinical records")

# COMMAND ----------
# MAGIC %md
# MAGIC ## 7. Write evaluation outcomes (restricted access)
# MAGIC These are for the ML owner and evaluator only. The app must never read this table.

# COMMAND ----------
outcome_rows = [
    Row(
        cohort_id=cohort_id,
        patient_id=pid,
        DEATH_EVENT=outcome["DEATH_EVENT"],
        follow_up_days=outcome["time"],
    )
    for pid, outcome in ingestion.outcomes.items()
]
spark.createDataFrame(outcome_rows).write.format("delta").mode("overwrite").option(
    "replaceWhere", f"cohort_id = '{cohort_id}'"
).saveAsTable(f"{CATALOG}.{SCHEMA}.evaluation_outcomes")
print(f"OK Wrote {len(outcome_rows)} evaluation outcome records")

# COMMAND ----------
# MAGIC %md
# MAGIC ## 8. Verify
# MAGIC Quick check that the tables have the expected row counts.

# COMMAND ----------
for table_name, expected in [
    ("cohort_manifests", 1),
    ("patient_features", 299),
    ("raw_clinical_records", 299),
    ("evaluation_outcomes", 299),
]:
    fqn = f"{CATALOG}.{SCHEMA}.{table_name}"
    count = spark.sql(f"SELECT COUNT(*) FROM {fqn} WHERE cohort_id = '{cohort_id}'").collect()[0][0]
    status = "OK" if count == expected else "FAIL"
    print(f"{status} {table_name}: {count} rows (expected {expected})")

# COMMAND ----------
# MAGIC %md
# MAGIC ## Done
# MAGIC Tables are created and populated. Next steps:
# MAGIC - ML owner: run `02_training.ipynb` to train and publish predictions.
# MAGIC - Backend owner: verify external SQL access from `.env` credentials.
# MAGIC - Record verified capabilities in `databricks/capabilities.local.json`.
