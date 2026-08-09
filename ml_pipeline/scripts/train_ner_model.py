import os
import sys
import time
import random
import pickle

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from config import settings

try:
    from sklearn.feature_extraction.text import CountVectorizer
    from sklearn.linear_model import SGDClassifier
    from sklearn.pipeline import Pipeline
except ImportError:
    print("scikit-learn is required. Run: pip install scikit-learn")
    sys.exit(1)

def add_noise(text):
    if random.random() < 0.2:
        return text.lower()
    return text

def generate_training_data(total_samples=1000000):
    print(f"Generating {total_samples:,} NER training datasets...")
    
    templates = [
        ("Patient BP is {val}", "VITAL_BP", lambda: f"{random.randint(90, 180)}/{random.randint(60, 110)}"),
        ("BP {val}", "VITAL_BP", lambda: f"{random.randint(90, 180)}/{random.randint(60, 110)}"),
        ("Blood pressure: {val}", "VITAL_BP", lambda: f"{random.randint(90, 180)}/{random.randint(60, 110)}"),
        ("Heart rate {val}", "VITAL_HR", lambda: str(random.randint(50, 120))),
        ("HR is {val} bpm", "VITAL_HR", lambda: str(random.randint(50, 120))),
        ("Pulse {val}", "VITAL_HR", lambda: str(random.randint(50, 120))),
        ("Temperature {val}", "VITAL_TEMP", lambda: str(round(random.uniform(36.0, 40.0), 1))),
        ("Temp is {val} degrees", "VITAL_TEMP", lambda: str(round(random.uniform(36.0, 40.0), 1))),
        ("Patient temp {val}", "VITAL_TEMP", lambda: str(round(random.uniform(36.0, 40.0), 1))),
        ("SpO2 is {val}%", "VITAL_SPO2", lambda: str(random.randint(85, 100))),
        ("Oxygen sat {val}", "VITAL_SPO2", lambda: str(random.randint(85, 100))),
        ("Weight {val} kg", "VITAL_WEIGHT", lambda: str(random.randint(40, 120))),
        ("Gave {val}", "MEDICATION_NAME", lambda: random.choice(["Tylenol", "Metformin", "Lisinopril", "Aspirin", "Ibuprofen", "Morphine", "Zofran", "Lasix"])),
        ("Administered {val}", "MEDICATION_NAME", lambda: random.choice(["Tylenol", "Metformin", "Lisinopril", "Aspirin", "Ibuprofen", "Morphine", "Zofran", "Lasix"])),
        ("Hold {val}", "MEDICATION_NAME", lambda: random.choice(["Tylenol", "Metformin", "Lisinopril", "Aspirin", "Ibuprofen", "Morphine", "Zofran", "Lasix"])),
        ("Summarize {val}", "PATIENT_NAME", lambda: random.choice(["John", "Doe", "Jane", "Smith", "Bob", "Alice"])),
        ("Select room {val}", "PATIENT_ROOM", lambda: str(random.randint(100, 999)))
    ]
    
    # We treat NER as a Token Classification problem.
    # X_tokens = list of feature strings for each token
    # y_tokens = list of labels (O or B-ENTITY)
    X_tokens = []
    y_tokens = []
    
    for _ in range(total_samples):
        template, ent_type, val_func = random.choice(templates)
        val = val_func()
        
        text = template.replace("{val}", val)
        text = add_noise(text)
        
        # Tokenize by space
        words = text.split()
        
        # Find which word(s) is the entity
        for i, w in enumerate(words):
            # Feature extraction
            w_lower = w.lower()
            prev_w = words[i-1].lower() if i > 0 else 'BOS'
            next_w = words[i+1].lower() if i < len(words)-1 else 'EOS'
            is_num = 'T' if any(c.isdigit() for c in w) else 'F'
            
            feature_str = f"W:{w_lower} P:{prev_w} N:{next_w} NUM:{is_num}"
            X_tokens.append(feature_str)
            
            # Labeling
            if val.lower() in w.lower() or w.lower() in val.lower():
                y_tokens.append(ent_type)
            else:
                y_tokens.append("O")
                
    return X_tokens, y_tokens

def train_ner():
    model_path = settings.DATA_DIR / "ner_model.pkl"
    print("Initializing NER ML Pipeline (Token Classification)...")
    
    start_time = time.time()
    
    X_tokens, y_tokens = generate_training_data(1000000)
    
    pipeline = Pipeline([
        # We split by space so each feature is treated as a discrete token
        ('vect', CountVectorizer(token_pattern=r'\S+', max_features=15000, min_df=2)),
        ('clf', SGDClassifier(loss='log_loss', alpha=1e-4, random_state=42, max_iter=20, n_jobs=-1, tol=1e-3))
    ])
    
    print(f"Training SGDClassifier on {len(X_tokens):,} tokens...")
    pipeline.fit(X_tokens, y_tokens)
    
    with open(model_path, 'wb') as f:
        pickle.dump(pipeline, f)
        
    elapsed = time.time() - start_time
    print(f"[SUCCESS] Trained and saved ML NER Model in {elapsed:.2f} seconds!")
    print(f"Model saved to: {model_path}")
    
    # Test
    print("\nSanity Check Predictions:")
    test_sentences = [
        "BP is 120/80",
        "Gave patient Zofran 4mg",
        "Heart rate 85 bpm"
    ]
    
    for text in test_sentences:
        print(f"\nText: '{text}'")
        words = text.split()
        for i, w in enumerate(words):
            w_lower = w.lower()
            prev_w = words[i-1].lower() if i > 0 else 'BOS'
            next_w = words[i+1].lower() if i < len(words)-1 else 'EOS'
            is_num = 'T' if any(c.isdigit() for c in w) else 'F'
            feature_str = f"W:{w_lower} P:{prev_w} N:{next_w} NUM:{is_num}"
            
            pred = pipeline.predict([feature_str])[0]
            if pred != "O":
                print(f"  -> Extracted Entity: {w} (Type: {pred})")

if __name__ == "__main__":
    train_ner()
