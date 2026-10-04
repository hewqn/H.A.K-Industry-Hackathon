# Databricks notebook source
# MAGIC %md
# MAGIC # Ingest (standalone) — no package dependencies
# MAGIC Upload `heart_failure_clinical_records.csv` to your workspace (e.g. via the
# MAGIC Workspace file browser), then update CSV_PATH below to point to it.
# MAGIC
# MAGIC This notebook creates all Delta tables and loads the CSV without needing
# MAGIC the `hf_followup` package installed. Run this once; re-run is safe (idempotent).

# COMMAND ----------
# Configuration — update these for your workspace.
CATALOG = "workspace"
SCHEMA = "hf_hackathon"
CSV_PATH = "/Workspace/Users/kohinoorc0110@gmail.com/heart_failure_clinical_records.csv"

# COMMAND ----------
# MAGIC %md
# MAGIC ## 1. Create the database/schema

# COMMAND ----------
spark.sql(f"CREATE DATABASE IF NOT EXISTS {CATALOG}.{SCHEMA}")
print(f"OK {CATALOG}.{SCHEMA}")

# COMMAND ----------
# MAGIC %md
# MAGIC ## 2. Create Delta tables

# COMMAND ----------
TABLE_DEFINITIONS = [
    ("raw_clinical_records",
     "cohort_id STRING, patient_id STRING, source_row BIGINT, source_hash STRING, raw_json STRING"),
    ("patient_features",
     "cohort_id STRING, patient_id STRING, source_row BIGINT, features_json STRING"),
    ("evaluation_outcomes",
     "cohort_id STRING, patient_id STRING, DEATH_EVENT BIGINT, follow_up_days DOUBLE"),
    ("cohort_manifests",
     "cohort_id STRING, source_hash STRING, manifest_json STRING"),
    ("model_predictions",
     "cohort_id STRING, model_id STRING, patient_id STRING, model_version STRING, "
     "score DOUBLE, prediction_json STRING, model_metadata_json STRING"),
    ("evaluation_reports",
     "cohort_id STRING, report_id STRING, report_kind STRING, report_json STRING"),
    ("application_events",
     "command_id STRING, session_id STRING, revision BIGINT, expected_revision BIGINT, "
     "command_digest STRING, payload_json STRING, created_at STRING"),
    ("summary_cache",
     "cache_key STRING, patient_id STRING, evidence_digest STRING, payload_json STRING"),
]

for table_name, columns in TABLE_DEFINITIONS:
    fqn = f"{CATALOG}.{SCHEMA}.{table_name}"
    spark.sql(f"CREATE TABLE IF NOT EXISTS {fqn} ({columns}) USING DELTA")
    print(f"OK {fqn}")

# COMMAND ----------
# MAGIC %md
# MAGIC ## 3. Read and validate the CSV

# COMMAND ----------
import csv
import hashlib
import json
import math

# Feature columns the app is allowed to use (PRD §5).
FEATURES = (
    "age", "anaemia", "creatinine_phosphokinase", "diabetes", "ejection_fraction",
    "high_blood_pressure", "platelets", "serum_creatinine", "serum_sodium", "sex", "smoking",
)
BINARY_FIELDS = {"anaemia", "diabetes", "high_blood_pressure", "sex", "smoking"}
EVALUATION_FIELDS = ("time", "DEATH_EVENT")
REQUIRED = (*FEATURES, *EVALUATION_FIELDS)

# Read and hash the raw file.
raw_bytes = open(CSV_PATH, "rb").read()
source_hash = hashlib.sha256(raw_bytes).hexdigest()

features = {}   # patient_id -> {"patient_id", "source_row", "facts"}
outcomes = {}   # patient_id -> {"DEATH_EVENT", "time"}
raw_records = []
excluded = []
missing_rows = 0
missing_cells = 0

with open(CSV_PATH, newline="", encoding="utf-8-sig") as handle:
    reader = csv.DictReader(handle)
    for row_number, row in enumerate(reader, 1):
        patient_id = f"HF-{row_number:04d}"
        raw_records.append((patient_id, row_number, json.dumps(row, sort_keys=True)))

        # Check for missing values.
        empty = [f for f in REQUIRED
                 if row.get(f) is None or str(row[f]).strip().lower() in {"", "na", "nan", "null"}]
        if empty:
            missing_rows += 1
            missing_cells += len(empty)
            excluded.append({"patient_id": patient_id, "reason": "missing_values", "fields": empty})
            continue

        # Parse and validate numeric values.
        errors, values = [], {}
        for field in REQUIRED:
            try:
                v = float(row[field])
                if not math.isfinite(v):
                    raise ValueError("non-finite")
                values[field] = v
                if field in BINARY_FIELDS | {"DEATH_EVENT"} and v not in (0, 1):
                    errors.append(f"{field}:binary_encoding")
                if field == "ejection_fraction" and not 0 <= v <= 100:
                    errors.append(f"{field}:out_of_range")
            except (ValueError, TypeError):
                errors.append(f"{field}:invalid_numeric")

        if errors:
            excluded.append({"patient_id": patient_id, "reason": "invalid_record", "fields": errors})
            continue

        facts = {f: bool(values[f]) if f in BINARY_FIELDS else values[f] for f in FEATURES}
        features[patient_id] = {"patient_id": patient_id, "source_row": row_number, "facts": facts}
        outcomes[patient_id] = {"DEATH_EVENT": int(values["DEATH_EVENT"]), "time": values["time"]}

source_count = len(raw_records)
cohort_id = "uci-hf-299-v1"
print(f"Source rows: {source_count}")
print(f"Accepted: {len(features)}, Excluded: {len(excluded)}")
print(f"Missing rows: {missing_rows}, Missing cells: {missing_cells}")
print(f"Source hash: {source_hash}")

# COMMAND ----------
# MAGIC %md
# MAGIC ## 4. Build the manifest

# COMMAND ----------

def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)

manifest = {
    "cohort_id": cohort_id,
    "source_hash": source_hash,
    "schema_version": "patient-features-v1",
    "accepted_ids": list(features),
    "accepted_count": len(features),
    "source_count": source_count,
    "excluded_count": len(excluded),
    "missing_rows": missing_rows,
    "missing_cells": missing_cells,
    "exclusions": excluded,
    "warnings": [],
    "feature_allowlist": list(FEATURES),
    "source": "UCI Heart Failure Clinical Records",
    "license": "CC BY 4.0",
}
print(f"Manifest cohort_id: {cohort_id}")

# COMMAND ----------
# MAGIC %md
# MAGIC ## 5. Write to Delta tables

# COMMAND ----------
from pyspark.sql import Row

# Cohort manifest.
spark.createDataFrame([Row(
    cohort_id=cohort_id, source_hash=source_hash, manifest_json=_canonical(manifest),
)]).write.format("delta").mode("overwrite").option(
    "replaceWhere", f"cohort_id = '{cohort_id}'"
).saveAsTable(f"{CATALOG}.{SCHEMA}.cohort_manifests")
print(f"OK cohort_manifests: 1 row")

# Patient features.
feature_rows = [
    Row(cohort_id=cohort_id, patient_id=pid, source_row=rec["source_row"],
        features_json=_canonical(rec["facts"]))
    for pid, rec in features.items()
]
spark.createDataFrame(feature_rows).write.format("delta").mode("overwrite").option(
    "replaceWhere", f"cohort_id = '{cohort_id}'"
).saveAsTable(f"{CATALOG}.{SCHEMA}.patient_features")
print(f"OK patient_features: {len(feature_rows)} rows")

# Raw clinical records.
raw_rows = [
    Row(cohort_id=cohort_id, patient_id=pid, source_row=srow,
        source_hash=source_hash, raw_json=rjson)
    for pid, srow, rjson in raw_records
]
spark.createDataFrame(raw_rows).write.format("delta").mode("overwrite").option(
    "replaceWhere", f"cohort_id = '{cohort_id}'"
).saveAsTable(f"{CATALOG}.{SCHEMA}.raw_clinical_records")
print(f"OK raw_clinical_records: {len(raw_rows)} rows")

# Evaluation outcomes (restricted — ML/evaluator only).
outcome_rows = [
    Row(cohort_id=cohort_id, patient_id=pid,
        DEATH_EVENT=out["DEATH_EVENT"], follow_up_days=out["time"])
    for pid, out in outcomes.items()
]
spark.createDataFrame(outcome_rows).write.format("delta").mode("overwrite").option(
    "replaceWhere", f"cohort_id = '{cohort_id}'"
).saveAsTable(f"{CATALOG}.{SCHEMA}.evaluation_outcomes")
print(f"OK evaluation_outcomes: {len(outcome_rows)} rows")

# COMMAND ----------
# MAGIC %md
# MAGIC ## 6. Verify row counts

# COMMAND ----------
all_ok = True
for table_name, expected in [
    ("cohort_manifests", 1),
    ("patient_features", 299),
    ("raw_clinical_records", 299),
    ("evaluation_outcomes", 299),
]:
    fqn = f"{CATALOG}.{SCHEMA}.{table_name}"
    count = spark.sql(f"SELECT COUNT(*) FROM {fqn} WHERE cohort_id = '{cohort_id}'").collect()[0][0]
    status = "OK" if count == expected else "FAIL"
    if count != expected:
        all_ok = False
    print(f"{status} {table_name}: {count} rows (expected {expected})")

if all_ok:
    print("\nAll tables verified. Ingest complete.")
else:
    print("\nSome tables have unexpected counts. Check the output above.")

# COMMAND ----------
# MAGIC %md
# MAGIC ## Done
# MAGIC Tables are created and populated. Next steps:
# MAGIC - ML owner: run `02_training.ipynb` to train and publish predictions.
# MAGIC - Backend owner: verify external SQL access from `.env` credentials.
# MAGIC - Record verified capabilities in `databricks/capabilities.local.json`.
