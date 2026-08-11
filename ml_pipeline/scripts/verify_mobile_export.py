"""Verify mobile-export parity and fail a release below its quality gate."""

from __future__ import annotations

import json
import math
import pickle
import sys
from pathlib import Path

import numpy as np

sys.path.append(str(Path(__file__).resolve().parent.parent))
from config import settings


MIN_VALIDATION_MICRO_F1 = 0.70
MIN_HELD_OUT_TEST_MICRO_F1 = 0.60
MIN_SELECTED_LABELS = 3
MAX_HELD_OUT_REGRESSION = 0.02
BASELINE_METRICS_PATH_NAME = "baseline_metrics.json"


def _load_pickle() -> dict:
    with (settings.DATA_DIR / "clinical_observation_model.pkl").open("rb") as file:
        return pickle.load(file)


def _load_json(filename: str) -> dict:
    return json.loads((settings.DATA_DIR / "mobile_export" / filename).read_text(encoding="utf-8"))


def _char_wb_ngrams(text: str, minimum: int = 3, maximum: int = 6) -> list[str]:
    """Match scikit-learn's ``char_wb`` analyzer for ASCII/English text."""
    normalized = " ".join(text.lower().split())
    ngrams: list[str] = []
    for word in normalized.split(" "):
        padded = f" {word} "
        for size in range(minimum, min(maximum, len(padded)) + 1):
            ngrams.extend(
                padded[index : index + size]
                for index in range(len(padded) - size + 1)
            )
    return ngrams


def _sigmoid(value: float) -> float:
    if value >= 0:
        return 1 / (1 + math.exp(-value))
    exp_value = math.exp(value)
    return exp_value / (1 + exp_value)


def predict_export_probabilities(text: str, model: dict) -> list[float]:
    """Predict using only TF-IDF features from the exported model.

    This mirrors the Dart runtime inference path which uses TF-IDF only.
    The optional bert_projection field is NOT used here because the Dart
    runtime does not have a BERT model to generate embeddings.
    """
    counts: dict[int, int] = {}
    for token in _char_wb_ngrams(text):
        index = model["vocabulary"].get(token)
        if index is not None:
            counts[index] = counts.get(index, 0) + 1
    vector = {index: count * model["idf"][index] for index, count in counts.items()}
    norm = math.sqrt(sum(value * value for value in vector.values()))
    if norm:
        vector = {index: value / norm for index, value in vector.items()}
    probabilities: list[float] = []
    for intercept, coefficients in zip(model["intercept"], model["coef"]):
        score = float(intercept)
        for index, value in vector.items():
            score += coefficients[index] * value
        probabilities.append(_sigmoid(score))
    return probabilities


def _verify_export_parity() -> None:
    artifact = _load_pickle()
    exported = _load_json("observations.json")
    if exported.get("type") != "multi_label_sgd_classifier":
        raise AssertionError("Unexpected mobile model type")
    if exported.get("classes") != artifact["labels"]:
        raise AssertionError("Exported observation labels do not match the trained model")

    used_bert = artifact.get("used_bert", False)
    tfidf_dim = len(artifact["vectorizer"].vocabulary_)

    # Verify that the exported TF-IDF coefficients match the trained model.
    # When BERT was used, the trained estimators have combined features (TF-IDF + BERT);
    # the exported model only ships the TF-IDF portion of the coefficients.
    for est_idx, estimator in enumerate(artifact["estimators"]):
        exported_coef = exported["coef"][est_idx]
        if used_bert:
            trained_tfidf_coef = estimator.coef_[0, :tfidf_dim]
        else:
            trained_tfidf_coef = estimator.coef_[0]

        if len(exported_coef) != len(trained_tfidf_coef):
            raise AssertionError(
                f"Estimator {est_idx}: exported coef length {len(exported_coef)} "
                f"!= trained TF-IDF coef length {len(trained_tfidf_coef)}"
            )
        for j, (exp_val, train_val) in enumerate(zip(exported_coef, trained_tfidf_coef)):
            if not math.isclose(exp_val, train_val, rel_tol=1e-6, abs_tol=1e-6):
                raise AssertionError(
                    f"Estimator {est_idx}, coef {j}: "
                    f"exported {exp_val} != trained {train_val}"
                )

    # Verify that the TF-IDF-only inference path produces consistent results
    probes = [
        "Oxygen saturation is 83 percent on nasal cannula.",
        "The patient has dark, foul-smelling urine.",
        "Respirations are elevated while using accessory muscles.",
    ]
    for probe in probes:
        # Compute expected probabilities using only TF-IDF features
        features = artifact["vectorizer"].transform([probe])
        expected = []
        for estimator in artifact["estimators"]:
            positive_index = estimator.classes_.tolist().index(1)
            if used_bert:
                # For BERT-trained model, we need to provide zero BERT features
                # to get TF-IDF-only predictions. Instead, we directly compute
                # using the TF-IDF portion of the coefficients.
                tfidf_coef = estimator.coef_[0, :tfidf_dim]
                dense_features = features.toarray()[0]
                score = float(estimator.intercept_[0])
                for idx, val in enumerate(dense_features):
                    if val != 0:
                        score += tfidf_coef[idx] * val
                prob = 1 / (1 + math.exp(-score)) if score >= 0 else math.exp(score) / (1 + math.exp(score))
                expected.append(prob)
            else:
                expected.append(float(estimator.predict_proba(features)[0][positive_index]))

        actual = predict_export_probabilities(probe, exported)
        for expected_value, actual_value in zip(expected, actual):
            if not math.isclose(expected_value, actual_value, rel_tol=1e-6, abs_tol=1e-6):
                raise AssertionError(
                    f"Export mismatch for {probe!r}: {expected_value} != {actual_value}"
                )

    # Verify backward compatibility: bert_projection is optional
    if "bert_projection" in exported:
        proj = exported["bert_projection"]
        if not isinstance(proj, dict):
            raise AssertionError("bert_projection must be a dict")
        required_keys = {"pca_components", "pca_mean", "bert_coef", "embedding_dim", "reduced_dim"}
        missing = required_keys - set(proj.keys())
        if missing:
            raise AssertionError(f"bert_projection missing keys: {missing}")
        print(
            f"  BioClinicalBERT projection verified: "
            f"{proj['embedding_dim']} → {proj['reduced_dim']} dims"
        )


def _verify_quality_gate() -> None:
    metadata = _load_json("metadata.json")
    metrics = metadata.get("metrics", {})
    validation = metrics.get("validation", {})
    held_out = metrics.get("held_out_test", {})
    labels = metrics.get("selected_labels", [])
    if len(labels) < MIN_SELECTED_LABELS:
        raise AssertionError("Too few validated advisory observation labels")
    if validation.get("micro_f1", 0) < MIN_VALIDATION_MICRO_F1:
        raise AssertionError("Validation F1 is below the release quality gate")
    if held_out.get("micro_f1", 0) < MIN_HELD_OUT_TEST_MICRO_F1:
        raise AssertionError("Held-out SYNUR F1 is below the release quality gate")


def _verify_no_regression() -> None:
    baseline_path = settings.DATA_DIR / BASELINE_METRICS_PATH_NAME
    if not baseline_path.exists():
        print(
            f"No {BASELINE_METRICS_PATH_NAME} found at {baseline_path}; "
            "skipping regression check. This is expected only on the first "
            "release -- commit this run's metrics as the new baseline."
        )
        return

    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    current = _load_json("metadata.json").get("metrics", {})

    baseline_held_out = baseline.get("held_out_test", {}).get("micro_f1", 0.0)
    current_held_out = current.get("held_out_test", {}).get("micro_f1", 0.0)
    if current_held_out < baseline_held_out - MAX_HELD_OUT_REGRESSION:
        raise AssertionError(
            "Held-out micro_f1 regressed beyond tolerance: "
            f"baseline={baseline_held_out:.4f}, current={current_held_out:.4f}, "
            f"max_allowed_drop={MAX_HELD_OUT_REGRESSION}"
        )

    baseline_labels = set(baseline.get("selected_labels", []))
    current_labels = set(current.get("selected_labels", []))
    if len(current_labels) < len(baseline_labels):
        raise AssertionError(
            "Number of validated advisory labels dropped: "
            f"baseline={len(baseline_labels)}, current={len(current_labels)}"
        )


if __name__ == "__main__":
    _verify_export_parity()
    _verify_quality_gate()
    _verify_no_regression()
    print("Mobile observation export matches the trained model and passed quality gates.")
