"""Check experiment isolation and development-only threshold selection with tiny grids.

Run with the ML extra installed. The full notebook validates the larger default grids;
these tests keep only one candidate/family to check the held-out-data boundary quickly.
"""

import copy
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from hf_followup.config import ROOT
from hf_followup.data.ingest import ingest_csv
from hf_followup.ml.experiments import choose_family, development_f1_threshold, run_experiments
from hf_followup.ml.training import fixed_split


class ExperimentIsolationTests(unittest.TestCase):
    def test_selection_prioritizes_fewer_fn_then_more_tn(self):
        searches = {
            name: SimpleNamespace(
                best_score_=0.5, best_index_=0, cv_results_={"mean_test_roc_auc": [auc]}
            )
            for name, auc in [
                ("logistic_regression", 0.9),
                ("random_forest", 0.8),
                ("gradient_boosting", 0.7),
            ]
        }
        development = {
            "logistic_regression": {"counts": {"fn": 3, "tn": 100, "tp": 7, "fp": 0}},
            "random_forest": {"counts": {"fn": 2, "tn": 10, "tp": 8, "fp": 90}},
            "gradient_boosting": {"counts": {"fn": 2, "tn": 20, "tp": 8, "fp": 80}},
        }
        self.assertEqual(
            choose_family(searches, development, "min_false_negatives"), "gradient_boosting"
        )
        development["random_forest"]["counts"].update(fn=1, tp=9)
        self.assertEqual(
            choose_family(searches, development, "min_false_negatives"), "random_forest"
        )

    def test_threshold_finds_positive_f1_and_prefers_higher_ties(self):
        self.assertEqual(
            development_f1_threshold([0, 1, 1, 0], np.array([0.1, 0.3, 0.4, 0.2])), 0.3
        )
        self.assertEqual(development_f1_threshold([1, 0], np.array([0.7, 0.3])), 0.7)

    def test_test_labels_cannot_change_selection_thresholds_bands_or_scores(self):
        ingestion = ingest_csv(ROOT / "data/heart_failure_clinical_records.csv")
        split = fixed_split(ingestion.cohort, ingestion.outcomes)
        altered = copy.deepcopy(ingestion.outcomes)
        for pid in split["test_ids"]:
            altered[pid]["DEATH_EVENT"] = 1 - altered[pid]["DEATH_EVENT"]
        # Freeze the original split: only held-out labels change, never development labels.
        grids = {
            "logistic_regression": {"model__C": [1.0]},
            "random_forest": {"model__n_estimators": [5], "model__max_depth": [2]},
            "gradient_boosting": {"model__n_estimators": [5], "model__max_depth": [1]},
        }
        with (
            tempfile.TemporaryDirectory() as folder,
            patch("hf_followup.ml.experiments.fixed_split", return_value=split),
        ):
            first = run_experiments(
                ingestion,
                Path(folder) / "original",
                param_grids=grids,
                refit_metric="f1_positive",
                selection_policy="min_false_negatives",
            )
            second = run_experiments(
                replace(ingestion, outcomes=altered),
                Path(folder) / "altered",
                param_grids=grids,
                refit_metric="f1_positive",
                selection_policy="min_false_negatives",
            )
        self.assertEqual(first["report"]["cv_fit_count"], 45)
        self.assertEqual(first["report"]["refit_metric"], "f1_positive")
        self.assertEqual(first["selected_thresholds"], second["selected_thresholds"])
        np.testing.assert_array_equal(first["predictions"], second["predictions"])
        for task, original in first["report"]["tasks"].items():
            changed = second["report"]["tasks"][task]
            self.assertEqual(original["selected_family"], changed["selected_family"])
            self.assertEqual(original["band_cutoffs"], changed["band_cutoffs"])
            for family, model in original["models"].items():
                other = changed["models"][family]
                for key in (
                    "best_params",
                    "best_cv_score",
                    "cv_results",
                    "development_threshold",
                    "development_oof",
                ):
                    self.assertEqual(model[key], other[key])
                self.assertEqual(
                    model["best_cv_score"], model["cv_results"][0]["mean_test_f1_positive"]
                )
                self.assertNotEqual(model["confusion_matrix"], other["confusion_matrix"])
