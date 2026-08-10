import os
import sys
import pickle
import json
import hashlib
import zipfile
from datetime import datetime

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from config import settings

def export_model_to_json(pkl_path: str, output_path: str):
    """
    Exports a Scikit-learn TF-IDF/CountVectorizer + SGDClassifier pipeline to JSON.
    Works for both Intent and NER models.
    """
    if not os.path.exists(pkl_path):
        raise FileNotFoundError(f"Model not found at {pkl_path}")
        
    with open(pkl_path, 'rb') as f:
        pipeline = pickle.load(f)
        
    # Get vectorizer (tfidf or count)
    vect = pipeline.steps[0][1]
    clf = pipeline.steps[1][1]
    
    # Handle numpy int32 values in vocabulary
    vocab = {k: int(v) for k, v in vect.vocabulary_.items()}
    
    # Handle both TfidfVectorizer and CountVectorizer
    if hasattr(vect, 'idf_'):
        idf = vect.idf_.tolist()
    else:
        idf = [1.0] * len(vocab) # Dummy IDF for CountVectorizer
        
    coef = clf.coef_.tolist()
    intercept = clf.intercept_.tolist()
    classes = clf.classes_.tolist()
    
    model_data = {
        "type": "sgd_classifier",
        "format_version": 2,
        "vocabulary": vocab,
        "idf": idf,
        "coef": coef,
        "intercept": intercept,
        "classes": classes,
        # This lets every runtime reproduce the vectorizer deliberately rather
        # than guessing from a JSON blob. In particular, the NER model was
        # trained on four whitespace-separated feature tokens per word.
        "preprocessing": {
            "vectorizer": "tfidf" if hasattr(vect, "idf_") else "count",
            "lowercase": bool(getattr(vect, "lowercase", True)),
            "token_pattern": getattr(vect, "token_pattern", None),
            "ngram_range": list(getattr(vect, "ngram_range", (1, 1))),
        },
    }
    
    with open(output_path, 'w') as f:
        json.dump(model_data, f)
        
    return calculate_sha256(output_path)


def calculate_sha256(filepath: str) -> str:
    sha256_hash = hashlib.sha256()
    with open(filepath, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()


def main():
    print("Exporting ML models for mobile inference...")
    
    output_dir = settings.DATA_DIR / "mobile_export"
    os.makedirs(output_dir, exist_ok=True)
    
    intent_pkl_path = settings.DATA_DIR / "intent_model.pkl"
    ner_pkl_path = settings.DATA_DIR / "ner_model.pkl"
    
    intent_json_path = output_dir / "intent.json"
    ner_json_path = output_dir / "ner.json"
    
    try:
        intent_sha = export_model_to_json(intent_pkl_path, intent_json_path)
        print(f"Exported Intent Model -> {intent_json_path.name} (SHA-256: {intent_sha[:8]}...)")
        
        ner_sha = export_model_to_json(ner_pkl_path, ner_json_path)
        print(f"Exported NER Model -> {ner_json_path.name} (SHA-256: {ner_sha[:8]}...)")
        
        version = os.environ.get("MODEL_VERSION", "v1")
        commit_sha = os.environ.get("GITHUB_SHA", "unknown")
        
        metadata = {
            "model_version": version,
            "schema_version": 1,
            "created_at": datetime.utcnow().isoformat(),
            "commit_sha": commit_sha,
            "intent_model": {
                "artifact": "intent.json",
                "sha256": intent_sha
            },
            "ner_model": {
                "artifact": "ner.json",
                "sha256": ner_sha
            },
            "runtime": {
                "android": "dart_native_ml",
                "ios": "dart_native_ml"
            },
            "training": {
                "python_version": sys.version.split()[0],
                "scikit_learn_version": "1.4+"
            },
            "metrics": {}
        }
        
        metadata_path = output_dir / "metadata.json"
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)
            
        zip_filename = output_dir / f"nurseassist-model-{version}.zip"
        with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
            zipf.write(intent_json_path, "intent.json")
            zipf.write(ner_json_path, "ner.json")
            zipf.write(metadata_path, "metadata.json")
            
        print(f"Successfully packaged model update: {zip_filename.name}")
        
    except Exception as e:
        print(f"Export failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
