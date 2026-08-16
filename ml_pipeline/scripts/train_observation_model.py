"""Train an advisory clinical-observation MLP model with knowledge distillation.

This module trains a compact Multi-Layer Perceptron (MLP) using scikit-learn.
When BioClinicalBERT is available (CI), it uses knowledge distillation:
  1. Train a TEACHER model on BERT+TF-IDF features (1024 dims)
  2. Distill into a STUDENT model on TF-IDF-only features (512 dims)
  3. Export the student for mobile inference

When BioClinicalBERT is not available (local dev), trains directly on TF-IDF.
This ensures perfect train/serve parity — the exported model always uses the
same feature space as the Dart runtime.

All hyperparameters are read from config.py (env-overridable via NURSEASSIST_*).
"""

from __future__ import annotations

import json
import pickle
import sys
from collections import Counter
from pathlib import Path
from typing import Optional

import numpy as np
from sklearn.decomposition import PCA
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import f1_score, precision_recall_fscore_support
from sklearn.preprocessing import normalize as sklearn_normalize
from sklearn.neural_network import MLPClassifier

sys.path.append(str(Path(__file__).resolve().parent.parent))
from config import settings
from synur_dataset import DATASET_ID, DATASET_LICENSE, DATASET_REVISION, SynurExample, load_all_splits

try:
    from clinical_dataset import load_mtsamples_dataset
except ImportError:
    load_mtsamples_dataset = None

from nlp.bioclinicalbert_embedder import BioClinicalBertEmbedder

# All constants sourced from settings — no magic numbers in this file
THRESHOLD_GRID = tuple(round(value / 100, 2) for value in range(10, 91, 5))


def _verify_parameter_budget(mlp: MLPClassifier):
    """Verify the trained model stays within the configured parameter budget."""
    total_params = sum(c.size for c in mlp.coefs_) + sum(b.size for b in mlp.intercepts_)
    print(f"MLP Parameter count: {total_params}")
    if total_params > settings.MLP_PARAM_BUDGET:
        raise ValueError(
            f"Model exceeds {settings.MLP_PARAM_BUDGET:,} parameter budget! ({total_params:,})"
        )


def _make_vectorizer() -> TfidfVectorizer:
    return TfidfVectorizer(
        lowercase=True,
        analyzer="char_wb",
        ngram_range=(3, 6),
        min_df=1,
        max_features=settings.TFIDF_MAX_FEATURES,
        norm="l2",
    )


def _labels(examples, selected: set[str]) -> list[list[int]]:
    return [
        [int(label in example.observation_names) for label in sorted(selected)]
        for example in examples
    ]


def _train_mlp(
    features: np.ndarray,
    targets: list[list[int]],
    hidden_sizes: tuple | None = None,
) -> MLPClassifier:

    if not targets:
        raise ValueError("No training examples")

    if hidden_sizes is None:
        hidden_sizes = settings.MLP_HIDDEN_SIZES

    print(f"Training MLP on {features.shape[0]} samples with {features.shape[1]} features "
          f"(hidden={hidden_sizes})...")
    mlp = MLPClassifier(
        hidden_layer_sizes=hidden_sizes,
        activation='relu',
        solver='adam',
        alpha=settings.MLP_ALPHA,
        batch_size=settings.MLP_BATCH_SIZE,
        learning_rate_init=settings.MLP_LEARNING_RATE,
        max_iter=settings.MLP_MAX_ITER,
        random_state=settings.SEED,
        early_stopping=True,
        validation_fraction=0.1,
    )

    mlp.fit(features, np.array(targets))
    _verify_parameter_budget(mlp)

    return mlp


def _distill_targets(
    hard_targets: np.ndarray,
    teacher_proba: np.ndarray,
    alpha: float | None = None,
    temperature: float | None = None,
) -> list[list[int]]:
    """Create distilled training targets by blending hard labels with teacher predictions.

    Uses the teacher's soft predictions to augment the hard labels:
    - Where the teacher is confident about a positive label that the hard label missed,
      the distilled label may flip to positive (transferring BERT knowledge).
    - Where the teacher disagrees with a positive hard label, the hard label is trusted
      (ground truth takes precedence).
    """
    if alpha is None:
        alpha = settings.DISTILL_ALPHA
    if temperature is None:
        temperature = settings.DISTILL_TEMPERATURE

    eps = 1e-7
    teacher_logits = np.log((teacher_proba + eps) / (1 - teacher_proba + eps))
    soft_proba = 1.0 / (1.0 + np.exp(-teacher_logits / temperature))

    blended = alpha * hard_targets.astype(float) + (1 - alpha) * soft_proba
    distilled = (blended >= settings.DISTILL_THRESHOLD).astype(int)

    return distilled.tolist()


def _probabilities(model: MLPClassifier, features: np.ndarray) -> list[list[float]]:
    return model.predict_proba(features).tolist()


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
            float(f1_score(targets, predictions, average="samples", zero_division=0)), 4,
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
        if support >= settings.MIN_DEV_SUPPORT and label_f1 >= settings.MIN_DEV_LABEL_F1:
            chosen.append(label)
    if len(chosen) < settings.MIN_SELECTED_LABELS:
        raise RuntimeError(
            f"Validation did not yield {settings.MIN_SELECTED_LABELS} sufficiently reliable "
            "advisory labels"
        )
    return chosen, details


def _compute_bert_features(
    embedder: "BioClinicalBertEmbedder",
    texts: list[str],
    pca: Optional[PCA] = None,
    fit_pca: bool = False,
) -> tuple[np.ndarray, Optional[PCA]]:
    print(f"  Computing BioClinicalBERT embeddings for {len(texts)} texts...")
    embeddings = embedder.encode(texts, pooling="cls", show_progress=True)

    if fit_pca:
        n_components = min(settings.PCA_COMPONENTS, embeddings.shape[0], embeddings.shape[1])
        pca = PCA(n_components=n_components, random_state=settings.SEED)
        reduced = pca.fit_transform(embeddings)
        explained = sum(pca.explained_variance_ratio_) * 100
        print(
            f"  PCA: {embeddings.shape[1]} → {n_components} dims "
            f"({explained:.1f}% variance explained)"
        )
    elif pca is not None:
        reduced = pca.transform(embeddings)
    else:
        reduced = embeddings

    reduced = sklearn_normalize(reduced, norm="l2")
    return reduced, pca


def _combine_features(tfidf_features, bert_features: Optional[np.ndarray]) -> np.ndarray:
    tfidf_dense = tfidf_features.toarray() if hasattr(tfidf_features, "toarray") else tfidf_features
    if bert_features is None:
        return tfidf_dense.astype(np.float32)
    return np.hstack([tfidf_dense, bert_features]).astype(np.float32)


def _training_report(
    *,
    splits: dict[str, list[SynurExample]],
    labels: list[str],
    threshold: float,
    dev_metrics: dict[str, float],
    test_metrics: dict[str, float],
    per_label_dev: dict[str, dict[str, float | int]],
    synthetic_count: int = 0,
    telemetry_count: int = 0,
    used_distillation: bool = False,
) -> dict:
    return {
        "model_role": "advisory_clinical_observation_context",
        "architecture": (
            "Compact Clinical MLP (TF-IDF student via knowledge distillation)"
            if used_distillation
            else "Compact Clinical MLP (TF-IDF only)"
        ),
        "dataset": {
            "id": DATASET_ID,
            "synthetic_count": synthetic_count,
            "telemetry_count": telemetry_count,
            "split_sizes": {name: len(rows) for name, rows in splits.items()},
        },
        "selection": {
            "candidate_min_train_support": settings.MIN_TRAIN_SUPPORT,
            "minimum_dev_support": settings.MIN_DEV_SUPPORT,
            "minimum_dev_label_f1": settings.MIN_DEV_LABEL_F1,
            "threshold": threshold,
            "labels": labels,
            "per_label_dev": {label: per_label_dev[label] for label in labels},
            "dev_metrics": dev_metrics,
        },
        "held_out_test": test_metrics,
        "training_features": {
            "tfidf_dims": settings.TFIDF_MAX_FEATURES,
            "bioclinicalbert": False,
            "distilled_from_bert": used_distillation,
            "pca_components": settings.PCA_COMPONENTS,
        },
    }


def train_model() -> None:
    print("Loading datasets...")
    splits = load_all_splits()
    train_examples = list(splits["train"])
    dev_examples = list(splits["dev"])
    test_examples = list(splits["test"])

    synthetic_count = 0
    if load_mtsamples_dataset:
        print("Fetching real clinical notes from MTSamples...")
        synthetic_examples = load_mtsamples_dataset(
            max_records=settings.MTSAMPLES_MAX_RECORDS
        )
        synthetic_count = len(synthetic_examples)

        split_1 = int(synthetic_count * 0.8)
        split_2 = int(synthetic_count * 0.9)
        train_examples.extend(synthetic_examples[:split_1])
        dev_examples.extend(synthetic_examples[split_1:split_2])
        test_examples.extend(synthetic_examples[split_2:])

    telemetry_count = 0
    telemetry_path = settings.DATA_DIR / ".cache" / "telemetry" / "telemetry_examples.pkl"
    if telemetry_path.exists():
        try:
            with telemetry_path.open("rb") as f:
                telemetry_data = pickle.load(f)
            telemetry_count = len(telemetry_data)
            split_1 = int(telemetry_count * 0.8)
            split_2 = int(telemetry_count * 0.9)
            train_examples.extend(telemetry_data[:split_1])
            dev_examples.extend(telemetry_data[split_1:split_2])
            test_examples.extend(telemetry_data[split_2:])
            print(f"Loaded {telemetry_count} field-telemetry examples for continual training.")
        except Exception as e:
            print(f"Failed to load field-telemetry examples: {e}")

    support = Counter(
        label for example in train_examples for label in example.observation_names
    )
    candidate_labels = sorted(
        label for label, count in support.items() if count >= settings.MIN_TRAIN_SUPPORT
    )
    if not candidate_labels:
        raise RuntimeError("No labels meet the training support threshold")
    candidate_set = set(candidate_labels)

    # --- TF-IDF ---
    print(f"Extracting TF-IDF features (max {settings.TFIDF_MAX_FEATURES})...")
    selector_vectorizer = _make_vectorizer()
    train_tfidf = selector_vectorizer.fit_transform(
        [example.transcript for example in train_examples]
    )
    dev_tfidf = selector_vectorizer.transform(
        [example.transcript for example in dev_examples]
    )

    # --- BioClinicalBERT (for teacher model only) ---
    print("\n=== BioClinicalBERT Feature Extraction ===")
    used_bert = False
    bert_embedder = None
    train_bert = None
    dev_bert = None

    if settings.USE_BIOCLINICALBERT:
        try:
            bert_embedder = BioClinicalBertEmbedder(
                model_name=settings.BIOCLINICALBERT_MODEL,
                max_length=settings.BIOCLINICALBERT_MAX_LENGTH,
                batch_size=settings.BIOCLINICALBERT_BATCH_SIZE,
                cache_dir=settings.BIOCLINICALBERT_CACHE_DIR,
            )

            train_texts = [example.transcript for example in train_examples]
            dev_texts = [example.transcript for example in dev_examples]

            train_bert, selector_pca = _compute_bert_features(
                bert_embedder, train_texts, fit_pca=True,
            )
            dev_bert, _ = _compute_bert_features(
                bert_embedder, dev_texts, pca=selector_pca,
            )
            used_bert = True
        except Exception as e:
            print(f"BioClinicalBERT is unavailable due to an error: {e}")
            print("Falling back to TF-IDF only (no distillation).")
    else:
        print("BioClinicalBERT is disabled. Using TF-IDF only.")

    # --- Label Selection (use best available features) ---
    train_targets = _labels(train_examples, candidate_set)
    dev_targets = _labels(dev_examples, candidate_set)

    if used_bert:
        teacher_train_features = _combine_features(train_tfidf, train_bert)
        teacher_dev_features = _combine_features(dev_tfidf, dev_bert)

        print("\n=== Training TEACHER MLP (BERT+TF-IDF) for Label Selection ===")
        teacher_mlp = _train_mlp(teacher_train_features, train_targets)

        teacher_dev_proba = _probabilities(teacher_mlp, teacher_dev_features)
        threshold = _best_threshold(dev_targets, teacher_dev_proba)
        selected_labels, per_label_dev = _select_labels(
            candidate_labels, dev_targets, teacher_dev_proba, threshold,
        )
    else:
        tfidf_train_features = _combine_features(train_tfidf, None)
        tfidf_dev_features = _combine_features(dev_tfidf, None)

        print("\n=== Training MLP (TF-IDF only) ===")
        selector_mlp = _train_mlp(tfidf_train_features, train_targets)

        dev_probabilities = _probabilities(selector_mlp, tfidf_dev_features)
        threshold = _best_threshold(dev_targets, dev_probabilities)
        selected_labels, per_label_dev = _select_labels(
            candidate_labels, dev_targets, dev_probabilities, threshold,
        )

    selected_set = set(selected_labels)

    # ====================================================================
    # Final model training: ALWAYS produces a TF-IDF-only model for mobile
    # ====================================================================
    final_examples = [*train_examples, *dev_examples]
    final_vectorizer = _make_vectorizer()
    final_tfidf = final_vectorizer.fit_transform(
        [example.transcript for example in final_examples]
    )
    test_tfidf = final_vectorizer.transform(
        [example.transcript for example in test_examples]
    )

    final_tfidf_features = _combine_features(final_tfidf, None)
    test_tfidf_features = _combine_features(test_tfidf, None)

    final_targets = _labels(final_examples, selected_set)
    test_targets = _labels(test_examples, selected_set)

    used_distillation = False

    if used_bert:
        # === KNOWLEDGE DISTILLATION ===
        print("\n=== Knowledge Distillation: Training TEACHER on final data ===")

        final_texts = [example.transcript for example in final_examples]
        test_texts = [example.transcript for example in test_examples]

        final_bert, final_pca = _compute_bert_features(
            bert_embedder, final_texts, fit_pca=True,
        )
        test_bert, _ = _compute_bert_features(
            bert_embedder, test_texts, pca=final_pca,
        )

        final_teacher_features = _combine_features(final_tfidf, final_bert)
        test_teacher_features = _combine_features(test_tfidf, test_bert)

        teacher_final = _train_mlp(final_teacher_features, final_targets)

        teacher_proba = np.array(teacher_final.predict_proba(final_teacher_features))

        distilled_targets = _distill_targets(
            np.array(final_targets), teacher_proba,
        )

        print("\n=== Training STUDENT MLP (TF-IDF only, distilled from BERT teacher) ===")
        final_mlp = _train_mlp(final_tfidf_features, distilled_targets)
        used_distillation = True

        test_metrics = _metric_summary(
            test_targets,
            _binary(_probabilities(final_mlp, test_tfidf_features), threshold),
        )

        teacher_test_metrics = _metric_summary(
            test_targets,
            _binary(_probabilities(teacher_final, test_teacher_features), threshold),
        )
        print(f"\nTeacher (BERT+TF-IDF) test metrics: {teacher_test_metrics}")
        print(f"Student (TF-IDF distilled) test metrics: {test_metrics}")
    else:
        # === Direct TF-IDF training (no distillation) ===
        print("\n=== Final Training on Train+Dev (TF-IDF only) ===")
        final_mlp = _train_mlp(final_tfidf_features, final_targets)

        test_metrics = _metric_summary(
            test_targets,
            _binary(_probabilities(final_mlp, test_tfidf_features), threshold),
        )

    # Save artifact — ALWAYS a TF-IDF-only student model
    artifact = {
        "vectorizer": final_vectorizer,
        "mlp_model": final_mlp,
        "labels": selected_labels,
        "threshold": threshold,
        "used_bert": False,
        "bert_pca": None,
        "distilled": used_distillation,
    }

    model_path = settings.DATA_DIR / "clinical_observation_model.pkl"
    report_path = settings.DATA_DIR / "clinical_observation_metrics.json"

    with model_path.open("wb") as file:
        pickle.dump(artifact, file)

    # Dev metrics from student model on TF-IDF features
    dev_tfidf_features = _combine_features(
        selector_vectorizer.transform([e.transcript for e in dev_examples]), None
    )
    student_dev_proba = _probabilities(final_mlp, dev_tfidf_features)
    dev_selected_targets = _labels(dev_examples, selected_set)
    dev_metrics = _metric_summary(
        dev_selected_targets,
        _binary(student_dev_proba, threshold),
    )

    report = _training_report(
        splits=splits,
        labels=selected_labels,
        threshold=threshold,
        dev_metrics=dev_metrics,
        test_metrics=test_metrics,
        per_label_dev=per_label_dev,
        synthetic_count=synthetic_count,
        telemetry_count=telemetry_count,
        used_distillation=used_distillation,
    )
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"\nSaved model: {model_path}")
    print(f"Validation metrics: {dev_metrics}")
    print(f"Held-out test metrics: {test_metrics}")
    if used_distillation:
        print("Model type: TF-IDF student (distilled from BERT+TF-IDF teacher)")
    else:
        print("Model type: TF-IDF only (no distillation)")


if __name__ == "__main__":
    train_model()
