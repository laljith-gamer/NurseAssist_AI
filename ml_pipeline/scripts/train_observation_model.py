"""Train an advisory clinical-observation model from public SYNUR labels.

The model only supplies optional context to the on-device LLM.  It never
extracts a value, selects a patient, or causes a chart write.  This boundary
is deliberate: SYNUR is a small synthetic research dataset, not an adequate
source for autonomous clinical documentation.

When BioClinicalBERT is available, its dense embeddings are concatenated with
TF-IDF features to give the classifier richer clinical-language understanding.
The BioClinicalBERT model is used *only* during training; the exported mobile
artifact remains a lightweight JSON file with TF-IDF weights. A trained PCA
projection from BERT space is optionally exported alongside the TF-IDF model
so future on-device runtimes can adopt BERT features incrementally.
"""

from __future__ import annotations

import json
import pickle
import sys
from collections import Counter
from pathlib import Path
from typing import Iterable, Optional

import numpy as np
from sklearn.decomposition import PCA
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import SGDClassifier
from sklearn.metrics import f1_score, precision_recall_fscore_support
from sklearn.preprocessing import normalize as sklearn_normalize
from scipy.sparse import hstack as sparse_hstack, issparse

sys.path.append(str(Path(__file__).resolve().parent.parent))
from config import settings
from synur_dataset import DATASET_ID, DATASET_LICENSE, DATASET_REVISION, SynurExample, load_all_splits

# Try to import BioClinicalBERT embedder
try:
    from nlp.bioclinicalbert_embedder import BioClinicalBertEmbedder
    _BERT_IMPORTABLE = True
except ImportError:
    _BERT_IMPORTABLE = False


SEED = 42
MIN_TRAIN_SUPPORT = 8
MIN_DEV_SUPPORT = 4
MIN_DEV_LABEL_F1 = 0.70
THRESHOLD_GRID = tuple(round(value / 100, 2) for value in range(10, 91, 5))
PCA_COMPONENTS = 64  # Reduce BERT 768-dim to this for the combined feature space


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


def _get_bert_embedder() -> Optional["BioClinicalBertEmbedder"]:
    """Create a BioClinicalBERT embedder if available and enabled."""
    if not settings.USE_BIOCLINICALBERT:
        print("BioClinicalBERT disabled via USE_BIOCLINICALBERT=False")
        return None

    if not _BERT_IMPORTABLE:
        print("BioClinicalBERT not available (missing torch/transformers)")
        return None

    embedder = BioClinicalBertEmbedder(
        model_name=settings.BIOCLINICALBERT_MODEL,
        max_length=settings.BIOCLINICALBERT_MAX_LENGTH,
        batch_size=settings.BIOCLINICALBERT_BATCH_SIZE,
        cache_dir=settings.BIOCLINICALBERT_CACHE_DIR,
    )
    if not embedder.is_available:
        print("BioClinicalBERT not available (torch/transformers not installed)")
        return None

    return embedder


def _compute_bert_features(
    embedder: "BioClinicalBertEmbedder",
    texts: list[str],
    pca: Optional[PCA] = None,
    fit_pca: bool = False,
) -> tuple[np.ndarray, Optional[PCA]]:
    """Compute BioClinicalBERT embeddings and optionally fit/apply PCA.

    Returns the (optionally PCA-reduced) embedding matrix and the fitted PCA.
    """
    print(f"  Computing BioClinicalBERT embeddings for {len(texts)} texts...")
    embeddings = embedder.encode(texts, pooling="cls", show_progress=True)

    if fit_pca:
        n_components = min(PCA_COMPONENTS, embeddings.shape[0], embeddings.shape[1])
        pca = PCA(n_components=n_components, random_state=SEED)
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

    # L2-normalize the reduced embeddings
    reduced = sklearn_normalize(reduced, norm="l2")
    return reduced, pca


def _combine_features(tfidf_features, bert_features: Optional[np.ndarray]):
    """Concatenate TF-IDF (sparse) and BERT (dense) features horizontally."""
    if bert_features is None:
        return tfidf_features
    from scipy.sparse import csr_matrix
    bert_sparse = csr_matrix(bert_features)
    return sparse_hstack([tfidf_features, bert_sparse], format="csr")


def _training_report(
    *,
    splits: dict[str, list[SynurExample]],
    labels: list[str],
    threshold: float,
    dev_metrics: dict[str, float],
    test_metrics: dict[str, float],
    per_label_dev: dict[str, dict[str, float | int]],
    used_bert: bool = False,
    tfidf_only_test_metrics: Optional[dict[str, float]] = None,
) -> dict:
    report = {
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
        "training_features": {
            "tfidf": True,
            "bioclinicalbert": used_bert,
            "pca_components": PCA_COMPONENTS if used_bert else None,
        },
        "limitations": [
            "SYNUR is synthetic research data, not real EHR or patient data.",
            "The model only proposes context labels and cannot extract values or write a record.",
            "Nurses must review and confirm every AI-proposed chart change.",
        ],
    }
    if tfidf_only_test_metrics is not None:
        report["tfidf_only_test_metrics"] = tfidf_only_test_metrics
    return report


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

    # --- TF-IDF features (always computed) ---
    selector_vectorizer = _make_vectorizer()
    train_tfidf = selector_vectorizer.fit_transform(
        [example.transcript for example in train_examples]
    )
    dev_tfidf = selector_vectorizer.transform(
        [example.transcript for example in dev_examples]
    )

    # --- BioClinicalBERT features (optional) ---
    bert_embedder = _get_bert_embedder()
    train_bert = None
    dev_bert = None
    selector_pca = None
    used_bert = False

    if bert_embedder is not None:
        try:
            print("\n=== BioClinicalBERT Feature Extraction (Selection Phase) ===")
            train_texts = [example.transcript for example in train_examples]
            dev_texts = [example.transcript for example in dev_examples]

            train_bert, selector_pca = _compute_bert_features(
                bert_embedder, train_texts, fit_pca=True,
            )
            dev_bert, _ = _compute_bert_features(
                bert_embedder, dev_texts, pca=selector_pca,
            )
            used_bert = True
            print("BioClinicalBERT features extracted successfully.\n")
        except Exception as error:
            print(f"BioClinicalBERT feature extraction failed: {error}")
            print("Falling back to TF-IDF only.\n")
            train_bert = None
            dev_bert = None
            selector_pca = None

    # --- Combine features ---
    train_features = _combine_features(train_tfidf, train_bert)
    dev_features = _combine_features(dev_tfidf, dev_bert)

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
    final_tfidf = final_vectorizer.fit_transform(
        [example.transcript for example in final_examples]
    )
    test_tfidf = final_vectorizer.transform(
        [example.transcript for example in test_examples]
    )

    # --- Final BERT features ---
    final_bert = None
    test_bert = None
    final_pca = None
    tfidf_only_test_metrics = None

    if used_bert and bert_embedder is not None:
        try:
            print("\n=== BioClinicalBERT Feature Extraction (Final Phase) ===")
            final_texts = [example.transcript for example in final_examples]
            test_texts = [example.transcript for example in test_examples]

            final_bert, final_pca = _compute_bert_features(
                bert_embedder, final_texts, fit_pca=True,
            )
            test_bert, _ = _compute_bert_features(
                bert_embedder, test_texts, pca=final_pca,
            )

            # Also compute TF-IDF-only test metrics for comparison
            tfidf_only_targets = _labels(test_examples, selected_set)
            tfidf_only_estimators = _fit_estimators(
                final_tfidf, _labels(final_examples, selected_set)
            )
            tfidf_only_test_metrics = _metric_summary(
                tfidf_only_targets,
                _binary(
                    _probabilities(tfidf_only_estimators, test_tfidf),
                    threshold,
                ),
            )
            print(f"  TF-IDF-only test metrics: {tfidf_only_test_metrics}")
        except Exception as error:
            print(f"Final BioClinicalBERT extraction failed: {error}")
            print("Falling back to TF-IDF only for final model.\n")
            final_bert = None
            test_bert = None
            final_pca = None
            used_bert = False

    final_features = _combine_features(final_tfidf, final_bert)
    test_features = _combine_features(test_tfidf, test_bert)

    final_targets = _labels(final_examples, selected_set)
    final_estimators = _fit_estimators(final_features, final_targets)
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
        "used_bert": used_bert,
    }
    if used_bert and final_pca is not None:
        artifact["bert_pca"] = final_pca
        artifact["bert_model_name"] = settings.BIOCLINICALBERT_MODEL
        artifact["bert_pca_components"] = final_pca.n_components

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
        used_bert=used_bert,
        tfidf_only_test_metrics=tfidf_only_test_metrics,
    )
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"\nSelected {len(selected_labels)} advisory observation labels.")
    if used_bert:
        print("Features: TF-IDF + BioClinicalBERT (PCA-reduced)")
        if tfidf_only_test_metrics:
            tfidf_f1 = tfidf_only_test_metrics.get("micro_f1", 0)
            bert_f1 = test_metrics.get("micro_f1", 0)
            delta = bert_f1 - tfidf_f1
            sign = "+" if delta >= 0 else ""
            print(f"  TF-IDF-only test micro_f1: {tfidf_f1:.4f}")
            print(f"  TF-IDF+BERT  test micro_f1: {bert_f1:.4f} ({sign}{delta:.4f})")
    else:
        print("Features: TF-IDF only (BioClinicalBERT not available)")
    print(f"Validation metrics: {dev_metrics}")
    print(f"Held-out test metrics: {test_metrics}")
    print(f"Saved model: {model_path}")
    print(f"Saved metrics: {report_path}")


if __name__ == "__main__":
    train_model()
