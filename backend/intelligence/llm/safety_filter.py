from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from enum import Enum
import re


class SafetyLevel(Enum):
    SAFE = "safe"
    CAUTION = "caution"
    BLOCKED = "blocked"


@dataclass
class SafetyCheckResult:
    level: SafetyLevel
    passed: bool
    concerns: List[str]
    modified_content: Optional[str]
    requires_review: bool


class SafetyFilter:
    def __init__(self):
        self.blocked_patterns = self._load_blocked_patterns()
        self.caution_patterns = self._load_caution_patterns()
        self.medical_disclaimers = self._load_disclaimers()
    
    def _load_blocked_patterns(self) -> List[re.Pattern]:
        patterns = [
            r"(?i)\b(kill|suicide|self[- ]?harm|end\s+(?:my|your|their)\s+life)\b",
            r"(?i)\b(overdose|od)\s+(?:on|with)\b",
            r"(?i)\bhow\s+to\s+(?:die|hurt\s+(?:myself|yourself|someone))\b",
            r"(?i)\b(poison|poisoning)\s+(?:someone|patient)\b",
            r"(?i)\blethal\s+(?:dose|injection|amount)\b",
            r"(?i)\beuthan(?:ize|asia)\b(?!\s+(?:pet|animal))",
        ]
        return [re.compile(p) for p in patterns]
    
    def _load_caution_patterns(self) -> List[Tuple[re.Pattern, str]]:
        patterns = [
            (r"(?i)\bstop\s+(?:taking|all)\s+medications?\b", 
             "Medication changes should be discussed with the physician"),
            (r"(?i)\bdouble\s+(?:the\s+)?dose\b",
             "Dose adjustments require physician approval"),
            (r"(?i)\b(?:don'?t|do\s+not)\s+(?:give|administer)\s+(?:any\s+)?(?:more\s+)?medications?\b",
             "Medication decisions require clinical judgment"),
            (r"(?i)\bdiagnos(?:e|is)\s+(?:this|the)\s+patient\s+with\b",
             "Diagnoses must be made by qualified physicians"),
            (r"(?i)\bprescribe\b",
             "Prescribing authority is limited to licensed providers"),
            (r"(?i)\bchange\s+(?:the\s+)?code\s+status\b",
             "Code status changes require physician order and patient/family consent"),
            (r"(?i)\bdischarge\s+(?:the\s+)?patient\b",
             "Discharge decisions require physician authorization"),
        ]
        return [(re.compile(p), msg) for p, msg in patterns]
    
    def _load_disclaimers(self) -> Dict[str, str]:
        return {
            "medication": "Always verify medications with the pharmacy and check for interactions.",
            "diagnosis": "This information is for reference only. Clinical diagnosis requires physician evaluation.",
            "treatment": "Treatment recommendations should be verified with the attending physician.",
            "emergency": "For emergencies, activate rapid response or call emergency services immediately.",
            "vitals": "Critical vital signs require immediate clinical assessment.",
            "general": "This AI assistant provides support information only. Clinical decisions require professional judgment."
        }
    
    def check_input(self, text: str) -> SafetyCheckResult:
        concerns = []
        
        for pattern in self.blocked_patterns:
            if pattern.search(text):
                return SafetyCheckResult(
                    level=SafetyLevel.BLOCKED,
                    passed=False,
                    concerns=["Input contains prohibited content"],
                    modified_content=None,
                    requires_review=True
                )
        
        for pattern, message in self.caution_patterns:
            if pattern.search(text):
                concerns.append(message)
        
        if concerns:
            return SafetyCheckResult(
                level=SafetyLevel.CAUTION,
                passed=True,
                concerns=concerns,
                modified_content=None,
                requires_review=True
            )
        
        return SafetyCheckResult(
            level=SafetyLevel.SAFE,
            passed=True,
            concerns=[],
            modified_content=None,
            requires_review=False
        )
    
    def check_output(self, text: str, context: Optional[str] = None) -> SafetyCheckResult:
        concerns = []
        modified = text
        
        for pattern in self.blocked_patterns:
            if pattern.search(text):
                return SafetyCheckResult(
                    level=SafetyLevel.BLOCKED,
                    passed=False,
                    concerns=["Output contains prohibited content"],
                    modified_content="I cannot provide that information. Please consult with the healthcare team.",
                    requires_review=True
                )
        
        dangerous_advice = [
            (r"(?i)you\s+should\s+(?:stop|discontinue)\s+(?:taking\s+)?(?:all\s+)?(?:your\s+)?medications?",
             "Always consult with your healthcare provider before making medication changes."),
            (r"(?i)(?:this|the)\s+patient\s+(?:has|definitely\s+has|is\s+diagnosed\s+with)\s+\w+",
             "Note: This is an AI assessment. Official diagnosis requires physician evaluation."),
            (r"(?i)administer\s+\d+\s*(?:mg|mcg|units?|ml)",
             "Verify dosing with pharmacy and medication administration record."),
        ]
        
        for pattern, disclaimer in dangerous_advice:
            if re.search(pattern, text):
                concerns.append(disclaimer)
        
        definitive_language = [
            (r"(?i)\bdefinitely\s+(?:is|has|will)\b", "likely"),
            (r"(?i)\balways\s+(?:give|administer|do)\b", "typically"),
            (r"(?i)\bnever\s+(?:give|administer|do)\b", "generally avoid"),
            (r"(?i)\bguaranteed\s+to\b", "may help to"),
            (r"(?i)\bwill\s+cure\b", "may help manage"),
        ]
        
        for pattern, replacement in definitive_language:
            if re.search(pattern, modified):
                modified = re.sub(pattern, replacement, modified, flags=re.IGNORECASE)
                concerns.append("Modified definitive language to be more clinically appropriate")
        
        if concerns:
            return SafetyCheckResult(
                level=SafetyLevel.CAUTION,
                passed=True,
                concerns=concerns,
                modified_content=modified if modified != text else None,
                requires_review=len(concerns) > 2
            )
        
        return SafetyCheckResult(
            level=SafetyLevel.SAFE,
            passed=True,
            concerns=[],
            modified_content=None,
            requires_review=False
        )
    
    def add_disclaimer(self, text: str, category: str = "general") -> str:
        disclaimer = self.medical_disclaimers.get(category, self.medical_disclaimers["general"])
        return f"{text}\n\n_{disclaimer}_"
    
    def sanitize_patient_info(self, text: str) -> str:
        patterns = [
            (r"\b\d{3}[-.]?\d{2}[-.]?\d{4}\b", "[SSN REDACTED]"),
            (r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b", "[PHONE REDACTED]"),
            (r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", "[EMAIL REDACTED]"),
            (r"\b\d{1,5}\s+\w+\s+(?:street|st|avenue|ave|road|rd|boulevard|blvd|drive|dr|lane|ln)\b",
             "[ADDRESS REDACTED]"),
        ]
        
        result = text
        for pattern, replacement in patterns:
            result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
        
        return result
    
    def validate_vital_range(self, vital_type: str, value: float) -> Tuple[bool, Optional[str]]:
        ranges = {
            "systolic": (50, 300, "Blood pressure systolic"),
            "diastolic": (30, 200, "Blood pressure diastolic"),
            "heart_rate": (20, 250, "Heart rate"),
            "temperature": (30, 45, "Temperature (Celsius)"),
            "spo2": (50, 100, "Oxygen saturation"),
            "respiratory_rate": (4, 60, "Respiratory rate"),
            "glucose": (20, 800, "Blood glucose"),
        }
        
        if vital_type not in ranges:
            return True, None
        
        min_val, max_val, name = ranges[vital_type]
        
        if value < min_val or value > max_val:
            return False, f"{name} value {value} is outside valid range ({min_val}-{max_val})"
        
        return True, None
    
    def check_medication_safety(self, medication: str, patient_allergies: List[str]) -> SafetyCheckResult:
        concerns = []
        
        allergy_drug_mapping = {
            "penicillin": ["amoxicillin", "ampicillin", "penicillin", "augmentin"],
            "sulfa": ["sulfamethoxazole", "bactrim", "septra", "sulfasalazine"],
            "aspirin": ["aspirin", "excedrin"],
            "nsaid": ["ibuprofen", "naproxen", "advil", "motrin", "aleve", "celebrex"],
            "codeine": ["codeine", "tylenol 3", "tylenol #3"],
            "morphine": ["morphine", "ms contin"],
            "latex": [],
        }
        
        medication_lower = medication.lower()
        
        for allergy in patient_allergies:
            allergy_lower = allergy.lower().strip()
            
            if allergy_lower in medication_lower:
                return SafetyCheckResult(
                    level=SafetyLevel.BLOCKED,
                    passed=False,
                    concerns=[f"ALLERGY ALERT: Patient allergic to {allergy}. {medication} may contain this allergen."],
                    modified_content=None,
                    requires_review=True
                )
            
            related_drugs = allergy_drug_mapping.get(allergy_lower, [])
            for drug in related_drugs:
                if drug in medication_lower:
                    concerns.append(
                        f"Cross-reactivity warning: Patient allergic to {allergy}. "
                        f"{medication} may cause allergic reaction."
                    )
        
        if concerns:
            return SafetyCheckResult(
                level=SafetyLevel.CAUTION,
                passed=True,
                concerns=concerns,
                modified_content=None,
                requires_review=True
            )
        
        return SafetyCheckResult(
            level=SafetyLevel.SAFE,
            passed=True,
            concerns=[],
            modified_content=None,
            requires_review=False
        )
    
    def get_safe_response(self, blocked_reason: str = "") -> str:
        responses = {
            "prohibited": "I cannot assist with that request. Please speak with your healthcare provider.",
            "medication": "For medication questions, please consult with the pharmacist or prescribing physician.",
            "diagnosis": "Diagnostic questions should be directed to the attending physician.",
            "emergency": "If this is an emergency, please activate rapid response or call for immediate assistance.",
            "default": "I'm not able to help with that. Please consult with the appropriate healthcare professional."
        }
        
        return responses.get(blocked_reason, responses["default"])