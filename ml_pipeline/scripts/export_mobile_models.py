"""Export the real-data SYNUR advisory model for deterministic Dart inference.

When BioClinicalBERT was used during training, the export includes an optional
``bert_projection`` field containing the PCA components matrix. This field is
optional and backward-compatible: the Dart runtime ignores it if absent and
continues to use TF-IDF-only inference.
"""

from __future__ import annotations

import hashlib
import json
import os
import pickle
import sys
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import sklearn

sys.path.append(str(Path(__file__).resolve().parent.parent))
from config import settings


def calculate_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def export_observation_model(model_path: Path, output_path: Path) -> str:
    with model_path.open("rb") as file:
        artifact = pickle.load(file)
    vectorizer = artifact["vectorizer"]
    estimators = artifact["estimators"]
    labels = artifact["labels"]
    threshold = artifact["threshold"]
    used_bert = artifact.get("used_bert", False)
    bert_pca = artifact.get("bert_pca")
    if len(estimators) != len(labels):
        raise ValueError("Observation model estimators and labels do not match")

    # Extract the TF-IDF portion of the coefficients
    tfidf_dim = len(vectorizer.vocabulary_)
    if used_bert and bert_pca is not None:
        bert_dim = bert_pca.n_components
        total_dim = tfidf_dim + bert_dim
        # Verify dimensions match
        for est in estimators:
            if est.coef_.shape[1] != total_dim:
                raise ValueError(
                    f"Estimator has {est.coef_.shape[1]} features, "
                    f"expected {total_dim} (tfidf={tfidf_dim} + bert={bert_dim})"
                )
        # Split coefficients into TF-IDF and BERT parts
        tfidf_coef = [est.coef_[0, :tfidf_dim].tolist() for est in estimators]
        bert_coef = [est.coef_[0, tfidf_dim:].tolist() for est in estimators]
    else:
        tfidf_coef = [est.coef_[0].tolist() for est in estimators]
        bert_coef = None

    payload = {
        "type": "multi_label_sgd_classifier",
        "format_version": 1,
        "role": "advisory_clinical_observation_context",
        "vocabulary": {key: int(value) for key, value in vectorizer.vocabulary_.items()},
        "idf": vectorizer.idf_.tolist(),
        "coef": tfidf_coef,
        "intercept": [float(est.intercept_[0]) for est in estimators],
        "classes": labels,
        "threshold": float(threshold),
        "preprocessing": {
            "lowercase": True,
            "analyzer": "char_wb",
            "ngram_range": [3, 6],
            "vectorizer": "tfidf_l2",
        },
    }

    # Add optional BioClinicalBERT projection data (backward-compatible)
    if used_bert and bert_pca is not None and bert_coef is not None:
        payload["bert_projection"] = {
            "model_name": artifact.get("bert_model_name", "emilyalsentzer/Bio_ClinicalBERT"),
            "pca_components": bert_pca.components_.tolist(),
            "pca_mean": bert_pca.mean_.tolist(),
            "bert_coef": bert_coef,
            "embedding_dim": int(bert_pca.components_.shape[1]),
            "reduced_dim": int(bert_pca.n_components),
            "note": (
                "Optional. Dart runtime uses TF-IDF inference by default. "
                "BERT projection is available for future on-device BERT integration."
            ),
        }

    output_path.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    return calculate_sha256(output_path)


def main() -> None:
    output_dir = settings.DATA_DIR / "mobile_export"
    output_dir.mkdir(parents=True, exist_ok=True)
    model_path = settings.DATA_DIR / "clinical_observation_model.pkl"
    metrics_path = settings.DATA_DIR / "clinical_observation_metrics.json"
    if not model_path.exists() or not metrics_path.exists():
        raise FileNotFoundError("Train the SYNUR observation model before exporting it")

    observations_path = output_dir / "observations.json"
    observation_sha = export_observation_model(model_path, observations_path)
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    version = os.environ.get("MODEL_VERSION", "nurse-nlp-dev")
    metadata = {
        "model_version": version,
        "schema_version": 2,
        "created_at": datetime.now(UTC).isoformat(),
        "commit_sha": os.environ.get("GITHUB_SHA", "unknown"),
        "observation_model": {"artifact": "observations.json", "sha256": observation_sha},
        "runtime": {"android": "dart_native_ml", "ios": "dart_native_ml"},
        "training": {
            "python_version": sys.version.split()[0],
            "scikit_learn_version": sklearn.__version__,
            "dataset": metrics["dataset"],
            "model_role": metrics["model_role"],
            "features": metrics.get("training_features", {"tfidf": True, "bioclinicalbert": False}),
        },
        "metrics": {
            "validation": metrics["selection"]["dev_metrics"],
            "held_out_test": metrics["held_out_test"],
            "selected_labels": metrics["selection"]["labels"],
            "limitations": metrics["limitations"],
        },
    }
    if "tfidf_only_test_metrics" in metrics:
        metadata["metrics"]["tfidf_only_test"] = metrics["tfidf_only_test_metrics"]

    metadata_path = output_dir / "metadata.json"
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    package_path = output_dir / f"nurseassist-observation-model-{version}.zip"
    with zipfile.ZipFile(package_path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.write(observations_path, "observations.json")
        archive.write(metadata_path, "metadata.json")
    print(f"Exported {observations_path.name} ({observation_sha[:12]}...)")
    if metrics.get("training_features", {}).get("bioclinicalbert"):
        print("  Includes BioClinicalBERT projection data (optional, backward-compatible)")
    print(f"Packaged {package_path.name}")


if __name__ == "__main__":
    main()
