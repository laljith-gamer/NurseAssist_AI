"""Export the real-data SYNUR advisory model for deterministic Dart inference."""

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
    if len(estimators) != len(labels):
        raise ValueError("Observation model estimators and labels do not match")

    payload = {
        "type": "multi_label_sgd_classifier",
        "format_version": 1,
        "role": "advisory_clinical_observation_context",
        "vocabulary": {key: int(value) for key, value in vectorizer.vocabulary_.items()},
        "idf": vectorizer.idf_.tolist(),
        "coef": [estimator.coef_[0].tolist() for estimator in estimators],
        "intercept": [float(estimator.intercept_[0]) for estimator in estimators],
        "classes": labels,
        "threshold": float(threshold),
        "preprocessing": {
            "lowercase": True,
            "analyzer": "char_wb",
            "ngram_range": [3, 6],
            "vectorizer": "tfidf_l2",
        },
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
        },
        "metrics": {
            "validation": metrics["selection"]["dev_metrics"],
            "held_out_test": metrics["held_out_test"],
            "selected_labels": metrics["selection"]["labels"],
            "limitations": metrics["limitations"],
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
