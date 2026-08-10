"""Train an advisory clinical-observation model from public SYNUR labels.

The model only supplies optional context to the on-device LLM.  It never
extracts a value, selects a patient, or causes a chart write.  This boundary
is deliberate: SYNUR is a small synthetic research dataset, not an adequate
source for autonomous clinical documentation.
"""

from __future__ import annotations

import json
import pickle
import sys
from collections import Counter
from pathlib import Path
from typing import Iterable

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import SGDClassifier
from sklearn.metrics import f1_score, precision_recall_fscore_support

sys.path.append(str(Path(__file__).resolve().parent.parent))
from config import settings
from synur_dataset import DATASET_ID, DATASET_LICENSE, DATASET_REVISION, SynurExample, load_all_splits


SEED = 42
MIN_TRAIN_SUPPORT = 8
MIN_DEV_SUPPORT = 4
MIN_DEV_LABEL_F1 = 0.70
THRESHOLD_GRID = tuple(round(value / 100, 2) for value in range(10, 91, 5))


def _make_vectorizer() -> TfidfVectorizer:
    # Character n-grams are resilient to dictation punctuation and common
    # transcription variation. ``char_wb`` keeps n-grams inside word
    # boundaries and is mirrored in the Dart runtime.
    return TfidfVectorizer(
        lowercase=True,
        analyzer="char_wb",
        ngram_range=(3, 6),
        min_df=1,
        max_features=20000,
        norm="l2",
    )


def _labels(examples: Iterable[SynurExample], selected: set[str]) -> list[list[int]]:
    return [
        [int(label in example.observation_names) for label in sorted(selected)]
        for example in examples
    ]


def _fit_estimators(features, targets: list[list[int]]) -> list[SGDClassifier]:
    if not targets:
        raise ValueError("No training examples")
    transposed = list(zip(*targets))
    estimators: list[SGDClassifier] = []
    for target in transposed:
        if len(set(target)) < 2:
            raise ValueError("Each observation label needs positive and negative examples")
        estimator = SGDClassifier(
            loss="log_loss",
            alpha=0.0002,
            class_weight="balanced",
            random_state=SEED,
            max_iter=3000,
            tol=0.0001,
        )
        estimator.fit(features, target)
        estimators.append(estimator)
    return estimators


def _probabilities(estimators: list[SGDClassifier], features) -> list[list[float]]:
    rows = [[0.0] * len(estimators) for _ in range(features.shape[0])]
    for index, estimator in enumerate(estimators):
        probabilities = estimator.predict_proba(features)
        positive_index = estimator.classes_.tolist().index(1)
        for row_index, probability in enumerate(probabilities[:, positive_index]):
            rows[row_index][index] = float(probability)
    return rows


def _binary(probabilities: list[list[float]], threshold: float) -> list[list[int]]:
    return [[int(value >= threshold) for value in row] for row in probabilities]


def _metric_summary(targets: list[list[int]], predictions: list[list[int]]) -> dict[str, float]:
    return {
        "micro_f1": round(
            float(f1_score(targets, predictions, average="micro", zero_division=0)), 4
        ),
        "macro_f1": round(
            float(f1_score(targets, predictions, average="macro", zero_division=0)), 4
        ),
        "samples_f1": round(
            float(f1_score(targets, predictions, average="samples", zero_division=0)),
            4,
        ),
    }


def _best_threshold(targets: list[list[int]], probabilities: list[list[float]]) -> float:
    return max(
        THRESHOLD_GRID,
        key=lambda threshold: f1_score(
            targets,
            _binary(probabilities, threshold),
            average="micro",
            zero_division=0,
        ),
    )


def _select_labels(
    labels: list[str],
    targets: list[list[int]],
    probabilities: list[list[float]],
    threshold: float,
) -> tuple[list[str], dict[str, dict[str, float | int]]]:
    predicted = _binary(probabilities, threshold)
    chosen: list[str] = []
    details: dict[str, dict[str, float | int]] = {}
    for index, label in enumerate(labels):
        actual_column = [row[index] for row in targets]
        predicted_column = [row[index] for row in predicted]
        precision, recall, label_f1, _ = precision_recall_fscore_support(
            actual_column,
            predicted_column,
            average="binary",
            zero_division=0,
        )
        support = sum(actual_column)
        details[label] = {
            "support": int(support),
            "precision": round(float(precision), 4),
            "recall": round(float(recall), 4),
            "f1": round(float(label_f1), 4),
        }
        if support >= MIN_DEV_SUPPORT and label_f1 >= MIN_DEV_LABEL_F1:
            chosen.append(label)
    if len(chosen) < 3:
        raise RuntimeError(
            "SYNUR validation did not yield three sufficiently reliable advisory labels"
        )
    return chosen, details


def _training_report(
    *,
    splits: dict[str, list[SynurExample]],
    labels: list[str],
    threshold: float,
    dev_metrics: dict[str, float],
    test_metrics: dict[str, float],
    per_label_dev: dict[str, dict[str, float | int]],
) -> dict:
    return {
        "model_role": "advisory_clinical_observation_context",
        "dataset": {
            "id": DATASET_ID,
            "revision": DATASET_REVISION,
            "license": DATASET_LICENSE,
            "split_sizes": {name: len(rows) for name, rows in splits.items()},
        },
        "selection": {
            "candidate_min_train_support": MIN_TRAIN_SUPPORT,
            "minimum_dev_support": MIN_DEV_SUPPORT,
            "minimum_dev_label_f1": MIN_DEV_LABEL_F1,
            "threshold": threshold,
            "labels": labels,
            "per_label_dev": {label: per_label_dev[label] for label in labels},
            "dev_metrics": dev_metrics,
        },
        "held_out_test": test_metrics,
        "limitations": [
            "SYNUR is synthetic research data, not real EHR or patient data.",
            "The model only proposes context labels and cannot extract values or write a record.",
            "Nurses must review and confirm every AI-proposed chart change.",
        ],
    }


def train_model() -> None:
    print("Loading pinned public nursing-dictation dataset (SYNUR)...")
    splits = load_all_splits()
    train_examples = splits["train"]
    dev_examples = splits["dev"]
    test_examples = splits["test"]

    support = Counter(
        label for example in train_examples for label in example.observation_names
    )
    candidate_labels = sorted(
        label for label, count in support.items() if count >= MIN_TRAIN_SUPPORT
    )
    if not candidate_labels:
        raise RuntimeError("No SYNUR labels meet the training support threshold")
    candidate_set = set(candidate_labels)

    selector_vectorizer = _make_vectorizer()
    train_features = selector_vectorizer.fit_transform(
        [example.transcript for example in train_examples]
    )
    dev_features = selector_vectorizer.transform(
        [example.transcript for example in dev_examples]
    )
    train_targets = _labels(train_examples, candidate_set)
    dev_targets = _labels(dev_examples, candidate_set)
    selector_estimators = _fit_estimators(train_features, train_targets)
    dev_probabilities = _probabilities(selector_estimators, dev_features)
    threshold = _best_threshold(dev_targets, dev_probabilities)
    selected_labels, per_label_dev = _select_labels(
        candidate_labels,
        dev_targets,
        dev_probabilities,
        threshold,
    )
    selected_set = set(selected_labels)
    selected_indexes = [candidate_labels.index(label) for label in selected_labels]
    selected_dev_targets = [[row[index] for index in selected_indexes] for row in dev_targets]
    selected_dev_probabilities = [
        [row[index] for index in selected_indexes] for row in dev_probabilities
    ]
    dev_metrics = _metric_summary(
        selected_dev_targets, _binary(selected_dev_probabilities, threshold)
    )

    # Only after selection/calibration do we add the development split to the
    # final fit.  The MEDIQA test split remains entirely held out.
    final_examples = [*train_examples, *dev_examples]
    final_vectorizer = _make_vectorizer()
    final_features = final_vectorizer.fit_transform(
        [example.transcript for example in final_examples]
    )
    final_targets = _labels(final_examples, selected_set)
    final_estimators = _fit_estimators(final_features, final_targets)
    test_features = final_vectorizer.transform(
        [example.transcript for example in test_examples]
    )
    test_targets = _labels(test_examples, selected_set)
    test_metrics = _metric_summary(
        test_targets,
        _binary(_probabilities(final_estimators, test_features), threshold),
    )

    artifact = {
        "vectorizer": final_vectorizer,
        "estimators": final_estimators,
        "labels": selected_labels,
        "threshold": threshold,
    }
    model_path = settings.DATA_DIR / "clinical_observation_model.pkl"
    report_path = settings.DATA_DIR / "clinical_observation_metrics.json"
    with model_path.open("wb") as file:
        pickle.dump(artifact, file)
    report = _training_report(
        splits=splits,
        labels=selected_labels,
        threshold=threshold,
        dev_metrics=dev_metrics,
        test_metrics=test_metrics,
        per_label_dev=per_label_dev,
    )
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"Selected {len(selected_labels)} advisory observation labels.")
    print(f"Validation metrics: {dev_metrics}")
    print(f"Held-out test metrics: {test_metrics}")
    print(f"Saved model: {model_path}")
    print(f"Saved metrics: {report_path}")


if __name__ == "__main__":
    train_model()
