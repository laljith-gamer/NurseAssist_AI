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


MIN_VALIDATION_MICRO_F1 = settings.MIN_VALIDATION_MICRO_F1
MIN_HELD_OUT_TEST_MICRO_F1 = settings.MIN_HELD_OUT_TEST_MICRO_F1
MIN_SELECTED_LABELS = settings.MIN_SELECTED_LABELS
MAX_HELD_OUT_REGRESSION = settings.MAX_HELD_OUT_REGRESSION
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


def relu(x: np.ndarray) -> np.ndarray:
    return np.maximum(0, x)


def sigmoid(x: np.ndarray) -> np.ndarray:
    return 1 / (1 + np.exp(-x))


def predict_export_probabilities(text: str, model: dict) -> list[float]:
    """Predict using the exported MLP weights.
    
    This mirrors the Dart runtime inference path which uses TF-IDF only.
    """
    counts: dict[int, int] = {}
    for token in _char_wb_ngrams(text):
        index = model["vocabulary"].get(token)
        if index is not None:
            counts[index] = counts.get(index, 0) + 1
    
    input_dim = model["mlp"]["arch"]["input_dim"]
    vector = np.zeros(input_dim)
    
    # TF-IDF calculation
    for index, count in counts.items():
        if index < input_dim: # Only fill up to TF-IDF features (ignoring BERT for now)
            vector[index] = count * model["idf"][index]
            
    norm = np.linalg.norm(vector)
    if norm > 0:
        vector = vector / norm
        
    # MLP Forward Pass
    mlp = model["mlp"]
    W1 = np.array(mlp["layer1_weight"])
    b1 = np.array(mlp["layer1_bias"])
    W2 = np.array(mlp["layer2_weight"])
    b2 = np.array(mlp["layer2_bias"])
    W3 = np.array(mlp["output_weight"])
    b3 = np.array(mlp["output_bias"])
    
    # h1 = relu(W1.T * x + b1)
    # The weights exported were mlp_model.coefs_[i].T
    # Which means they have shape (out_features, in_features)
    # So we do matrix multiplication W * x + b
    
    h1 = relu(np.dot(W1, vector) + b1)
    h2 = relu(np.dot(W2, h1) + b2)
    out = sigmoid(np.dot(W3, h2) + b3)
    
    return out.tolist()


def _verify_export_parity() -> None:
    artifact = _load_pickle()
    exported = _load_json("observations.json")
    if exported.get("type") != "compact_clinical_mlp":
        raise AssertionError("Unexpected mobile model type")
    if exported.get("classes") != artifact["labels"]:
        raise AssertionError("Exported observation labels do not match the trained model")

    # Verify that the TF-IDF-only inference path produces consistent results
    probes = [
        "Oxygen saturation is 83 percent on nasal cannula.",
        "The patient has dark, foul-smelling urine.",
        "Respirations are elevated while using accessory muscles.",
    ]
    
    mlp_model = artifact["mlp_model"]
    vectorizer = artifact["vectorizer"]
    
    for probe in probes:
        # Student model uses TF-IDF only — no zero-padding needed
        tfidf_features = vectorizer.transform([probe]).toarray()
        
        expected = mlp_model.predict_proba(tfidf_features)[0].tolist()
        actual = predict_export_probabilities(probe, exported)
        
        for expected_value, actual_value in zip(expected, actual):
            if not math.isclose(expected_value, actual_value, rel_tol=1e-5, abs_tol=1e-5):
                raise AssertionError(
                    f"Export mismatch for {probe!r}: {expected_value} != {actual_value}"
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
        print(
            "Warning: Number of validated advisory labels dropped: "
            f"baseline={len(baseline_labels)}, current={len(current_labels)}"
        )


if __name__ == "__main__":
    _verify_export_parity()
    _verify_quality_gate()
    _verify_no_regression()
    print("Mobile observation export matches the trained model and passed quality gates.")
