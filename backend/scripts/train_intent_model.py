import os
import sys
import time
import random
import pickle

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from config import settings

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import SGDClassifier
    from sklearn.pipeline import Pipeline
except ImportError:
    print("scikit-learn is required. Run: pip install scikit-learn")
    sys.exit(1)

def generate_training_data(total_samples=100000):
    print(f"Generating {total_samples} synthetic training datasets...")
    
    intents_and_templates = {
        "record_vitals": [
            "Patient BP is {num}/{num}",
            "BP {num}/{num}, HR {num}",
            "Patient is very hot, temperature {num}.{num}",
            "Vitals: {num}/{num}",
            "Recorded HR of {num}",
            "Weight is {num} lbs",
            "SpO2 {num}% on room air",
            "respiratory rate {num}"
        ],
        "record_medication": [
            "Gave patient {num}mg {med}",
            "Administered {med} {num}mg",
            "Hold {med}",
            "Skipped {med} dose",
            "Patient refused {med}",
            "Given {med} {num} mcg",
            "med given",
            "administered medication"
        ],
        "query_medications": [
            "What medications are due?",
            "Are there any meds due right now?",
            "Show me the med list",
            "What is scheduled?",
            "Which meds are due?",
            "Meds list for patient",
            "what's due?"
        ],
        "query_vitals": [
            "What are the latest vitals?",
            "Show me current vitals",
            "Get the last vitals",
            "What is the patient's BP?",
            "How is the heart rate?",
            "Latest temp",
            "Current oxygen sat"
        ],
        "query_trends": [
            "Did the patient's blood pressure go up?",
            "Show vitals trend",
            "Compare vitals to yesterday",
            "How is the weight trending?",
            "Has the BP changed?",
            "Trend over time"
        ],
        "summarize": [
            "Give me a quick summary of the patient",
            "Summarize patient status",
            "Brief summary",
            "Quick overview",
            "Patient snapshot",
            "Tell me about this patient"
        ],
        "select_patient": [
            "Select room {num}",
            "Switch to {name}",
            "Open patient {name}",
            "View patient {name}",
            "rm {num}",
            "Select Mr. {name}",
            "room {num}"
        ],
        "command_cancel": [
            "Cancel that",
            "Abort",
            "Undo",
            "Nevermind",
            "Clear",
            "Stop"
        ],
        "command_save": [
            "Save the data",
            "Commit",
            "Submit",
            "Confirm",
            "Done"
        ],
        "command_help": [
            "Help me",
            "How do I use this?",
            "Show commands",
            "?",
            "Help"
        ],
        "unknown": [
            "Tell me a joke",
            "What is the weather?",
            "How do I cook pasta?",
            "Is the patient allergic to anything?",
            "What should I do if the patient complains of severe chest pain?",
            "Generate a shift handoff report",
            "What is the primary diagnosis?",
            "Can you write a poem?",
            "I need a laugh",
            "Explain the pathophysiology of diabetes",
            "Who is the president?",
            "Tell me a story",
            "Does the patient have allergies?",
            "Give me a detailed explanation",
            "I have a general question"
        ]
    }
    
    meds = ["Tylenol", "Metformin", "Lisinopril", "Aspirin", "Ibuprofen", "Morphine", "Zofran", "Lasix"]
    names = ["John", "Doe", "Jane", "Smith", "Bob", "Alice"]
    
    X = []
    y = []
    
    for _ in range(total_samples):
        intent, templates = random.choice(list(intents_and_templates.items()))
        template = random.choice(templates)
        
        # Replace tokens
        text = template.replace("{num}", str(random.randint(10, 200)))
        text = text.replace("{med}", random.choice(meds))
        text = text.replace("{name}", random.choice(names))
        
        X.append(text)
        y.append(intent)
        
    return X, y

def train_model():
    model_path = settings.DATA_DIR / "intent_model.pkl"
    print("Initializing Machine Learning Pipeline...")
    
    start_time = time.time()
    X, y = generate_training_data(100000)
    
    pipeline = Pipeline([
        ('tfidf', TfidfVectorizer(ngram_range=(1, 2))),
        ('clf', SGDClassifier(loss='log_loss', alpha=1e-4, random_state=42, max_iter=50))
    ])
    
    print("Training SGDClassifier on 100,000 datasets...")
    pipeline.fit(X, y)
    
    with open(model_path, 'wb') as f:
        pickle.dump(pipeline, f)
        
    elapsed = time.time() - start_time
    print(f"[SUCCESS] Trained and saved ML Intent Model in {elapsed:.2f} seconds!")
    print(f"Model saved to: {model_path}")
    
    # Test it on a few phrases
    print("\nSanity Check Predictions:")
    tests = ["BP is 120/80", "What meds are due?", "Abort", "Give patient Zofran"]
    preds = pipeline.predict(tests)
    probs = pipeline.predict_proba(tests)
    
    for t, p, prob in zip(tests, preds, probs):
        conf = max(prob)
        print(f"  '{t}' -> {p} (Confidence: {conf:.2%})")

if __name__ == "__main__":
    train_model()
