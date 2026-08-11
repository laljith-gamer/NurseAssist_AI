"""Verify mobile-export parity and fail a release below its quality gate."""

from __future__ import annotations

import json
import math
import pickle
import sys
from pathlib import Path

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
    probes = [
        "Oxygen saturation is 83 percent on nasal cannula.",
        "The patient has dark, foul-smelling urine.",
        "Respirations are elevated while using accessory muscles.",
    ]
    for probe in probes:
        expected = []
        features = artifact["vectorizer"].transform([probe])
        for estimator in artifact["estimators"]:
            positive_index = estimator.classes_.tolist().index(1)
            expected.append(float(estimator.predict_proba(features)[0][positive_index]))
        actual = predict_export_probabilities(probe, exported)
        for expected_value, actual_value in zip(expected, actual):
            if not math.isclose(expected_value, actual_value, rel_tol=1e-6, abs_tol=1e-6):
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
        raise AssertionError(
            "Number of validated advisory labels dropped: "
            f"baseline={len(baseline_labels)}, current={len(current_labels)}"
        )


if __name__ == "__main__":
    _verify_export_parity()
    _verify_quality_gate()
    _verify_no_regression()
    print("Mobile observation export matches the trained model and passed quality gates.")
