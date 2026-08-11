"""Export the real-data SYNUR advisory MLP model for Dart inference.

Exports the sklearn MLPClassifier weights, biases, TF-IDF vocabulary, and BERT PCA
projection into a single JSON artifact.
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
    mlp_model = artifact["mlp_model"]
    labels = artifact["labels"]
    threshold = artifact["threshold"]
    bert_pca = artifact["bert_pca"]

    # Extract MLP weights from sklearn MLPClassifier
    # mlp_model.coefs_ is a list of length n_layers - 1
    # For a (128, 64) hidden layer MLP, length is 3.
    # coefs_[0] shape: (n_features, 128)
    # coefs_[1] shape: (128, 64)
    # coefs_[2] shape: (64, n_classes)
    
    # Dart expects transposed weights for its matrix-vector multiply 
    # (or we can just export as is and handle in Dart)
    layer1_weight = mlp_model.coefs_[0].T.tolist()
    layer1_bias = mlp_model.intercepts_[0].tolist()
    layer2_weight = mlp_model.coefs_[1].T.tolist()
    layer2_bias = mlp_model.intercepts_[1].tolist()
    output_weight = mlp_model.coefs_[2].T.tolist()
    output_bias = mlp_model.intercepts_[2].tolist()

    payload = {
        "type": "compact_clinical_mlp",
        "format_version": 2,
        "role": "advisory_clinical_observation_context",
        "vocabulary": {key: int(value) for key, value in vectorizer.vocabulary_.items()},
        "idf": vectorizer.idf_.tolist(),
        "classes": labels,
        "threshold": float(threshold),
        "preprocessing": {
            "lowercase": True,
            "analyzer": "char_wb",
            "ngram_range": [3, 6],
            "vectorizer": "tfidf_l2",
        },
        "mlp": {
            "arch": {
                "input_dim": mlp_model.coefs_[0].shape[0],
                "output_dim": len(labels)
            },
            "layer1_weight": layer1_weight,
            "layer1_bias": layer1_bias,
            "layer2_weight": layer2_weight,
            "layer2_bias": layer2_bias,
            "output_weight": output_weight,
            "output_bias": output_bias,
        },
    }
    
    if bert_pca is not None:
        payload["bert_projection"] = {
            "model_name": artifact.get("bert_model_name", "emilyalsentzer/Bio_ClinicalBERT"),
            "pca_components": bert_pca.components_.tolist(),
            "pca_mean": bert_pca.mean_.tolist(),
            "embedding_dim": int(bert_pca.components_.shape[1]),
            "reduced_dim": int(bert_pca.n_components),
        }

    output_path.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    return calculate_sha256(output_path)


def main() -> None:
    output_dir = settings.DATA_DIR / "mobile_export"
    output_dir.mkdir(parents=True, exist_ok=True)
    model_path = settings.DATA_DIR / "clinical_observation_model.pkl"
    metrics_path = settings.DATA_DIR / "clinical_observation_metrics.json"
    if not model_path.exists() or not metrics_path.exists():
        raise FileNotFoundError("Train the observation model before exporting it")

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
            "features": metrics.get("training_features", {}),
            "architecture": metrics.get("architecture", "Unknown")
        },
        "metrics": {
            "validation": metrics["selection"]["dev_metrics"],
            "held_out_test": metrics["held_out_test"],
            "selected_labels": metrics["selection"]["labels"],
        },
    }

    metadata_path = output_dir / "metadata.json"
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    package_path = output_dir / f"nurseassist-observation-model-{version}.zip"
    with zipfile.ZipFile(package_path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.write(observations_path, "observations.json")
        archive.write(metadata_path, "metadata.json")
    print(f"Exported {observations_path.name} ({observation_sha[:12]}...)")
    print(f"Packaged {package_path.name}")


if __name__ == "__main__":
    main()
