import os
import spacy
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from enum import Enum

from config import settings


class EntityType(Enum):
    VITAL_BP = "vital_bp"
    VITAL_HR = "vital_hr"
    VITAL_TEMP = "vital_temp"
    VITAL_SPO2 = "vital_spo2"
    VITAL_RR = "vital_rr"
    VITAL_WEIGHT = "vital_weight"
    VITAL_HEIGHT = "vital_height"
    VITAL_GLUCOSE = "vital_glucose"
    MEDICATION_NAME = "medication_name"
    MEDICATION_DOSE = "medication_dose"
    MEDICATION_ROUTE = "medication_route"
    MEDICATION_FREQUENCY = "medication_frequency"
    PATIENT_NAME = "patient_name"
    PATIENT_ROOM = "patient_room"
    PATIENT_MRN = "patient_mrn"
    TIME_REFERENCE = "time_reference"
    DATE_REFERENCE = "date_reference"
    DURATION = "duration"
    NUMERIC_VALUE = "numeric_value"
    BODY_PART = "body_part"
    SYMPTOM = "symptom"
    CONDITION = "condition"


@dataclass
class Entity:
    entity_type: EntityType
    value: Any
    raw_text: str
    start: int
    end: int
    confidence: float
    unit: Optional[str] = None
    normalized_value: Optional[Any] = None


@dataclass
class ExtractionResult:
    entities: List[Entity]
    vitals: Dict[str, Any]
    medications: Dict[str, Any]
    patient_identifiers: Dict[str, Any]
    time_references: List[Dict]
    unmatched_text: str


class EntityExtractor:
    def __init__(self):
        self.nlp = None
        self._load_model()
    
    def _load_model(self):
        model_path = settings.DATA_DIR / "ner_model"
        if os.path.exists(model_path):
            try:
                self.nlp = spacy.load(model_path)
                print(f"Loaded ML NER Model from {model_path}")
            except Exception as e:
                print(f"Failed to load ML NER Model: {e}")
        else:
            print(f"ML NER Model not found at {model_path}")
    
    def extract(self, text: str) -> ExtractionResult:
        entities = []
        vitals = {}
        medications = {}
        patient_identifiers = {}
        time_references = []
        
        if self.nlp:
            doc = self.nlp(text)
            for ent in doc.ents:
                try:
                    # Attempt to map to Enum, fallback if missing
                    try:
                        ent_type = EntityType(ent.label_.lower())
                    except ValueError:
                        try:
                            ent_type = EntityType[ent.label_]
                        except KeyError:
                            continue # Skip unknown labels
                    
                    entity = Entity(
                        entity_type=ent_type,
                        value=ent.text,
                        raw_text=ent.text,
                        start=ent.start_char,
                        end=ent.end_char,
                        confidence=0.99
                    )
                    entities.append(entity)
                    
                    if "VITAL" in ent.label_:
                        vital_key = ent.label_.lower().replace("vital_", "")
                        if vital_key == "bp" and "/" in ent.text:
                            parts = ent.text.split("/")
                            vitals["bp"] = {"systolic": int(parts[0]), "diastolic": int(parts[1])}
                        else:
                            vitals[vital_key] = ent.text
                    elif "MEDICATION" in ent.label_:
                        medications[ent.label_.lower().replace("medication_", "")] = ent.text
                    elif "PATIENT" in ent.label_:
                        patient_identifiers[ent.label_.lower().replace("patient_", "")] = ent.text
                        
                except Exception as e:
                    print(f"Error extracting entity: {e}")
        
        # Determine unmatched text
        matched_spans = set()
        for entity in entities:
            for i in range(entity.start, entity.end):
                matched_spans.add(i)
        
        unmatched_chars = []
        for i, char in enumerate(text):
            if i not in matched_spans:
                unmatched_chars.append(char)
        unmatched_text = "".join(unmatched_chars).strip()
        
        return ExtractionResult(
            entities=entities,
            vitals=vitals,
            medications=medications,
            patient_identifiers=patient_identifiers,
            time_references=time_references,
            unmatched_text=unmatched_text
        )

    def update_model(self, text: str, entity_label: str, start_idx: int, end_idx: int) -> bool:
        """
        Online Reinforcement Learning: Adjust the spaCy deep learning weights live.
        """
        from spacy.training.example import Example
        if self.nlp is None:
            return False
            
        try:
            # We must resume training to update gradients
            optimizer = self.nlp.resume_training()
            
            doc = self.nlp.make_doc(text)
            annotations = {"entities": [(start_idx, end_idx, entity_label)]}
            example = Example.from_dict(doc, annotations)
            
            self.nlp.update([example], sgd=optimizer)
            
            # Save updated weights
            model_path = settings.DATA_DIR / "ner_model"
            self.nlp.to_disk(model_path)
            
            print(f"RL Update: Trained NER Model on '{text[start_idx:end_idx]}' -> {entity_label}")
            return True
        except Exception as e:
            print(f"Failed RL update for NER: {e}")
            return False