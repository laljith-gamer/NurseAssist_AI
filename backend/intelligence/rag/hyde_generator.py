from typing import List, Optional
from dataclasses import dataclass


@dataclass
class HyDEResult:
    original_query: str
    hypothetical_document: str
    enhanced_queries: List[str]


class HyDEGenerator:
    def __init__(self):
        self.templates = self._load_templates()
    
    def _load_templates(self) -> dict:
        return {
            "vital_query": """
Based on the clinical question about vital signs, a relevant medical document would state:
The patient's {vital_type} reading indicates {clinical_interpretation}. 
According to clinical guidelines, this value falls within the {classification} range.
Recommended actions include {recommendations}.
""",
            "medication_query": """
Regarding the medication inquiry, a clinical reference would explain:
{medication_name} is a {drug_class} medication used for {indications}.
Common dosing is {typical_dose}. Important considerations include {precautions}.
Monitoring parameters: {monitoring}.
""",
            "patient_status": """
A clinical progress note addressing this query would document:
Patient presents with {presenting_condition}. Current vital signs show {vital_summary}.
Assessment indicates {clinical_assessment}. Plan includes {treatment_plan}.
""",
            "trend_analysis": """
A clinical analysis report would describe:
Review of {parameter} over {time_period} reveals {trend_direction} trend.
Values ranged from {min_value} to {max_value}. Clinical significance: {significance}.
Recommendations based on trend: {recommendations}.
""",
            "general": """
A medical reference document addressing this clinical question would explain:
{topic_overview}. Key clinical considerations include {key_points}.
Evidence-based recommendations suggest {recommendations}.
"""
        }
    
    def generate_hypothetical_document(
        self,
        query: str,
        query_type: Optional[str] = None,
        context: Optional[dict] = None
    ) -> HyDEResult:
        query_type = query_type or self._detect_query_type(query)
        template = self.templates.get(query_type, self.templates["general"])
        
        filled_template = self._fill_template(template, query, context or {})
        enhanced_queries = self._generate_enhanced_queries(query, query_type)
        
        return HyDEResult(
            original_query=query,
            hypothetical_document=filled_template,
            enhanced_queries=enhanced_queries
        )
    
    def _detect_query_type(self, query: str) -> str:
        query_lower = query.lower()
        
        vital_keywords = [
            "bp", "blood pressure", "heart rate", "hr", "pulse",
            "temperature", "temp", "spo2", "oxygen", "respiratory"
        ]
        if any(kw in query_lower for kw in vital_keywords):
            return "vital_query"
        
        med_keywords = [
            "medication", "medicine", "drug", "dose", "dosage",
            "give", "administer", "prescribe", "side effect"
        ]
        if any(kw in query_lower for kw in med_keywords):
            return "medication_query"
        
        trend_keywords = [
            "trend", "over time", "history", "change", "compare",
            "increase", "decrease", "pattern"
        ]
        if any(kw in query_lower for kw in trend_keywords):
            return "trend_analysis"
        
        status_keywords = [
            "status", "condition", "how is", "assessment", "current"
        ]
        if any(kw in query_lower for kw in status_keywords):
            return "patient_status"
        
        return "general"
    
    def _fill_template(
        self,
        template: str,
        query: str,
        context: dict
    ) -> str:
        query_lower = query.lower()
        
        placeholders = {
            "vital_type": self._extract_vital_type(query_lower),
            "clinical_interpretation": "within expected parameters",
            "classification": "normal",
            "recommendations": "continue monitoring",
            "medication_name": self._extract_medication_name(query_lower),
            "drug_class": "therapeutic",
            "indications": "the diagnosed condition",
            "typical_dose": "standard dosing",
            "precautions": "standard precautions apply",
            "monitoring": "routine clinical monitoring",
            "presenting_condition": "current clinical status",
            "vital_summary": "stable vital signs",
            "clinical_assessment": "stable condition",
            "treatment_plan": "continue current management",
            "parameter": "clinical parameter",
            "time_period": "the observation period",
            "trend_direction": "stable",
            "min_value": "lower range",
            "max_value": "upper range",
            "significance": "clinical significance noted",
            "topic_overview": "relevant clinical information",
            "key_points": "important clinical factors"
        }
        
        placeholders.update(context)
        
        result = template
        for key, value in placeholders.items():
            result = result.replace("{" + key + "}", str(value))
        
        return result.strip()
    
    def _extract_vital_type(self, query: str) -> str:
        vital_map = {
            "blood pressure": "blood pressure",
            "bp": "blood pressure",
            "heart rate": "heart rate",
            "hr": "heart rate",
            "pulse": "heart rate",
            "temperature": "temperature",
            "temp": "temperature",
            "spo2": "oxygen saturation",
            "oxygen": "oxygen saturation",
            "respiratory": "respiratory rate",
            "weight": "weight",
            "glucose": "blood glucose"
        }
        
        for keyword, vital_type in vital_map.items():
            if keyword in query:
                return vital_type
        
        return "vital signs"
    
    def _extract_medication_name(self, query: str) -> str:
        common_meds = [
            "metformin", "lisinopril", "amlodipine", "metoprolol",
            "atorvastatin", "omeprazole", "levothyroxine", "gabapentin",
            "hydrochlorothiazide", "losartan", "furosemide", "prednisone",
            "aspirin", "warfarin", "insulin"
        ]
        
        for med in common_meds:
            if med in query:
                return med
        
        return "the medication"
    
    def _generate_enhanced_queries(
        self,
        query: str,
        query_type: str
    ) -> List[str]:
        enhanced = [query]
        
        if query_type == "vital_query":
            enhanced.extend([
                f"{query} normal range clinical guidelines",
                f"{query} interpretation assessment",
                f"{query} abnormal values intervention"
            ])
        
        elif query_type == "medication_query":
            enhanced.extend([
                f"{query} dosing administration",
                f"{query} side effects precautions",
                f"{query} drug interactions monitoring"
            ])
        
        elif query_type == "trend_analysis":
            enhanced.extend([
                f"{query} clinical significance",
                f"{query} pattern analysis",
                f"{query} intervention threshold"
            ])
        
        elif query_type == "patient_status":
            enhanced.extend([
                f"{query} assessment documentation",
                f"{query} clinical indicators",
                f"{query} care plan"
            ])
        
        else:
            enhanced.extend([
                f"{query} clinical guidelines",
                f"{query} best practices",
                f"{query} evidence-based"
            ])
        
        return enhanced[:4]
    
    def expand_clinical_query(self, query: str) -> List[str]:
        result = self.generate_hypothetical_document(query)
        return result.enhanced_queries
    
    def get_search_context(
        self,
        query: str,
        patient_context: Optional[dict] = None
    ) -> dict:
        result = self.generate_hypothetical_document(
            query=query,
            context=patient_context or {}
        )
        
        return {
            "original_query": result.original_query,
            "hypothetical_doc": result.hypothetical_document,
            "enhanced_queries": result.enhanced_queries,
            "query_type": self._detect_query_type(query)
        }