"""Shared fixed split, pipeline construction and frozen-selection training.

Training/evaluation are explicit commands. Application interactions consume a frozen
prediction cache and never fit a model. configs/ml_selection.json freezes the user's
chosen families/parameters/thresholds for reproducible development-only refitting.
"""

import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from hf_followup.domain.constants import FEATURES

SEED = 42
ALPHA = 25 / 299


def training_frame(cohort, outcomes):
    # Exactly the predictor allowlist: time/DEATH_EVENT are never features.
    ids = list(cohort.features)
    x = pd.DataFrame(
        [cohort.features[pid]["facts"] for pid in ids], index=ids, columns=FEATURES
    ).astype(float)
    y = pd.Series([outcomes[pid]["DEATH_EVENT"] for pid in ids], index=ids)
    return x, y


def fixed_split(cohort, outcomes):
    x, y = training_frame(cohort, outcomes)
    development, test = train_test_split(
        list(x.index), test_size=0.2, random_state=SEED, stratify=y
    )
    return {
        "split_version": "stratified-80-20-seed42-v1",
        "seed": SEED,
        "source_hash": cohort.manifest["source_hash"],
        "development_ids": development,
        "test_ids": test,
    }


def candidate_pipelines():
    # Learned scaling stays in the pipeline and is fitted only inside each training fold.
    return {
        "logistic_regression": Pipeline(
            [
                ("scale", StandardScaler()),
                ("model", LogisticRegression(C=1, max_iter=2000, random_state=SEED)),
            ]
        ),
        "random_forest": Pipeline(
            [
                (
                    "model",
                    RandomForestClassifier(
                        n_estimators=150,
                        max_depth=4,
                        min_samples_leaf=5,
                        random_state=SEED,
                        n_jobs=1,
                    ),
                )
            ]
        ),
    }


def development_folds():
    return StratifiedKFold(n_splits=5, shuffle=True, random_state=SEED)


# TODO(ML-01): evaluate both candidates and age/points references on identical fold IDs.
# K_eval = ceil((25/299)*N); report precision/capture/lift, ROC-AUC, AP, Brier and variability.
# TODO(ML-02): select on development CV only, freeze, refit on 239 development patients,
# evaluate once on 60 test patients (K=6), and publish reproducible artifacts to MLflow.
# Logistic explanation = scaled value * fitted coefficient in log-odds + intercept.
# Forest P0 explanation = recorded indicators; local attribution unavailable.
# Publish full-cohort scores with development_in_sample / held_out_test provenance.


def train_frozen_selection(ingestion, selection: dict, output):
    """Refit the agreed three configurations; no parameter search or family reselection.

    The frozen source hash prevents carrying thresholds across an unreviewed dataset.
    OOF verification confirms the saved thresholds/bands still match their lineage.
    """
    import platform

    import joblib
    import numpy as np
    import sklearn
    from sklearn.base import clone
    from sklearn.ensemble import GradientBoostingClassifier
    from sklearn.model_selection import cross_val_predict

    from hf_followup.domain.predictions import RISK_TASKS
    from hf_followup.ml.experiments import classification_metrics, preprocessor, ranking_metrics
    from hf_followup.ml.publishing import write_json

    if (
        selection["schema_version"] != "frozen-risk-selection-v1"
        or selection["source_hash"] != ingestion.cohort.manifest["source_hash"]
    ):
        raise ValueError("Frozen selection does not match the validated source dataset")
    if set(selection["models"]) != set(RISK_TASKS):
        raise ValueError("Frozen selection must contain all three outputs")
    output.mkdir(parents=True, exist_ok=True)
    x, y = training_frame(ingestion.cohort, ingestion.outcomes)
    split = fixed_split(ingestion.cohort, ingestion.outcomes)
    dev, test = split["development_ids"], split["test_ids"]
    constructors = {
        "logistic_regression": lambda: LogisticRegression(max_iter=2000, random_state=SEED),
        "random_forest": lambda: RandomForestClassifier(
            n_estimators=150, random_state=SEED, n_jobs=1
        ),
        "gradient_boosting": lambda: GradientBoostingClassifier(random_state=SEED, subsample=0.8),
    }
    report = {
        "target": "DEATH_EVENT",
        "source_hash": selection["source_hash"],
        "cleaning": ingestion.cohort.manifest,
        "split": split,
        "feature_groups": {task: model["features"] for task, model in selection["models"].items()},
        "feature_group_version": selection["feature_group_version"],
        "refit_metric": "frozen_parameters",
        "selection_policy": "frozen_family_and_thresholds",
        "selection": "Refit previously selected configurations, thresholds and bands without reselection. Original policy: "
        + selection["selection"],
        "versions": {
            "python": platform.python_version(),
            "sklearn": sklearn.__version__,
            "pandas": pd.__version__,
            "numpy": np.__version__,
            "joblib": joblib.__version__,
        },
        "limitations": selection["limitations"],
        "cv_fit_count": 15,
        "tasks": {},
    }
    for task, config in selection["models"].items():
        fields, family = config["features"], config["family"]
        if not fields or len(set(fields)) != len(fields) or not set(fields).issubset(FEATURES):
            raise ValueError(f"Invalid frozen baseline features: {task}")
        pipeline = Pipeline(
            [
                ("preprocessor", preprocessor(fields, family == "logistic_regression")),
                ("model", constructors[family]()),
            ]
        )
        pipeline.set_params(**config["params"])
        xd, yd = x.loc[dev, fields], y.loc[dev]
        pipeline.fit(xd, yd)
        oof = cross_val_predict(
            clone(pipeline), xd, yd, cv=development_folds(), method="predict_proba", n_jobs=1
        )[:, 1]
        np.testing.assert_allclose(
            np.quantile(oof, [1 / 3, 2 / 3]),
            [config["band_cutoffs"][name] for name in ("lower_max", "middle_max")],
            atol=1e-8,
            rtol=0,
        )
        threshold = config["classification_threshold"]
        development = classification_metrics(yd, oof >= threshold)
        if development["counts"] != config["development_counts"]:
            raise ValueError(f"Frozen threshold no longer reproduces development counts: {task}")
        scores = pipeline.predict_proba(x.loc[test, fields])[:, 1]
        from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score

        selected_cv = config["selected_cv_result"]
        model_report = {
            "best_params": config["params"],
            "best_cv_score": selected_cv["mean_test_f1_positive"],
            "best_cv_capture": selected_cv["mean_test_capture_at_k"],
            "cv_results": [selected_cv],
            "cv_result_source": "previous_frozen_development_search",
            "candidate_count": 1,
            **classification_metrics(y.loc[test], scores >= 0.5),
            "development_threshold": threshold,
            "threshold_policy": "development_oof_positive_f1_v1",
            "development_oof": development,
            "thresholded": classification_metrics(y.loc[test], scores >= threshold),
            "test": {
                **ranking_metrics(y.loc[test], scores, test),
                "roc_auc": float(roc_auc_score(y.loc[test], scores)),
                "average_precision": float(average_precision_score(y.loc[test], scores)),
                "brier": float(brier_score_loss(y.loc[test], scores)),
            },
        }
        report["tasks"][task] = {
            "selected_family": family,
            "selected_threshold": threshold,
            "selection_development_counts": development["counts"],
            "models": {family: model_report},
            "band_cutoffs": config["band_cutoffs"],
            "band_policy": "development_oof_tertiles_v1",
            "score_kind": "model_output",
            "calibration_status": "not_calibrated",
            "features": fields,
        }
        joblib.dump(pipeline, output / f"{task}_pipeline.joblib")
        print(f"Refit {task}: {family}; threshold={threshold:.6f}", flush=True)
    write_json(output / "split_manifest.json", split)
    write_json(output / "experiment_report.json", report)
    return report
