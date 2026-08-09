import os
import sys
import json
import pickle
import hashlib
import zipfile
from datetime import datetime

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from config import settings

def export_intent_model(output_dir):
    model_path = settings.DATA_DIR / "intent_model.pkl"
    if not model_path.exists():
        print("Intent model not found. Run train_intent_model.py first.")
        return False
        
    with open(model_path, 'rb') as f:
        pipeline = pickle.load(f)
        
    tfidf = pipeline.named_steps['tfidf']
    clf = pipeline.named_steps['clf']
    
    # Extract TF-IDF data
    vocab = tfidf.vocabulary_
    idf = tfidf.idf_.tolist()
    
    # Extract SGDClassifier data
    coef = clf.coef_.tolist()
    intercept = clf.intercept_.tolist()
    classes = clf.classes_.tolist()
    
    export_data = {
        "type": "tfidf_sgd",
        "version": "1.0",
        "vocabulary": vocab,
        "idf": idf,
        "coef": coef,
        "intercept": intercept,
        "classes": classes
    }
    
    out_path = os.path.join(output_dir, "intent_weights.json")
    with open(out_path, 'w') as f:
        json.dump(export_data, f, indent=2)
        
    print(f"Exported intent model to {out_path}")
    return True

def export_ner_patterns(output_dir):
    # Since exporting a spaCy CNN to Dart is technically prohibitive for native offline execution,
    # we export deterministic regex patterns matching the training semantics.
    patterns = {
        "VITAL_BP": [
            r"Patient BP is (?P<val>\d{2,3}/\d{2,3})",
            r"BP (?P<val>\d{2,3}/\d{2,3})",
            r"Blood pressure: (?P<val>\d{2,3}/\d{2,3})"
        ],
        "VITAL_HR": [
            r"Heart rate (?P<val>\d{2,3})",
            r"HR is (?P<val>\d{2,3}) bpm",
            r"Pulse (?P<val>\d{2,3})"
        ],
        "VITAL_TEMP": [
            r"Temperature (?P<val>\d{2,3}(?:\.\d)?)",
            r"Temp is (?P<val>\d{2,3}(?:\.\d)?) degrees",
            r"Patient temp (?P<val>\d{2,3}(?:\.\d)?)"
        ],
        "VITAL_SPO2": [
            r"SpO2 is (?P<val>\d{2,3})%",
            r"Oxygen sat (?P<val>\d{2,3})"
        ],
        "VITAL_WEIGHT": [
            r"Weight (?P<val>\d{2,3}) kg"
        ],
        "MEDICATION_NAME": [
            r"Gave (?P<val>[A-Za-z]+)",
            r"Administered (?P<val>[A-Za-z]+)",
            r"Hold (?P<val>[A-Za-z]+)"
        ]
    }
    
    export_data = {
        "type": "regex_ner",
        "version": "1.0",
        "patterns": patterns
    }
    
    out_path = os.path.join(output_dir, "ner_patterns.json")
    with open(out_path, 'w') as f:
        json.dump(export_data, f, indent=2)
        
    print(f"Exported NER patterns to {out_path}")
    return True

def generate_sha256(filepath):
    sha256_hash = hashlib.sha256()
    with open(filepath, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

def package_models(version="v1"):
    output_dir = settings.DATA_DIR / "export"
    os.makedirs(output_dir, exist_ok=True)
    
    if not export_intent_model(output_dir): return
    if not export_ner_patterns(output_dir): return
    
    intent_path = os.path.join(output_dir, "intent_weights.json")
    ner_path = os.path.join(output_dir, "ner_patterns.json")
    
    metadata = {
        "model_version": version,
        "schema_version": 1,
        "created_at": datetime.utcnow().isoformat() + "Z",
        "intent_model": {
            "artifact": "intent_weights.json",
            "sha256": generate_sha256(intent_path)
        },
        "ner_model": {
            "artifact": "ner_patterns.json",
            "sha256": generate_sha256(ner_path)
        },
        "runtime": {
            "android": "dart-native",
            "ios": "dart-native"
        }
    }
    
    metadata_path = os.path.join(output_dir, "metadata.json")
    with open(metadata_path, 'w') as f:
        json.dump(metadata, f, indent=2)
        
    zip_path = settings.DATA_DIR / f"nurseassist-model-{version}.zip"
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        zipf.write(intent_path, arcname="intent_weights.json")
        zipf.write(ner_path, arcname="ner_patterns.json")
        zipf.write(metadata_path, arcname="metadata.json")
        
    print(f"\n[SUCCESS] Packaged device inference artifacts to: {zip_path}")
    print(f"Overall ZIP SHA256: {generate_sha256(zip_path)}")

if __name__ == "__main__":
    version = sys.argv[1] if len(sys.argv) > 1 else "v1"
    package_models(version)
