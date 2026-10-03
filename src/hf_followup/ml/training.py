"""ML owner's entry points, not a trained model or a completed experiment.

The fixed split and candidate pipeline constructors are provided. The owner implements
fold evaluation, bounded candidate selection, final test, MLflow logging, and exports
in the notebook. Never train or inspect outcomes during a frontend interaction.
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
