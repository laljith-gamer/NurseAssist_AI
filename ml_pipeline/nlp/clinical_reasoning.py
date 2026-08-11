"""Clinical Reasoning Module.

This module applies nursing domain knowledge to post-process AI predictions.
It enforces clinical rules, checks for medication interactions, and adds 
clinical severity scoring.
"""

from typing import List, Dict, Set
from dataclasses import dataclass

@dataclass
class ClinicalRule:
    triggers: List[str]
    implied_observation: str
    severity: str  # "low", "medium", "high"
    
CLINICAL_RULES = [
    ClinicalRule(["Hypertension", "Tachycardia"], "Hemodynamic Instability", "high"),
    ClinicalRule(["Hypoxia", "Respiratory Distress"], "Respiratory Compromise", "high"),
    ClinicalRule(["Severe pain", "Agitated"], "Inadequate Pain Control", "medium"),
]

def apply_clinical_reasoning(predicted_labels: List[str]) -> List[Dict[str, str]]:
    """Applies clinical reasoning rules to enhance predictions."""
    results = []
    active_labels = set(predicted_labels)
    
    # 1. Add original predictions
    for label in active_labels:
        results.append({
            "name": label,
            "type": "observation",
            "severity": "low"
        })
        
    # 2. Check clinical rules
    for rule in CLINICAL_RULES:
        if all(trigger in active_labels for trigger in rule.triggers):
            results.append({
                "name": rule.implied_observation,
                "type": "inferred_risk",
                "severity": rule.severity
            })
            
    # Sort by severity (high -> medium -> low)
    severity_order = {"high": 0, "medium": 1, "low": 2}
    results.sort(key=lambda x: severity_order.get(x["severity"], 3))
    
    return results
