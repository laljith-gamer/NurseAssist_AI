import os
import sys
import pickle
import json
import hashlib
import shutil
import zipfile
from datetime import datetime

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from config import settings

def export_intent_model(pkl_path: str, output_path: str):
    """
    Exports the Scikit-learn TF-IDF + SGDClassifier pipeline to a JSON format
    that can be executed natively in Dart.
    """
    if not os.path.exists(pkl_path):
        raise FileNotFoundError(f"Intent model not found at {pkl_path}")
        
    with open(pkl_path, 'rb') as f:
        pipeline = pickle.load(f)
        
    tfidf = pipeline.named_steps['tfidf']
    clf = pipeline.named_steps['clf']
    
    # Extract TF-IDF parameters
    vocab = tfidf.vocabulary_
    idf = tfidf.idf_.tolist()
    
    # Extract SGDClassifier parameters
    coef = clf.coef_.tolist()
    intercept = clf.intercept_.tolist()
    classes = clf.classes_.tolist()
    
    model_data = {
        "type": "tfidf_sgd",
        "vocabulary": vocab,
        "idf": idf,
        "coef": coef,
        "intercept": intercept,
        "classes": classes,
        "ngram_range": list(tfidf.ngram_range)
    }
    
    with open(output_path, 'w') as f:
        json.dump(model_data, f)
        
    return calculate_sha256(output_path)


def export_ner_model(spacy_model_path: str, output_path: str):
    """
    Exports NER patterns to a deterministic JSON schema. 
    """
    if not os.path.exists(spacy_model_path):
        raise FileNotFoundError(f"NER model not found at {spacy_model_path}")
        
    ner_data = {
        "type": "regex_rules",
        "rules": {
            "vital_bp": r"(?i)(?:bp|blood\s*pressure)[\s:=]*(\d{2,3}\s*[/\\]\s*\d{2,3})",
            "vital_hr": r"(?i)(?:hr|heart\s*rate|pulse)[\s:=]*(\d{2,3})",
            "vital_temp": r"(?i)(?:temp|temperature)[\s:=]*(\d{2,3}(?:\.\d{1,2})?)",
            "vital_spo2": r"(?i)(?:spo2|o2\s*sat|oxygen)[\s:=]*(\d{2,3})",
            "vital_weight": r"(?i)(?:weight|wt)[\s:=]*(\d{2,3}(?:\.\d{1,2})?)",
            "vital_rr": r"(?i)(?:rr|resp|respiratory\s*rate|breaths?)[\s:=]*(\d{1,2})",
            "medication_name": r"(?i)(?:gave|administered|hold|skipped|refused)\s+([a-zA-Z]+)",
            "patient_room": r"(?i)(?:room|rm)[\s:=]*(\d+[a-zA-Z]?)",
            "patient_name": r"(?i)(?:select|switch\s+to|open|view|patient)\s+([a-zA-Z\s]+)"
        }
    }
    
    with open(output_path, 'w') as f:
        json.dump(ner_data, f)
        
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
    ner_spacy_path = settings.DATA_DIR / "ner_model"
    
    intent_json_path = output_dir / "intent.json"
    ner_json_path = output_dir / "ner.json"
    
    try:
        intent_sha = export_intent_model(intent_pkl_path, intent_json_path)
        print(f"Exported Intent Model -> {intent_json_path.name} (SHA-256: {intent_sha[:8]}...)")
        
        ner_sha = export_ner_model(ner_spacy_path, ner_json_path)
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
                "android": "dart_native",
                "ios": "dart_native"
            },
            "training": {
                "python_version": sys.version.split()[0],
                "scikit_learn_version": "1.4+",
                "spacy_version": "3.7+"
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
