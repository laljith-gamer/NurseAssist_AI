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
import numpy as np
from sklearn.metrics import f1_score

sys.path.append(str(Path(__file__).resolve().parent.parent))
sys.path.append(str(Path(__file__).resolve().parent))

from config import settings
try:
    from clinical_dataset import load_mtsamples_dataset
except ImportError:
    load_mtsamples_dataset = None
from synur_dataset import load_all_splits


def calculate_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def evaluate_tfidf_parity(artifact: dict) -> dict:
    vectorizer = artifact["vectorizer"]
    mlp_model = artifact["mlp_model"]
    labels = artifact["labels"]
    threshold = artifact["threshold"]

    splits = load_all_splits()
    test_examples = list(splits["test"])

    if load_mtsamples_dataset:
        synthetic_examples = load_mtsamples_dataset(max_records=3000)
        synthetic_count = len(synthetic_examples)
        split_2 = int(synthetic_count * 0.9)
        test_examples.extend(synthetic_examples[split_2:])

    telemetry_path = settings.DATA_DIR / ".cache" / "telemetry" / "telemetry_examples.pkl"
    if telemetry_path.exists():
        try:
            with telemetry_path.open("rb") as f:
                telemetry_data = pickle.load(f)
            telemetry_count = len(telemetry_data)
            split_2 = int(telemetry_count * 0.9)
            test_examples.extend(telemetry_data[split_2:])
        except Exception:
            pass

    test_tfidf = vectorizer.transform([example.transcript for example in test_examples])
    parity_features = test_tfidf.toarray()  # Student model uses TF-IDF only

    targets = [
        [int(label in example.observation_names) for label in labels]
        for example in test_examples
    ]

    probabilities = mlp_model.predict_proba(parity_features).tolist()
    predictions = [[int(val >= threshold) for val in row] for row in probabilities]

    return {
        "micro_f1": round(float(f1_score(targets, predictions, average="micro", zero_division=0)), 4),
        "macro_f1": round(float(f1_score(targets, predictions, average="macro", zero_division=0)), 4),
        "samples_f1": round(float(f1_score(targets, predictions, average="samples", zero_division=0)), 4),
    }


def export_observation_model(model_path: Path, output_path: Path) -> str:
    with model_path.open("rb") as file:
        artifact = pickle.load(file)
        
    vectorizer = artifact["vectorizer"]
    mlp_model = artifact["mlp_model"]
    labels = artifact["labels"]
    threshold = artifact["threshold"]

    # Extract MLP weights from sklearn MLPClassifier
    # The student model always has 2 hidden layers (512, 256) with TF-IDF-only input.
    # coefs_[0] shape: (512, 512)  -- TF-IDF input to hidden1
    # coefs_[1] shape: (512, 256)  -- hidden1 to hidden2
    # coefs_[2] shape: (256, n_classes) -- hidden2 to output
    
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
    
    # Student model is always TF-IDF only — no BERT projection needed

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

    with model_path.open("rb") as f:
        artifact = pickle.load(f)
    
    metadata["metrics"]["held_out_test_tfidf_only"] = evaluate_tfidf_parity(artifact)

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
