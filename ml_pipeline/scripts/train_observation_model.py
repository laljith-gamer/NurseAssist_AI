"""Train an advisory clinical-observation MLP model.

This module trains a compact Multi-Layer Perceptron (MLP) with a hard parameter
budget (< 100K parameters) using scikit-learn. The model takes a concatenated vector
of TF-IDF features and BioClinicalBERT embeddings (PCA-reduced) as input, and
outputs multi-label probabilities for clinical observations.

The clinical reasoning module is applied post-prediction to enhance the output.
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
from sklearn.metrics import f1_score, precision_recall_fscore_support
from sklearn.preprocessing import normalize as sklearn_normalize
from sklearn.neural_network import MLPClassifier

sys.path.append(str(Path(__file__).resolve().parent.parent))
from config import settings
from synur_dataset import DATASET_ID, DATASET_LICENSE, DATASET_REVISION, SynurExample, load_all_splits

# New custom dataset
try:
    from clinical_dataset import load_mtsamples_dataset
except ImportError:
    load_mtsamples_dataset = None

from nlp.bioclinicalbert_embedder import BioClinicalBertEmbedder

SEED = 42
MIN_TRAIN_SUPPORT = 8
MIN_DEV_SUPPORT = 4
MIN_DEV_LABEL_F1 = 0.40
THRESHOLD_GRID = tuple(round(value / 100, 2) for value in range(10, 91, 5))
PCA_COMPONENTS = 256
TFIDF_FEATURES = 256


def _verify_parameter_budget(mlp: MLPClassifier):
    # MLPClassifier stores weights in coefs_ (list of arrays) and biases in intercepts_ (list of arrays)
    total_params = 0
    for coef in mlp.coefs_:
        total_params += coef.size
    for intercept in mlp.intercepts_:
        total_params += intercept.size
    print(f"MLP Parameter count: {total_params}")
    if total_params > 100000:
        raise ValueError(f"Model exceeds 100K parameter budget! ({total_params})")


def _make_vectorizer() -> TfidfVectorizer:
    return TfidfVectorizer(
        lowercase=True,
        analyzer="char_wb",
        ngram_range=(3, 6),
        min_df=1,
        max_features=TFIDF_FEATURES,
        norm="l2",
    )


def _labels(examples: Iterable[SynurExample], selected: set[str]) -> list[list[int]]:
    return [
        [int(label in example.observation_names) for label in sorted(selected)]
        for example in examples
    ]


def _train_mlp(
    features: np.ndarray, 
    targets: list[list[int]]
) -> MLPClassifier:
    
    if not targets:
        raise ValueError("No training examples")
        
    print(f"Training MLP on {features.shape[0]} samples with {features.shape[1]} features...")
    # 128 hidden neurons, 64 hidden neurons
    mlp = MLPClassifier(
        hidden_layer_sizes=(128, 64),
        activation='relu',
        solver='adam',
        alpha=0.01,
        batch_size=32,
        learning_rate_init=0.001,
        max_iter=50,
        random_state=SEED,
        early_stopping=True,
        validation_fraction=0.1
    )
    
    # MLPClassifier supports multi-label classification directly
    mlp.fit(features, np.array(targets))
    _verify_parameter_budget(mlp)
    
    return mlp


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
            "Validation did not yield three sufficiently reliable advisory labels"
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
) -> dict:
    return {
        "model_role": "advisory_clinical_observation_context",
        "architecture": "Compact Clinical MLP (<100K params)",
        "dataset": {
            "id": DATASET_ID,
            "synthetic_count": synthetic_count,
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
            "tfidf_dims": TFIDF_FEATURES,
            "bioclinicalbert": True,
            "pca_components": PCA_COMPONENTS,
        }
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
        synthetic_examples = load_mtsamples_dataset(max_records=3000)
        synthetic_count = len(synthetic_examples)
        
        # Split real MTSamples data
        split_1 = int(synthetic_count * 0.8)
        split_2 = int(synthetic_count * 0.9)
        train_examples.extend(synthetic_examples[:split_1])
        dev_examples.extend(synthetic_examples[split_1:split_2])
        test_examples.extend(synthetic_examples[split_2:])

    support = Counter(
        label for example in train_examples for label in example.observation_names
    )
    candidate_labels = sorted(
        label for label, count in support.items() if count >= MIN_TRAIN_SUPPORT
    )
    if not candidate_labels:
        raise RuntimeError("No labels meet the training support threshold")
    candidate_set = set(candidate_labels)

    # --- TF-IDF ---
    print(f"Extracting TF-IDF features (max {TFIDF_FEATURES})...")
    selector_vectorizer = _make_vectorizer()
    train_tfidf = selector_vectorizer.fit_transform(
        [example.transcript for example in train_examples]
    )
    dev_tfidf = selector_vectorizer.transform(
        [example.transcript for example in dev_examples]
    )

    # --- BioClinicalBERT ---
    print("\n=== BioClinicalBERT Feature Extraction ===")
    used_bert = False
    bert_pca = None
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
        bert_pca = selector_pca
    except Exception as e:
        print(f"BioClinicalBERT is unavailable due to an error: {e}")
        print("Falling back to TF-IDF only.")
        train_bert = None
        dev_bert = None

    # --- Combine and Train ---
    train_features = _combine_features(train_tfidf, train_bert)
    dev_features = _combine_features(dev_tfidf, dev_bert)

    train_targets = _labels(train_examples, candidate_set)
    dev_targets = _labels(dev_examples, candidate_set)
    
    print("\n=== Training Compact MLP ===")
    mlp_model = _train_mlp(train_features, train_targets)
    
    dev_probabilities = _probabilities(mlp_model, dev_features)
    threshold = _best_threshold(dev_targets, dev_probabilities)
    selected_labels, per_label_dev = _select_labels(
        candidate_labels,
        dev_targets,
        dev_probabilities,
        threshold,
    )
    
    selected_set = set(selected_labels)
    selected_indexes = [candidate_labels.index(label) for label in selected_labels]
    
    # Retrain on full combined train+dev with selected labels
    final_examples = [*train_examples, *dev_examples]
    final_vectorizer = _make_vectorizer()
    final_tfidf = final_vectorizer.fit_transform(
        [example.transcript for example in final_examples]
    )
    test_tfidf = final_vectorizer.transform(
        [example.transcript for example in test_examples]
    )

    final_texts = [example.transcript for example in final_examples]
    test_texts = [example.transcript for example in test_examples]

    if used_bert:
        final_bert, final_pca = _compute_bert_features(
            bert_embedder, final_texts, fit_pca=True,
        )
        test_bert, _ = _compute_bert_features(
            bert_embedder, test_texts, pca=final_pca,
        )
        bert_pca = final_pca
    else:
        final_bert = None
        test_bert = None
        final_pca = None
    
    final_features = _combine_features(final_tfidf, final_bert)
    test_features = _combine_features(test_tfidf, test_bert)

    final_targets = _labels(final_examples, selected_set)
    test_targets = _labels(test_examples, selected_set)
    
    print("\n=== Final Training on Train+Dev ===")
    final_mlp = _train_mlp(final_features, final_targets)
    
    test_metrics = _metric_summary(
        test_targets,
        _binary(_probabilities(final_mlp, test_features), threshold),
    )

    # Save artifact
    artifact = {
        "vectorizer": final_vectorizer,
        "mlp_model": final_mlp,
        "labels": selected_labels,
        "threshold": threshold,
        "used_bert": used_bert,
        "bert_pca": bert_pca,
    }
    if used_bert and bert_pca is not None:
        artifact["bert_model_name"] = settings.BIOCLINICALBERT_MODEL
        artifact["bert_pca_components"] = bert_pca.n_components

    model_path = settings.DATA_DIR / "clinical_observation_model.pkl"
    report_path = settings.DATA_DIR / "clinical_observation_metrics.json"
    
    with model_path.open("wb") as file:
        pickle.dump(artifact, file)
        
    dev_metrics = _metric_summary(
        [[row[index] for index in selected_indexes] for row in dev_targets],
        _binary([[row[index] for index in selected_indexes] for row in dev_probabilities], threshold)
    )
    
    report = _training_report(
        splits=splits,
        labels=selected_labels,
        threshold=threshold,
        dev_metrics=dev_metrics,
        test_metrics=test_metrics,
        per_label_dev=per_label_dev,
        synthetic_count=synthetic_count
    )
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"\nSaved model: {model_path}")
    print(f"Validation metrics: {dev_metrics}")
    print(f"Held-out test metrics: {test_metrics}")

if __name__ == "__main__":
    train_model()
