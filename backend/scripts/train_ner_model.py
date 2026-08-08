import os
import sys
import random
import spacy
from spacy.training.example import Example
import warnings
warnings.filterwarnings("ignore")

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from config import settings

def generate_training_data(num_samples=1000):
    print(f"Generating {num_samples} NER training datasets...")
    
    TRAIN_DATA = []
    
    templates = [
        ("Patient BP is {val}", "VITAL_BP"),
        ("BP {val}", "VITAL_BP"),
        ("Blood pressure: {val}", "VITAL_BP"),
        ("Heart rate {val}", "VITAL_HR"),
        ("HR is {val} bpm", "VITAL_HR"),
        ("Pulse {val}", "VITAL_HR"),
        ("Temperature {val}", "VITAL_TEMP"),
        ("Temp is {val} degrees", "VITAL_TEMP"),
        ("Patient temp {val}", "VITAL_TEMP"),
        ("SpO2 is {val}%", "VITAL_SPO2"),
        ("Oxygen sat {val}", "VITAL_SPO2"),
        ("Weight {val} kg", "VITAL_WEIGHT"),
        ("Gave {val}", "MEDICATION_NAME"),
        ("Administered {val}", "MEDICATION_NAME"),
        ("Hold {val}", "MEDICATION_NAME")
    ]
    
    meds = ["Tylenol", "Metformin", "Lisinopril", "Aspirin", "Ibuprofen", "Morphine", "Zofran", "Lasix"]
    
    for _ in range(num_samples):
        template, ent_type = random.choice(templates)
        
        if "BP" in ent_type:
            val = f"{random.randint(90, 180)}/{random.randint(60, 110)}"
        elif "HR" in ent_type:
            val = str(random.randint(50, 120))
        elif "TEMP" in ent_type:
            val = str(round(random.uniform(36.0, 40.0), 1))
        elif "SPO2" in ent_type:
            val = str(random.randint(85, 100))
        elif "WEIGHT" in ent_type:
            val = str(random.randint(40, 120))
        elif "MEDICATION" in ent_type:
            val = random.choice(meds)
        else:
            val = str(random.randint(10, 50))
            
        text = template.replace("{val}", val)
        start_idx = text.find(val)
        end_idx = start_idx + len(val)
        
        TRAIN_DATA.append((text, {"entities": [(start_idx, end_idx, ent_type)]}))
        
    return TRAIN_DATA

def train_ner():
    output_dir = settings.DATA_DIR / "ner_model"
    
    # Create blank English model
    nlp = spacy.blank("en")
    
    # Create NER pipeline
    if "ner" not in nlp.pipe_names:
        ner = nlp.add_pipe("ner", last=True)
    else:
        ner = nlp.get_pipe("ner")
        
    TRAIN_DATA = generate_training_data(2000)
    
    # Add labels to NER
    for _, annotations in TRAIN_DATA:
        for ent in annotations.get("entities"):
            ner.add_label(ent[2])
            
    print("Training Deep Learning NER Model (this may take a moment)...")
    
    # Disable other pipes during training
    pipe_exceptions = ["ner", "trf_wordpiecer", "trf_tok2vec"]
    other_pipes = [pipe for pipe in nlp.pipe_names if pipe not in pipe_exceptions]
    
    with nlp.disable_pipes(*other_pipes):
        optimizer = nlp.begin_training()
        for itn in range(10): # 10 iterations
            random.shuffle(TRAIN_DATA)
            losses = {}
            for text, annotations in TRAIN_DATA:
                doc = nlp.make_doc(text)
                example = Example.from_dict(doc, annotations)
                nlp.update([example], drop=0.5, sgd=optimizer, losses=losses)
            print(f"Iteration {itn+1}/10 - Losses: {losses}")
            
    # Save the model
    nlp.to_disk(output_dir)
    print(f"[SUCCESS] Saved ML NER Model to {output_dir}")
    
    # Test the model
    print("\nSanity Check Predictions:")
    test_texts = ["BP is 120/80 and heart rate is 85", "Patient temperature 38.5 degrees", "Administered Zofran 4mg"]
    for text in test_texts:
        doc = nlp(text)
        print(f"Text: '{text}'")
        for ent in doc.ents:
            print(f"  -> Extracted Entity: {ent.text} (Type: {ent.label_})")

if __name__ == "__main__":
    train_ner()
