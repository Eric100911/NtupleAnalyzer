#!/usr/bin/env python3
"""Bounded feature, event partition and saved training-history regression tests."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.templates.train_full_correlation_xgboost import (
    CLASS_ORDER, FEATURE_NAMES, feature_frame, partition_for, weighted_frame, train_variant, selected_features,
)


class FullFeatureTests(unittest.TestCase):
    def test_actual_feature_exclusion(self):
        names=selected_features(['phi_pt'])
        self.assertEqual(len(names),21);self.assertNotIn('phi_pt',names);self.assertNotIn('phi_y',FEATURE_NAMES)
        self.assertEqual(names,FEATURE_NAMES[:-1])
        with self.assertRaises(ValueError):selected_features(['phi_y'])
    def test_ordering_nominal_mass_and_genuine_phi_y(self):
        p = np.array([[[7., 1., 4.], [11., -2., -8.], [5., .2, 9.]]])
        masses = np.array([[3.05, 3.15, 1.02]])
        frame = feature_frame(p, masses)
        swapped = feature_frame(p[:, [1, 0, 2]], masses[:, [1, 0, 2]])
        np.testing.assert_allclose(frame, swapped)
        changed = feature_frame(p, np.array([[2.9, 3.3, 1.07]]))
        np.testing.assert_array_equal(frame[list(FEATURE_NAMES)], changed[list(FEATURE_NAMES)])
        self.assertNotEqual(frame.phi_y.iloc[0], changed.phi_y.iloc[0])
        self.assertEqual(len(FEATURE_NAMES), 22)
        self.assertGreater(frame.jpsi1_pt.iloc[0], frame.jpsi2_pt.iloc[0])
        expected = np.arcsinh(9. / np.sqrt(25. + .04 + 1.02**2))
        self.assertAlmostEqual(frame.phi_y.iloc[0], expected)

    def test_phi_wrapping_and_rejected_invalid_momentum(self):
        p = np.array([[[-10., .01, 0.], [-8., -.01, 0.], [5., 0., 0.]]])
        f = feature_frame(p, np.array([[3.1, 3.1, 1.02]]))
        self.assertLess(f.dphi_jj.iloc[0], .01)
        p[0, 0, 0] = np.nan
        with self.assertRaises(ValueError):
            feature_frame(p, np.array([[3.1, 3.1, 1.02]]))

    def test_partition_event_identity(self):
        original = {i: partition_for("DPS1", "/tmp/a.root", i, 10) for i in range(1000)}
        reordered = {i: partition_for("DPS1", "/tmp/a.root", i, 10) for i in reversed(range(1000))}
        self.assertEqual(original, reordered)
        self.assertEqual(set(original.values()), {"training", "development", "templates", "final_validation"})

    def test_weights_and_saved_histories(self):
        rng = np.random.default_rng(8)
        frames = []
        for label, name in enumerate(CLASS_ORDER):
            p = rng.normal(0., 8., size=(60, 3, 3))
            f = feature_frame(p, np.broadcast_to([3.1, 3.1, 1.02], (60, 3)))
            f["label"], f["sample"] = label, name
            f["source_file"], f["entry"] = f"/tmp/{name}.root", np.arange(60)
            f["partition"] = np.repeat(["training", "development", "templates", "final_validation"], [24, 9, 15, 12])
            f["input_weight"], f["gen_weight"] = label + 1., 1.
            frames.append(f)
        f = pd.concat(frames, ignore_index=True)
        shape_weights = np.linspace(.2, 2., len(f))
        weighted = weighted_frame(f, shape_weights)
        training = weighted[weighted.partition == "training"]
        self.assertAlmostEqual(training.training_weight.mean(), 1.)
        np.testing.assert_allclose(training.groupby("sample").training_weight.sum(), len(training) / 6)
        self.assertTrue((weighted.base_weight > 0).all())
        with tempfile.TemporaryDirectory(prefix="full_feature_test_") as tmp:
            output = Path(tmp) / "model"
            names=selected_features(['phi_pt'])
            train_variant(weighted, output, n_estimators=8, depths=(2, 3), jobs=1, early_stopping_rounds=2,feature_names=names)
            frozen = json.loads((output / "frozen_study.json").read_text())
            self.assertEqual(frozen["saved_model_max_prediction_difference"], 0.)
            for depth in (2, 3):
                progress = json.loads((output / f"candidate_depth{depth}_training_progress.json").read_text())
                self.assertEqual(progress["attempted_rounds"], len(progress["history"]["validation_0"]["mlogloss"]))
                self.assertEqual(progress["attempted_rounds"], len(progress["history"]["validation_1"]["mlogloss"]))
                self.assertGreaterEqual(progress["attempted_rounds"], progress["saved_rounds"])
                self.assertEqual(progress["early_stopping_monitored_dataset"], "validation_1")
            scores = np.load(output / "final_validation_scores.npz")
            np.testing.assert_array_equal(scores["class_order"][scores["labels"]], scores["sample"])
            self.assertEqual(scores["features"].shape[1],21)
            self.assertEqual(scores['feature_names'].tolist(),list(names))
            self.assertEqual(frozen['feature_names'],list(names))
            self.assertIn('phi_y',scores.files)
            self.assertTrue((output / "learning_curves.png").exists())
            with self.assertRaises(FileExistsError):
                train_variant(weighted, output, n_estimators=2, depths=(2,), jobs=1)


if __name__ == "__main__":
    unittest.main()
