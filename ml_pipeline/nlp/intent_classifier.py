import re
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import time
import pickle
import os

from config import settings

class Intent(Enum):
    RECORD_VITALS = "record_vitals"
    RECORD_MEDICATION = "record_medication"
    SELECT_PATIENT = "select_patient"
    QUERY_VITALS = "query_vitals"
    QUERY_MEDICATIONS = "query_medications"
    QUERY_PATIENT_INFO = "query_patient_info"
    QUERY_TRENDS = "query_trends"
    COMMAND_SAVE = "command_save"
    COMMAND_CANCEL = "command_cancel"
    COMMAND_HELP = "command_help"
    COMMAND_LIST = "command_list"
    COMMAND_STATUS = "command_status"
    SUMMARIZE = "summarize"
    COMPARE = "compare"
    ALERT_ACKNOWLEDGE = "alert_acknowledge"
    UNKNOWN = "unknown"

    @classmethod
    def from_string(cls, name: str) -> 'Intent':
        try:
            return cls(name)
        except ValueError:
            try:
                return cls[name.upper()]
            except KeyError:
                return cls.UNKNOWN

@dataclass
class IntentResult:
    intent: Intent
    confidence: float
    sub_intent: Optional[str]
    matched_pattern: Optional[str]
    processing_time_ms: float


class IntentClassifier:
    def __init__(self):
        self.model = None
        self._load_model()
    
    def _load_model(self):
        model_path = settings.DATA_DIR / "intent_model.pkl"
        if os.path.exists(model_path):
            try:
                with open(model_path, 'rb') as f:
                    self.model = pickle.load(f)
                print(f"Loaded ML Intent Model from {model_path}")
            except Exception as e:
                print(f"Failed to load ML Intent Model: {e}")
        else:
            print(f"ML Intent Model not found at {model_path}. Will fallback to unknown.")
    
    def classify(self, text: str, preprocessed: Optional[Dict] = None) -> IntentResult:
        start_time = time.perf_counter()
        text = text.strip()
        
        if not text:
            return IntentResult(
                intent=Intent.UNKNOWN,
                confidence=0.0,
                sub_intent=None,
                matched_pattern=None,
                processing_time_ms=0.0
            )
        
        if self.model is not None:
            try:
                # Use Scikit-Learn Model
                prediction = self.model.predict([text])[0]
                probabilities = self.model.predict_proba([text])[0]
                confidence = float(max(probabilities))
                
                # If confidence is too low, fallback to LLM
                if confidence < 0.4:
                    intent_val = Intent.UNKNOWN
                else:
                    intent_val = Intent.from_string(prediction)
                    
                processing_time = (time.perf_counter() - start_time) * 1000
                
                return IntentResult(
                    intent=intent_val,
                    confidence=confidence,
                    sub_intent=None,
                    matched_pattern="ML_MODEL",
                    processing_time_ms=processing_time
                )
            except Exception as e:
                print(f"Error during ML prediction: {e}")
                
        # Fallback to LLM if ML fails or confidence is too low
        return IntentResult(
            intent=Intent.UNKNOWN,
            confidence=0.0,
            sub_intent=None,
            matched_pattern=None,
            processing_time_ms=(time.perf_counter() - start_time) * 1000
        )
        
    def update_model(self, text: str, correct_intent: str) -> bool:
        """
        Online Reinforcement Learning: Adjust the SGDClassifier weights live.
        """
        if self.model is None:
            return False
            
        try:
            # The pipeline is TfidfVectorizer -> SGDClassifier
            # We must transform the text, then partial_fit the classifier
            tfidf = self.model.named_steps['tfidf']
            clf = self.model.named_steps['clf']
            
            X_new = tfidf.transform([text])
            clf.partial_fit(X_new, [correct_intent])
            
            # Save the updated weights back to disk
            model_path = settings.DATA_DIR / "intent_model.pkl"
            with open(model_path, 'wb') as f:
                import pickle
                pickle.dump(self.model, f)
                
            print(f"RL Update: Trained IntentModel on '{text}' -> {correct_intent}")
            return True
        except Exception as e:
            print(f"Failed RL update for Intent: {e}")
            return False