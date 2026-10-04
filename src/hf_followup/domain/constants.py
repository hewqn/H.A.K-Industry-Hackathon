"""Versioned PRD contracts; change versions when thresholds, fields, or ties change."""

COHORT_ID = "uci-hf-299-v1"
SOURCE_HASH = "9c73cea7468ff5d517801ec050fe9993da5912fce4b56f296f8df3b38dd75912"
SCHEMA_VERSION = "patient-features-v1"
TIE_POLICY = "sha256-patient-source-row-v1"
INDICATOR_POLICY = "organ-indicators-v1"
POINTS_POLICY = "points-policy-v1"
FEATURES = (
    "age",
    "anaemia",
    "creatinine_phosphokinase",
    "diabetes",
    "ejection_fraction",
    "high_blood_pressure",
    "platelets",
    "serum_creatinine",
    "serum_sodium",
    "sex",
    "smoking",
)
BINARY_FIELDS = {"anaemia", "diabetes", "high_blood_pressure", "sex", "smoking"}
EVALUATION_FIELDS = ("time", "DEATH_EVENT")
METHODS = ("oldest_first", "points_v1", "points_heart3")
UNITS = {
    "age": "years",
    "ejection_fraction": "%",
    "serum_creatinine": "mg/dL",
    "serum_sodium": "mEq/L",
    "creatinine_phosphokinase": "mcg/L",
}
