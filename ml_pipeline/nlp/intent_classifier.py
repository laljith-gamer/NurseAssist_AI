import re
import time
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum


class Intent(Enum):
    RECORD_VITALS = "record_vitals"
    RECORD_MEDICATION = "record_medication"
    SELECT_PATIENT = "select_patient"
    QUERY_VITALS = "query_vitals"
    QUERY_MEDICATIONS = "query_medications"
    QUERY_TRENDS = "query_trends"
    COMMAND_SAVE = "command_save"
    COMMAND_CANCEL = "command_cancel"
    COMMAND_HELP = "command_help"
    SUMMARIZE = "summarize"
    GREETING = "greeting"
    UNKNOWN = "unknown"

    @classmethod
    def from_string(cls, name: str) -> "Intent":
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


_RULES: List[Tuple[Intent, "re.Pattern"]] = [
    (Intent.COMMAND_CANCEL, re.compile(r"^(cancel|abort|undo|nevermind|clear|stop)\b", re.IGNORECASE)),
    (Intent.COMMAND_SAVE, re.compile(r"^(save|commit|submit|confirm|done)\b", re.IGNORECASE)),
    (Intent.COMMAND_HELP, re.compile(r"^(help|\?|how do i use this)\b", re.IGNORECASE)),
    (Intent.GREETING, re.compile(r"^(hi|hello|hey|good morning|good afternoon|greetings)\b", re.IGNORECASE)),
    (Intent.SELECT_PATIENT, re.compile(r"\b(select|switch to|open patient|view patient|room)\s+\S", re.IGNORECASE)),
    (Intent.RECORD_MEDICATION, re.compile(r"\b(gave|administered|hold|held|discontinue[d]?|refused)\b.*\b(mg|mcg|units?|tylenol|metformin|lisinopril|aspirin|ibuprofen|morphine|zofran|lasix|heparin|insulin|propofol)\b", re.IGNORECASE)),
    (Intent.RECORD_VITALS, re.compile(r"\b(bp|blood pressure|hr|heart rate|temp(?:erature)?|spo2|sp02|oxygen sat(?:uration)?|pulse|respiratory rate|weight)\b.*\d", re.IGNORECASE)),
    (Intent.RECORD_VITALS, re.compile(r"\b\d{2,3}\s*/\s*\d{2,3}\b")),
    (Intent.QUERY_TRENDS, re.compile(r"\b(trend|go up|go down|changed|compare|yesterday)\b", re.IGNORECASE)),
    (Intent.QUERY_MEDICATIONS, re.compile(r"\b(med|meds|medication)s?\b.*\b(due|scheduled|list)\b", re.IGNORECASE)),
    (Intent.QUERY_VITALS, re.compile(r"\b(latest|current|last)\b.*\b(vitals?|bp|hr|temp|spo2)\b", re.IGNORECASE)),
    (Intent.SUMMARIZE, re.compile(r"\b(summar(y|ize|ise)|overview|snapshot|handoff|brief)\b", re.IGNORECASE)),
]


class IntentClassifier:
    """Deterministic, rule-based intent classifier.

    The prior version loaded an SGDClassifier trained on ~1,000,000 sentences
    generated from hand-written templates with random substitutions, with no
    held-out evaluation set. That is not a validated model -- it is
    indistinguishable from a rule-based system in terms of evidence of
    quality, but presented itself as one. This implementation replaces it
    with the same effective capability (pattern matching) stated honestly,
    so accuracy claims are not implied where none were measured.
    """

    def classify(self, text: str, preprocessed: Optional[Dict] = None) -> IntentResult:
        start_time = time.perf_counter()
        stripped = text.strip()

        if not stripped:
            return IntentResult(
                intent=Intent.UNKNOWN,
                confidence=0.0,
                sub_intent=None,
                matched_pattern=None,
                processing_time_ms=(time.perf_counter() - start_time) * 1000,
            )

        for intent, pattern in _RULES:
            match = pattern.search(stripped)
            if match:
                return IntentResult(
                    intent=intent,
                    confidence=1.0,
                    sub_intent=None,
                    matched_pattern=match.group(0),
                    processing_time_ms=(time.perf_counter() - start_time) * 1000,
                )

        return IntentResult(
            intent=Intent.UNKNOWN,
            confidence=0.0,
            sub_intent=None,
            matched_pattern=None,
            processing_time_ms=(time.perf_counter() - start_time) * 1000,
        )
