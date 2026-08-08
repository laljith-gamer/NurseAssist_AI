import re
from typing import Tuple, Optional, Dict, Any
from enum import Enum
from dataclasses import dataclass
import time


class RouteType(Enum):
    DETERMINISTIC_VITALS = "deterministic_vitals"
    DETERMINISTIC_MEDS = "deterministic_meds"
    DETERMINISTIC_PATIENT = "deterministic_patient"
    DETERMINISTIC_COMMAND = "deterministic_command"
    NLP_REQUIRED = "nlp_required"
    LLM_REQUIRED = "llm_required"


@dataclass
class RoutingResult:
    route_type: RouteType
    confidence: float
    extracted_data: Dict[str, Any]
    processing_time_ms: float


class InputRouter:
    def __init__(self):
        self._compile_patterns()
    
    def _compile_patterns(self):
        self.vitals_patterns = {
            "bp": re.compile(
                r"(?:\bbp\b|\bblood\s*pressure\b|b\.p\.?)\s*[:=]?\s*(\d{2,3})\s*[/\\]\s*(\d{2,3})",
                re.IGNORECASE
            ),
            "bp_simple": re.compile(
                r"^(\d{2,3})\s*[/\\]\s*(\d{2,3})$"
            ),
            "hr": re.compile(
                r"(?:\bhr\b|\bheart\s*rate\b|\bpulse\b)\s*[:=]?\s*(\d{2,3})",
                re.IGNORECASE
            ),
            "hr_simple": re.compile(
                r"(?:^|\s)(\d{2,3})\s*(?:bpm|beats)",
                re.IGNORECASE
            ),
            "temp": re.compile(
                r"(?:\btemp\b|\btemperature\b)\s*[:=]?\s*(\d{2,3}(?:\.\d{1,2})?)\s*(?:f|c|fahrenheit|celsius)?",
                re.IGNORECASE
            ),
            "spo2": re.compile(
                r"(?:\bspo2\b|\bsp02\b|\bo2\s*sat\b|\boxygen\b|\bsat\b)\s*[:=]?\s*(\d{2,3})(?:\s*%)?",
                re.IGNORECASE
            ),
            "rr": re.compile(
                r"(?:\brr\b|\bresp\b|\brespiratory\s*rate\b|\bbreaths?\b)\s*[:=]?\s*(\d{1,2})",
                re.IGNORECASE
            ),
            "weight": re.compile(
                r"(?:\bweight\b|\bwt\b)\s*[:=]?\s*(\d{2,3}(?:\.\d{1,2})?)\s*(?:kg|lbs?|pounds?|kilos?)?",
                re.IGNORECASE
            ),
            "height": re.compile(
                r"(?:\bheight\b|\bht\b)\s*[:=]?\s*(\d{2,3}(?:\.\d{1,2})?)\s*(?:cm|m|ft|feet|inches?|in)?",
                re.IGNORECASE
            ),
            "glucose": re.compile(
                r"(?:\bglucose\b|\bsugar\b|\bbs\b|\bblood\s*sugar\b|\bbg\b)\s*[:=]?\s*(\d{2,3})",
                re.IGNORECASE
            ),
        }
        
        self.medication_patterns = {
            "given": re.compile(
                r"(?:gave|given|administered|admin)\s+(.+?)(?:\s+to\s+patient)?$",
                re.IGNORECASE
            ),
            "held": re.compile(
                r"(?:held?|hold|skip(?:ped)?)\s+(.+)",
                re.IGNORECASE
            ),
        }
        
        self.patient_patterns = {
            "select": re.compile(
                r"(?:select|switch\s+to|open|view|show)\s+(?:patient\s+)?(.+)",
                re.IGNORECASE
            ),
            "room": re.compile(
                r"(?:room|rm)\s*[:=]?\s*(\d+[a-z]?)",
                re.IGNORECASE
            ),
        }
        
        self.command_patterns = {
            "save": re.compile(r"^(?:save|commit|done|submit)$", re.IGNORECASE),
            "cancel": re.compile(r"^(?:cancel|abort|undo|clear)$", re.IGNORECASE),
            "help": re.compile(r"^(?:help|\?)$", re.IGNORECASE),
            "list": re.compile(r"^(?:list|show\s+all|ls)$", re.IGNORECASE),
            "status": re.compile(r"^(?:status|current|now)$", re.IGNORECASE),
        }
        
        self.query_indicators = [
            "what", "why", "how", "when", "where", "who",
            "should", "could", "would", "can", "is it", "are there",
            "explain", "tell me", "describe", "summarize", "summary",
            "compare", "trend", "history", "analysis"
        ]
    
    def route(self, text: str) -> RoutingResult:
        start_time = time.perf_counter()
        text = text.strip()
        
        if not text:
            return RoutingResult(
                route_type=RouteType.NLP_REQUIRED,
                confidence=0.0,
                extracted_data={},
                processing_time_ms=0.0
            )
        
        result = self._check_vitals(text)
        if result:
            result.processing_time_ms = (time.perf_counter() - start_time) * 1000
            return result
        
        result = self._check_medications(text)
        if result:
            result.processing_time_ms = (time.perf_counter() - start_time) * 1000
            return result
        
        result = self._check_patient_selection(text)
        if result:
            result.processing_time_ms = (time.perf_counter() - start_time) * 1000
            return result
        
        result = self._check_commands(text)
        if result:
            result.processing_time_ms = (time.perf_counter() - start_time) * 1000
            return result
        
        route_type = self._determine_fallback_route(text)
        
        return RoutingResult(
            route_type=route_type,
            confidence=0.5,
            extracted_data={"original_text": text},
            processing_time_ms=(time.perf_counter() - start_time) * 1000
        )
    
    def _check_vitals(self, text: str) -> Optional[RoutingResult]:
        extracted = {}
        
        for vital_type, pattern in self.vitals_patterns.items():
            match = pattern.search(text)
            if match:
                if vital_type in ("bp", "bp_simple"):
                    extracted["bp"] = {
                        "systolic": int(match.group(1)),
                        "diastolic": int(match.group(2))
                    }
                elif vital_type in ("hr", "hr_simple"):
                    extracted["hr"] = int(match.group(1))
                elif vital_type == "temp":
                    extracted["temp"] = float(match.group(1))
                elif vital_type == "spo2":
                    extracted["spo2"] = float(match.group(1))
                elif vital_type == "rr":
                    extracted["rr"] = int(match.group(1))
                elif vital_type == "weight":
                    extracted["weight"] = float(match.group(1))
                elif vital_type == "height":
                    extracted["height"] = float(match.group(1))
                elif vital_type == "glucose":
                    extracted["glucose"] = int(match.group(1))
        
        if extracted:
            confidence = min(0.99, 0.90 + (len(extracted) * 0.02))
            return RoutingResult(
                route_type=RouteType.DETERMINISTIC_VITALS,
                confidence=confidence,
                extracted_data=extracted,
                processing_time_ms=0.0
            )
        
        return None
    
    def _check_medications(self, text: str) -> Optional[RoutingResult]:
        for action, pattern in self.medication_patterns.items():
            match = pattern.search(text)
            if match:
                return RoutingResult(
                    route_type=RouteType.DETERMINISTIC_MEDS,
                    confidence=0.92,
                    extracted_data={
                        "action": action,
                        "medication": match.group(1).strip()
                    },
                    processing_time_ms=0.0
                )
        return None
    
    def _check_patient_selection(self, text: str) -> Optional[RoutingResult]:
        for sel_type, pattern in self.patient_patterns.items():
            match = pattern.search(text)
            if match:
                return RoutingResult(
                    route_type=RouteType.DETERMINISTIC_PATIENT,
                    confidence=0.95,
                    extracted_data={
                        "selection_type": sel_type,
                        "identifier": match.group(1).strip()
                    },
                    processing_time_ms=0.0
                )
        return None
    
    def _check_commands(self, text: str) -> Optional[RoutingResult]:
        for cmd_type, pattern in self.command_patterns.items():
            if pattern.match(text):
                return RoutingResult(
                    route_type=RouteType.DETERMINISTIC_COMMAND,
                    confidence=0.99,
                    extracted_data={"command": cmd_type},
                    processing_time_ms=0.0
                )
        return None
    
    def _determine_fallback_route(self, text: str) -> RouteType:
        # Route to NLP by default so the ML Intent Classifier can process it.
        # It will fallback to the LLM if the intent is unknown.
        return RouteType.NLP_REQUIRED
