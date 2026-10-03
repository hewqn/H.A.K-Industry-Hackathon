-- Review catalog/schema permissions first. Substitute the approved namespace only.
-- This script is a reference; 01_ingest.py creates the same schema programmatically.
-- Never grant the app access to raw records or evaluation outcomes.
CREATE TABLE IF NOT EXISTS ${catalog}.${schema}.raw_clinical_records
  (cohort_id STRING, patient_id STRING, source_row BIGINT, source_hash STRING, raw_json STRING) USING DELTA;
CREATE TABLE IF NOT EXISTS ${catalog}.${schema}.patient_features
  (cohort_id STRING, patient_id STRING, source_row BIGINT, features_json STRING) USING DELTA;
CREATE TABLE IF NOT EXISTS ${catalog}.${schema}.evaluation_outcomes
  (cohort_id STRING, patient_id STRING, DEATH_EVENT BIGINT, follow_up_days DOUBLE) USING DELTA;
CREATE TABLE IF NOT EXISTS ${catalog}.${schema}.cohort_manifests
  (cohort_id STRING, source_hash STRING, manifest_json STRING) USING DELTA;
CREATE TABLE IF NOT EXISTS ${catalog}.${schema}.model_predictions
  (cohort_id STRING, model_id STRING, patient_id STRING, model_version STRING, score DOUBLE, prediction_json STRING, model_metadata_json STRING) USING DELTA;
CREATE TABLE IF NOT EXISTS ${catalog}.${schema}.evaluation_reports
  (cohort_id STRING, report_id STRING, report_kind STRING, report_json STRING) USING DELTA;
CREATE TABLE IF NOT EXISTS ${catalog}.${schema}.application_events
  (command_id STRING, session_id STRING, revision BIGINT, expected_revision BIGINT, command_digest STRING, payload_json STRING, created_at STRING) USING DELTA;
CREATE TABLE IF NOT EXISTS ${catalog}.${schema}.summary_cache
  (cache_key STRING, patient_id STRING, evidence_digest STRING, payload_json STRING) USING DELTA;
-- Delta uniqueness is enforced by the application protocol, not these table definitions.
-- Owner must supply actual grants for separate evaluator and app identities if permitted.
