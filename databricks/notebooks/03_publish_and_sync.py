# Databricks notebook source
# MAGIC %md
# MAGIC # Publish and synchronize — backend + ML owners
# MAGIC Populate after training/capability checks. No writes run by default.

# COMMAND ----------
# TODO(ML-02/DB-01): load the frozen pipeline by immutable MLflow run/model version.
# Score FEATURES only in saved feature order. Publish model_predictions with cohort,
# patient/model IDs, version, score/kind, actual attribution scale and prediction
# provenance (development_in_sample / held_out_test). Never silently use "latest".
# Publish labelled evaluation_reports + checksummed feature/prediction/report exports.

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
