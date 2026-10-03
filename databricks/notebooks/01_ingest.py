# Databricks notebook source
# MAGIC %md
# MAGIC # Ingest — ML/data + backend owners
# MAGIC Configure a permitted workspace/repo import path and validate before Delta writes.
# MAGIC This skeleton performs no cloud writes; preserve identity before cleaning.

# COMMAND ----------
from pathlib import Path

from hf_followup.data.ingest import ingest_csv

# TODO(OWNER): replace with an allowed repo/volume path and make the package importable.
SOURCE_CSV = Path("/Workspace/Repos/TEAM/REPOSITORY/data/heart_failure_clinical_records.csv")
# ingestion = ingest_csv(SOURCE_CSV)
# print(ingestion.cohort.manifest)
# Expected: 299 accepted, 0 missing rows/cells, 96 evaluator labels, PRD hash/stable IDs.

# COMMAND ----------
# TODO(DATA-01/DB-01): create approved tables from ../sql/001_tables.sql and publish:
# raw_clinical_records: cohort/source hash, patient ID, original row and raw JSON.
# patient_features: cohort ID, patient ID, source row and allowlisted features_json.
# evaluation_outcomes: target + follow-up days; restricted evaluator/training access.
# cohort_manifests: schema/hash, accepted/excluded IDs and cleaning counters/warnings.
# Use explicit Spark schemas and version-aware/idempotent writes; no duplicate cohort IDs.
# Never overwrite application_events or collect an unbounded dataset.
# Record actual grants; logical separation is not permission-enforced separation.

# COMMAND ----------
# TODO(EVIDENCE): save table names, run URL, hash, cleaning report and verified capabilities.
