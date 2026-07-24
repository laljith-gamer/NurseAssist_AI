import re
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import time


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


@dataclass
class IntentResult:
    intent: Intent
    confidence: float
    sub_intent: Optional[str]
    matched_pattern: Optional[str]
    processing_time_ms: float


class IntentClassifier:
    def __init__(self):
        self._compile_patterns()
        self.intent_keywords = self._load_intent_keywords()
    
    def _compile_patterns(self):
        self.patterns = {
            Intent.RECORD_VITALS: [
                re.compile(r"^\d{2,3}\s*[/\\]\s*\d{2,3}$"),
                re.compile(r"(?:bp|blood\s*pressure)\s*[:=]?\s*\d{2,3}\s*[/\\]\s*\d{2,3}", re.I),
                re.compile(r"(?:hr|heart\s*rate|pulse)\s*[:=]?\s*\d{2,3}", re.I),
                re.compile(r"(?:temp|temperature)\s*[:=]?\s*\d{2,3}(?:\.\d)?", re.I),
                re.compile(r"(?:spo2|sp02|o2\s*sat|oxygen)\s*[:=]?\s*\d{2,3}", re.I),
                re.compile(r"(?:rr|resp|respiratory)\s*[:=]?\s*\d{1,2}", re.I),
                re.compile(r"(?:weight|wt)\s*[:=]?\s*\d{2,3}(?:\.\d)?", re.I),
                re.compile(r"(?:glucose|sugar|bs|bg)\s*[:=]?\s*\d{2,3}", re.I),
                re.compile(r"vitals?\s+(?:are|is|:)", re.I),
                re.compile(r"record(?:ed|ing)?\s+vitals?", re.I),
            ],
            Intent.RECORD_MEDICATION: [
                re.compile(r"(?:gave|given|administered|admin)\s+\w+", re.I),
                re.compile(r"(?:held?|hold|skip(?:ped)?)\s+\w+", re.I),
                re.compile(r"\w+\s+(?:given|administered)", re.I),
                re.compile(r"(?:med|medication)\s+(?:given|administered)", re.I),
                re.compile(r"(?:dose|dosage)\s+(?:given|administered)", re.I),
            ],
            Intent.SELECT_PATIENT: [
                re.compile(r"(?:select|switch\s+to|open|view)\s+(?:patient\s+)?\w+", re.I),
                re.compile(r"(?:room|rm)\s*[:=]?\s*\d+[a-z]?", re.I),
                re.compile(r"patient\s+\w+", re.I),
                re.compile(r"mrn\s*[:=]?\s*\w+", re.I),
            ],
            Intent.QUERY_VITALS: [
                re.compile(r"(?:what|show|get|display)\s+(?:are\s+)?(?:the\s+)?(?:current\s+)?vitals?", re.I),
                re.compile(r"(?:what|how)\s+(?:is|are)\s+(?:the\s+)?(?:bp|blood\s*pressure|hr|heart\s*rate|temp|temperature)", re.I),
                re.compile(r"(?:latest|last|recent)\s+vitals?", re.I),
                re.compile(r"vitals?\s+(?:for|of)", re.I),
            ],
            Intent.QUERY_MEDICATIONS: [
                re.compile(r"(?:what|show|list|get)\s+(?:are\s+)?(?:the\s+)?(?:current\s+)?(?:meds?|medications?)", re.I),
                re.compile(r"(?:meds?|medications?)\s+(?:due|list|for)", re.I),
                re.compile(r"(?:what|which)\s+(?:meds?|medications?)\s+(?:is|are)\s+(?:due|scheduled)", re.I),
                re.compile(r"(?:due|scheduled)\s+(?:meds?|medications?)", re.I),
                re.compile(r"(?:med|medication)\s+(?:schedule|list)", re.I),
            ],
            Intent.QUERY_PATIENT_INFO: [
                re.compile(r"(?:what|show|get|tell\s+me)\s+(?:about\s+)?(?:the\s+)?patient", re.I),
                re.compile(r"patient\s+(?:info|information|details|summary)", re.I),
                re.compile(r"(?:who\s+is|tell\s+me\s+about)\s+(?:this\s+)?patient", re.I),
                re.compile(r"(?:allergies?|diagnosis|age|history)\s+(?:for|of)?", re.I),
            ],
            Intent.QUERY_TRENDS: [
                re.compile(r"(?:show|what|how)\s+(?:is|are)\s+(?:the\s+)?trends?", re.I),
                re.compile(r"(?:bp|vitals?|weight)\s+(?:trend|history|over\s+time)", re.I),
                re.compile(r"(?:compare|comparison)\s+(?:with|to)\s+(?:yesterday|last\s+week|baseline)", re.I),
                re.compile(r"(?:how\s+has|has)\s+(?:bp|weight|vitals?)\s+(?:changed|trended)", re.I),
            ],
            Intent.COMMAND_SAVE: [
                re.compile(r"^(?:save|commit|done|submit|confirm)$", re.I),
            ],
            Intent.COMMAND_CANCEL: [
                re.compile(r"^(?:cancel|abort|undo|clear|nevermind|never\s+mind)$", re.I),
            ],
            Intent.COMMAND_HELP: [
                re.compile(r"^(?:help|\?|commands?|how\s+to)$", re.I),
                re.compile(r"(?:what\s+can\s+(?:you|i)\s+(?:do|say)|how\s+(?:do\s+i|to))", re.I),
            ],
            Intent.COMMAND_LIST: [
                re.compile(r"^(?:list|show\s+all|ls)$", re.I),
                re.compile(r"(?:list|show)\s+(?:all\s+)?patients?", re.I),
            ],
            Intent.COMMAND_STATUS: [
                re.compile(r"^(?:status|current|now)$", re.I),
                re.compile(r"(?:current|patient)\s+status", re.I),
            ],
            Intent.SUMMARIZE: [
                re.compile(r"(?:summarize|summary|overview|recap)", re.I),
                re.compile(r"(?:give|provide)\s+(?:me\s+)?(?:a\s+)?summary", re.I),
                re.compile(r"(?:what|how)\s+(?:happened|occurred)\s+(?:today|this\s+shift)", re.I),
            ],
            Intent.COMPARE: [
                re.compile(r"(?:compare|difference|vs|versus)", re.I),
                re.compile(r"(?:how\s+does|does)\s+\w+\s+compare", re.I),
                re.compile(r"(?:change|changed)\s+(?:from|since|compared\s+to)", re.I),
            ],
            Intent.ALERT_ACKNOWLEDGE: [
                re.compile(r"(?:acknowledge|ack|dismiss|noted|seen)\s+(?:alert|warning)?", re.I),
                re.compile(r"(?:i\s+)?(?:see|saw|noticed)\s+(?:the\s+)?(?:alert|warning)", re.I),
            ],
        }
    
    def _load_intent_keywords(self) -> Dict[Intent, List[str]]:
        return {
            Intent.RECORD_VITALS: [
                "vitals", "bp", "blood pressure", "heart rate", "hr", "pulse",
                "temperature", "temp", "spo2", "oxygen", "respiratory", "weight"
            ],
            Intent.RECORD_MEDICATION: [
                "gave", "given", "administered", "medication", "med", "dose",
                "held", "hold", "skip", "skipped"
            ],
            Intent.SELECT_PATIENT: [
                "select", "switch", "patient", "room", "mrn", "open", "view"
            ],
            Intent.QUERY_VITALS: [
                "what", "show", "current", "latest", "vitals", "readings"
            ],
            Intent.QUERY_MEDICATIONS: [
                "medications", "meds", "due", "scheduled", "list"
            ],
            Intent.QUERY_PATIENT_INFO: [
                "who", "patient", "info", "information", "allergies", "diagnosis"
            ],
            Intent.QUERY_TRENDS: [
                "trend", "trends", "history", "over time", "compare", "changed"
            ],
            Intent.SUMMARIZE: [
                "summarize", "summary", "overview", "recap", "happened"
            ],
            Intent.COMPARE: [
                "compare", "comparison", "versus", "vs", "difference"
            ],
        }
    
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
        
        result = self._pattern_match(text)
        if result and result.confidence >= 0.9:
            result.processing_time_ms = (time.perf_counter() - start_time) * 1000
            return result
        
        keyword_result = self._keyword_match(text)
        
        if result and keyword_result:
            if keyword_result.confidence > result.confidence:
                result = keyword_result
        elif keyword_result:
            result = keyword_result
        
        if not result or result.confidence < 0.5:
            result = self._fallback_classification(text)
        
        result.processing_time_ms = (time.perf_counter() - start_time) * 1000
        return result
    
    def _pattern_match(self, text: str) -> Optional[IntentResult]:
        best_match = None
        best_confidence = 0.0
        
        for intent, patterns in self.patterns.items():
            for pattern in patterns:
                match = pattern.search(text)
                if match:
                    match_ratio = len(match.group(0)) / len(text)
                    confidence = 0.85 + (match_ratio * 0.14)
                    
                    if confidence > best_confidence:
                        best_confidence = confidence
                        best_match = IntentResult(
                            intent=intent,
                            confidence=min(0.99, confidence),
                            sub_intent=self._detect_sub_intent(intent, text),
                            matched_pattern=pattern.pattern,
                            processing_time_ms=0.0
                        )
        
        return best_match
    
    def _keyword_match(self, text: str) -> Optional[IntentResult]:
        text_lower = text.lower()
        words = set(text_lower.split())
        
        best_intent = None
        best_score = 0.0
        
        for intent, keywords in self.intent_keywords.items():
            matches = 0
            for keyword in keywords:
                if keyword in text_lower:
                    matches += 1
            
            if matches > 0:
                score = matches / len(keywords)
                if score > best_score:
                    best_score = score
                    best_intent = intent
        
        if best_intent and best_score > 0.1:
            return IntentResult(
                intent=best_intent,
                confidence=min(0.85, 0.5 + best_score * 0.4),
                sub_intent=self._detect_sub_intent(best_intent, text),
                matched_pattern=None,
                processing_time_ms=0.0
            )
        
        return None
    
    def _fallback_classification(self, text: str) -> IntentResult:
        text_lower = text.lower()
        
        if re.search(r"\d{2,3}\s*[/\\]\s*\d{2,3}", text):
            return IntentResult(
                intent=Intent.RECORD_VITALS,
                confidence=0.75,
                sub_intent="blood_pressure",
                matched_pattern=None,
                processing_time_ms=0.0
            )
        
        if text.endswith("?") or text_lower.startswith(("what", "how", "why", "when", "where", "who")):
            return IntentResult(
                intent=Intent.QUERY_PATIENT_INFO,
                confidence=0.5,
                sub_intent=None,
                matched_pattern=None,
                processing_time_ms=0.0
            )
        
        if any(word in text_lower for word in ["gave", "given", "take", "took"]):
            return IntentResult(
                intent=Intent.RECORD_MEDICATION,
                confidence=0.6,
                sub_intent="administration",
                matched_pattern=None,
                processing_time_ms=0.0
            )
        
        return IntentResult(
            intent=Intent.UNKNOWN,
            confidence=0.3,
            sub_intent=None,
            matched_pattern=None,
            processing_time_ms=0.0
        )
    
    def _detect_sub_intent(self, intent: Intent, text: str) -> Optional[str]:
        text_lower = text.lower()
        
        if intent == Intent.RECORD_VITALS:
            if "bp" in text_lower or "blood pressure" in text_lower or re.search(r"\d+[/\\]\d+", text):
                return "blood_pressure"
            if "hr" in text_lower or "heart rate" in text_lower or "pulse" in text_lower:
                return "heart_rate"
            if "temp" in text_lower:
                return "temperature"
            if "spo2" in text_lower or "oxygen" in text_lower:
                return "oxygen_saturation"
            if "weight" in text_lower or "wt" in text_lower:
                return "weight"
            if "glucose" in text_lower or "sugar" in text_lower:
                return "glucose"
            return "multiple"
        
        if intent == Intent.RECORD_MEDICATION:
            if "gave" in text_lower or "given" in text_lower:
                return "administration"
            if "held" in text_lower or "hold" in text_lower:
                return "hold"
            if "skip" in text_lower:
                return "skip"
            return "administration"
        
        if intent == Intent.QUERY_MEDICATIONS:
            if "due" in text_lower:
                return "due_medications"
            if "schedule" in text_lower:
                return "schedule"
            return "list"
        
        return None
    
    def get_all_intents(self) -> List[Dict]:
        return [
            {
                "intent": intent.value,
                "description": self._get_intent_description(intent)
            }
            for intent in Intent
        ]
    
    def _get_intent_description(self, intent: Intent) -> str:
        descriptions = {
            Intent.RECORD_VITALS: "Record patient vital signs",
            Intent.RECORD_MEDICATION: "Record medication administration",
            Intent.SELECT_PATIENT: "Select or switch patient",
            Intent.QUERY_VITALS: "Query current or historical vitals",
            Intent.QUERY_MEDICATIONS: "Query medication information",
            Intent.QUERY_PATIENT_INFO: "Query patient information",
            Intent.QUERY_TRENDS: "Query trends and comparisons",
            Intent.COMMAND_SAVE: "Save pending changes",
            Intent.COMMAND_CANCEL: "Cancel current operation",
            Intent.COMMAND_HELP: "Get help information",
            Intent.COMMAND_LIST: "List items",
            Intent.COMMAND_STATUS: "Get current status",
            Intent.SUMMARIZE: "Get summary of patient or shift",
            Intent.COMPARE: "Compare values over time",
            Intent.ALERT_ACKNOWLEDGE: "Acknowledge an alert",
            Intent.UNKNOWN: "Unrecognized intent",
        }
        return descriptions.get(intent, "Unknown intent")