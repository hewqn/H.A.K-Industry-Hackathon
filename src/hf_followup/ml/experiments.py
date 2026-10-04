"""Small three-output experiment; organ-feature models predict DEATH_EVENT, not organ failure.

Risk names are integration keys. Scores are uncalibrated historical-outcome model
outputs; bands are relative development-score thirds, not clinical disease grades.
The patient model learns from all baseline features rather than averaging correlated,
uncalibrated organ scores. The external example notebook is a style reference only.
"""

import hashlib
import json
import math
import platform
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.base import clone
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    classification_report,
    confusion_matrix,
    f1_score,
    roc_auc_score,
)
from sklearn.model_selection import GridSearchCV, ParameterGrid, cross_val_predict
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from hf_followup.domain.constants import BINARY_FIELDS, FEATURES
from hf_followup.ml.training import ALPHA, SEED, development_folds, fixed_split, training_frame

# Literature-informed candidate groups, not clinically validated feature selection.
# Rationale and primary AHA/NHLBI/NIDDK/NKF sources: docs/feature-selection.md.
# Creatinine interpretation depends on age/sex; diabetes/BP/smoking are renal risk context.
# Sodium and anaemia are nonspecific for kidney function, so exclude them from that group.
# Total CPK is not heart-specific (the dataset has no CK-MB); leave it in patient only.
FEATURE_GROUP_VERSION = "organ-feature-groups-v2"
GROUPS = {
    "heart_risk": [
        "ejection_fraction",
        "age",
        "high_blood_pressure",
        "diabetes",
        "smoking",
        "anaemia",
    ],
    "kidney_risk": [
        "serum_creatinine",
        "age",
        "sex",
        "diabetes",
        "high_blood_pressure",
        "smoking",
    ],
    "patient_risk": list(FEATURES),
}


def preprocessor(fields, scale):
    # Already-clean binary fields pass through; numeric scaling is learned in each fold.
    # No one-hot encoder: the supplied categories are already validated binary flags.
    numeric = [field for field in fields if field not in BINARY_FIELDS]
    binary = [field for field in fields if field in BINARY_FIELDS]
    return ColumnTransformer(
        [
            ("numeric", StandardScaler() if scale else "passthrough", numeric),
            ("binary", "passthrough", binary),
        ],
        remainder="drop",
    )


def ranking_metrics(y, scores, ids):
    k = min(len(y), math.ceil(ALPHA * len(y)))
    # IDs retain original source rows; never use outcomes or follow-up time to break ties.
    order = sorted(
        range(len(y)),
        key=lambda i: (
            -float(scores[i]),
            hashlib.sha256(f"patient-{int(ids[i].split('-')[1])}".encode()).hexdigest(),
            ids[i],
        ),
    )
    labels = np.asarray(y, dtype=int)
    captured = int(labels[order[:k]].sum())
    precision = captured / k
    prevalence = float(labels.mean())
    return {
        "n": len(y),
        "k": k,
        "captured_outcomes": captured,
        "precision_at_k": precision,
        "capture_at_k": captured / int(labels.sum()) if labels.sum() else 0,
        "lift": precision / prevalence if prevalence else None,
    }


def capture_scorer(estimator, x, y):
    return ranking_metrics(y, estimator.predict_proba(x)[:, 1], list(x.index))["capture_at_k"]


# Explicit bounded grids: vary regularization, tree capacity and class weighting.
# 50 candidates/output x five folds = 750 CV fits across all three outputs.
# More trees mainly stabilize forests; fix 150 and tune capacity instead.
PARAM_GRIDS = {
    "logistic_regression": {
        "model__C": [0.01, 0.1, 1.0, 10.0, 100.0],
        "model__class_weight": [None, "balanced"],
    },
    "random_forest": {
        "model__max_depth": [4, 8, None],
        "model__min_samples_leaf": [1, 5],
        "model__max_features": ["sqrt", 1.0],
        "model__class_weight": [None, "balanced"],
    },
    "gradient_boosting": {
        "model__n_estimators": [100, 200],
        "model__learning_rate": [0.05, 0.1],
        "model__max_depth": [1, 2],
        "model__min_samples_leaf": [3, 8],
    },
}
REFIT_METRICS = {"capture_at_k", "average_precision", "roc_auc", "f1_positive", "f1_weighted"}


def development_f1_threshold(y, scores):
    """Choose a classification threshold using development OOF predictions only.

    This improves the precision/recall tradeoff, not score ranking or calibration.
    OOF predictions are conditional on selected hyperparameters (not nested CV).
    Prefer the higher threshold on exact F1 ties to limit unnecessary positives.
    """
    candidates = np.unique(np.r_[0.5, scores])
    return float(max(candidates, key=lambda t: (f1_score(y, scores >= t), t)))


def classification_metrics(y, predicted):
    tn, fp, fn, tp = map(int, confusion_matrix(y, predicted, labels=[0, 1]).ravel())
    return {
        "counts": {"tn": tn, "fp": fp, "fn": fn, "tp": tp},
        "classification_report": classification_report(
            y,
            predicted,
            labels=[0, 1],
            target_names=["no_recorded_death", "recorded_death"],
            output_dict=True,
            zero_division=0,
        ),
        "confusion_matrix": confusion_matrix(y, predicted, labels=[0, 1]).tolist(),
    }


def choose_family(searches, development, selection_policy):
    """Select before test evaluation; all families use identical development patients.

    Thresholds are F1-tuned on development OOF scores first. Among those operating
    points, fewer FN means more TP; TN breaks ties (equivalently fewer FP).
    Never optimize FN alone over arbitrary thresholds: that predicts everyone positive.
    """
    families = list(searches)

    def key(name):
        search = searches[name]
        auc = float(search.cv_results_["mean_test_roc_auc"][search.best_index_])
        if selection_policy == "min_false_negatives":
            counts = development[name]["counts"]
            return (-counts["fn"], counts["tn"], counts["tp"], auc, -families.index(name))
        return (search.best_score_, auc, -families.index(name))

    return max(families, key=key)


def run_experiments(
    ingestion,
    output: Path,
    *,
    feature_groups: dict | None = None,
    param_grids: dict | None = None,
    refit_metric: str = "capture_at_k",
    selection_policy: str = "cv_metric",
):
    """Tune three families on development only; keep classification/ranking separate."""
    if selection_policy not in {"cv_metric", "min_false_negatives"}:
        raise ValueError("selection_policy must be cv_metric or min_false_negatives")
    if refit_metric not in REFIT_METRICS:
        raise ValueError(f"refit_metric must be one of {sorted(REFIT_METRICS)}")
    grids = PARAM_GRIDS if param_grids is None else param_grids
    if set(grids) != set(PARAM_GRIDS):
        raise ValueError("Provide grids for logistic_regression, random_forest, gradient_boosting.")
    output.mkdir(parents=True, exist_ok=True)
    x, y = training_frame(ingestion.cohort, ingestion.outcomes)
    # Notebook lists are the actual experiment inputs, not merely display labels.
    groups = {
        name: list(fields)
        for name, fields in (GROUPS if feature_groups is None else feature_groups).items()
    }
    if set(groups) != set(GROUPS) or any(
        not fields or len(fields) != len(set(fields)) or not set(fields).issubset(FEATURES)
        for fields in groups.values()
    ):
        raise ValueError(
            "Provide the three risk groups with nonempty, unique baseline-feature lists; no time/DEATH_EVENT."
        )
    version = (
        FEATURE_GROUP_VERSION
        if groups == GROUPS
        else "notebook-custom-"
        + hashlib.sha256(json.dumps(groups, sort_keys=True).encode()).hexdigest()[:12]
    )
    split = fixed_split(ingestion.cohort, ingestion.outcomes)
    dev, test = split["development_ids"], split["test_ids"]
    report = {
        "target": "DEATH_EVENT",
        "source_hash": ingestion.cohort.manifest["source_hash"],
        "cleaning": ingestion.cohort.manifest,
        "split": split,
        "feature_groups": groups,
        "feature_group_version": version,
        "refit_metric": refit_metric,
        "selection_policy": selection_policy,
        "selection": (
            f"Parameters: development five-fold mean {refit_metric}. "
            + (
                "Family: fewest development OOF FN at development-F1-tuned thresholds, then most TN/TP, then CV AUC and simpler family. "
                if selection_policy == "min_false_negatives"
                else "Family: highest CV objective, then CV AUC and simpler family. "
            )
            + "Test never selects parameters, family or threshold."
        ),
        "param_grids": grids,
        "cv_fit_count": 3 * 5 * sum(len(ParameterGrid(grid)) for grid in grids.values()),
        "versions": {
            "python": platform.python_version(),
            "sklearn": sklearn.__version__,
            "joblib": joblib.__version__,
            "pandas": pd.__version__,
            "numpy": np.__version__,
        },
        "limitations": [
            "No organ-specific outcome labels: heart/kidney models are feature-associated mortality proxies.",
            "No fixed prediction horizon or calibrated clinical probability.",
            "Relative bands use development OOF-score thirds, conditional on hyperparameter selection; not independent validation.",
            "Full-cohort outputs mix development in-sample and held-out test scores.",
            "Repeated inspection of the same test set makes later comparisons exploratory.",
            "Classification thresholds maximize development OOF positive-class F1 conditional on hyperparameter selection; need fresh validation.",
        ],
        "tasks": {},
    }
    predictions = pd.DataFrame(index=x.index)
    predictions.index.name = "patient_id"
    searches, selected = {}, {}
    for task, fields in groups.items():
        xd, xt = x.loc[dev, fields], x.loc[test, fields]
        yd, yt = y.loc[dev], y.loc[test]
        specs = {
            "logistic_regression": LogisticRegression(max_iter=2000, random_state=SEED),
            "random_forest": RandomForestClassifier(n_estimators=150, random_state=SEED, n_jobs=1),
            "gradient_boosting": GradientBoostingClassifier(random_state=SEED, subsample=0.8),
        }
        searches[task] = {}
        for family, model in specs.items():
            grid = grids[family]
            print(f"{task} / {family}: {len(ParameterGrid(grid))} candidates x 5 folds", flush=True)
            pipeline = Pipeline(
                [
                    ("preprocessor", preprocessor(fields, family == "logistic_regression")),
                    ("model", model),
                ]
            )
            # GridSearchCV.fit fits every fold and refits best_estimator_ on development.
            search = GridSearchCV(
                pipeline,
                grid,
                cv=development_folds(),
                scoring={
                    "capture_at_k": capture_scorer,
                    "roc_auc": "roc_auc",
                    "f1_weighted": "f1_weighted",
                    "f1_positive": "f1",
                    "average_precision": "average_precision",
                    "recall_positive": "recall",
                },
                refit=refit_metric,
                n_jobs=1,
                error_score="raise",
            )
            search.fit(xd, yd)
            searches[task][family] = search
        # Establish every development operating point before looking at test outcomes.
        oof_by_family, thresholds, development = {}, {}, {}
        for family, search in searches[task].items():
            oof = cross_val_predict(
                clone(search.best_estimator_),
                xd,
                yd,
                cv=development_folds(),
                method="predict_proba",
                n_jobs=1,
            )[:, 1]
            oof_by_family[family] = oof
            thresholds[family] = development_f1_threshold(yd, oof)
            development[family] = classification_metrics(yd, oof >= thresholds[family])
        winner_name = choose_family(searches[task], development, selection_policy)
        # Freeze both family and classification threshold before any test evaluation.
        winner = searches[task][winner_name].best_estimator_
        selected[task] = winner
        task_report = {
            "selected_family": winner_name,
            "selected_threshold": thresholds[winner_name],
            "selection_development_counts": development[winner_name]["counts"],
            "models": {},
        }
        for family, search in searches[task].items():
            estimator = search.best_estimator_
            threshold = thresholds[family]
            scores = estimator.predict_proba(xt)[:, 1]
            task_report["models"][family] = {
                "best_params": search.best_params_,
                "best_cv_score": float(search.best_score_),
                "best_cv_capture": float(
                    search.cv_results_["mean_test_capture_at_k"][search.best_index_]
                ),
                "candidate_count": len(search.cv_results_["params"]),
                "cv_results": pd.DataFrame(search.cv_results_)[
                    [
                        "params",
                        "mean_test_capture_at_k",
                        "std_test_capture_at_k",
                        "mean_test_roc_auc",
                        "mean_test_average_precision",
                        "mean_test_f1_positive",
                        "mean_test_recall_positive",
                        "mean_test_f1_weighted",
                    ]
                ].to_dict(orient="records"),
                # Preserve existing keys for the default 0.5 reports.
                **classification_metrics(yt, scores >= 0.5),
                "development_threshold": threshold,
                "threshold_policy": "development_oof_positive_f1_v1",
                "development_oof": development[family],
                "thresholded": classification_metrics(yt, scores >= threshold),
                "test": {
                    **ranking_metrics(yt, scores, test),
                    "roc_auc": float(roc_auc_score(yt, scores)),
                    "average_precision": float(average_precision_score(yt, scores)),
                    "brier": float(brier_score_loss(yt, scores)),
                },
            }
        # Band cutoffs use development only; the test set cannot choose the cutoffs.
        oof = oof_by_family[winner_name]
        lower, upper = map(float, np.quantile(oof, [1 / 3, 2 / 3]))
        all_scores = winner.predict_proba(x[fields])[:, 1]
        predictions[task] = all_scores
        predictions[f"{task}_band"] = np.where(
            all_scores <= lower, "lower", np.where(all_scores <= upper, "middle", "higher")
        )
        task_report.update(
            band_cutoffs={"lower_max": lower, "middle_max": upper},
            band_policy="development_oof_tertiles_v1",
            score_kind="model_output",
            calibration_status="not_calibrated",
            features=fields,
        )
        report["tasks"][task] = task_report
        joblib.dump(
            winner, output / f"{task}_pipeline.joblib"
        )  # Only load this trusted team-created artifact.
        assert np.allclose(
            all_scores,
            joblib.load(output / f"{task}_pipeline.joblib").predict_proba(x[fields])[:, 1],
            atol=1e-12,
            rtol=0,
        )
    predictions["prediction_provenance"] = [
        "held_out_test" if pid in test else "development_in_sample" for pid in x.index
    ]
    # Keep measurement-driven visual indicators separate from model-based relative bands.
    predictions["heart_measurement_indicator"] = np.where(
        x.ejection_fraction < 35, "threshold_crossed", "threshold_not_crossed"
    )
    predictions["kidney_measurement_indicator"] = np.where(
        x.serum_creatinine > 1.5, "threshold_crossed", "threshold_not_crossed"
    )
    predictions["score_kind"] = "uncalibrated_outcome_model_output"
    predictions.to_csv(output / "risk_outputs.csv")  # No time/DEATH_EVENT columns.
    (output / "experiment_report.json").write_text(
        json.dumps(report, indent=2, allow_nan=False) + "\n"
    )
    (output / "split_manifest.json").write_text(json.dumps(split, indent=2) + "\n")
    return {
        "report": report,
        "predictions": predictions,
        "searches": searches,
        "selected_models": selected,
        "selected_thresholds": {
            task: task_report["selected_threshold"] for task, task_report in report["tasks"].items()
        },
    }
