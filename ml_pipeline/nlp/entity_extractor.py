import re
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum


class EntityType(Enum):
    VITAL_BP = "vital_bp"
    VITAL_HR = "vital_hr"
    VITAL_TEMP = "vital_temp"
    VITAL_SPO2 = "vital_spo2"
    VITAL_RR = "vital_rr"
    VITAL_WEIGHT = "vital_weight"
    MEDICATION_NAME = "medication_name"
    PATIENT_ROOM = "patient_room"


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


_KNOWN_MEDICATIONS = [
    "tylenol", "metformin", "lisinopril", "aspirin", "ibuprofen",
    "morphine", "zofran", "lasix", "heparin", "insulin", "propofol",
]

_PATTERNS: List[tuple] = [
    (EntityType.VITAL_BP, re.compile(r"\b(\d{2,3})\s*/\s*(\d{2,3})\b")),
    (EntityType.VITAL_TEMP, re.compile(r"\btemp(?:erature)?\s*(?:is|of)?\s*(\d{2,3}(?:\.\d)?)\b", re.IGNORECASE)),
    (EntityType.VITAL_SPO2, re.compile(r"\b(?:spo2|sp02|o2\s*sat(?:uration)?|oxygen\s*sat(?:uration)?)\s*(?:is|of)?\s*(\d{2,3})\s*%?\b", re.IGNORECASE)),
    (EntityType.VITAL_RR, re.compile(r"\b(?:rr|respiratory\s*rate|respirations?)\s*(?:is|of)?\s*(\d{1,2})\b", re.IGNORECASE)),
    (EntityType.VITAL_HR, re.compile(r"\b(?:hr|heart\s*rate|pulse)\s*(?:is|of)?\s*(\d{2,3})\b", re.IGNORECASE)),
    (EntityType.VITAL_WEIGHT, re.compile(r"\bweight\s*(?:is|of)?\s*(\d{2,3})\s*(kg|lbs?)\b", re.IGNORECASE)),
    (EntityType.PATIENT_ROOM, re.compile(r"\broom\s*(\d{2,4})\b", re.IGNORECASE)),
]

_MED_PATTERN = re.compile(
    r"\b(?:gave|administered|hold|held|discontinue[d]?)\s+(?:patient\s+)?(?:\d+\s*(?:mg|mcg|units?)\s+)?("
    + "|".join(_KNOWN_MEDICATIONS) + r")\b",
    re.IGNORECASE,
)


class EntityExtractor:
    def extract(self, text: str) -> ExtractionResult:
        entities: List[Entity] = []
        vitals: Dict[str, Any] = {}
        medications: Dict[str, Any] = {}
        patient_identifiers: Dict[str, Any] = {}
        time_references: List[Dict] = []

        for entity_type, pattern in _PATTERNS:
            for match in pattern.finditer(text):
                raw_text = match.group(0)
                entity = Entity(
                    entity_type=entity_type,
                    value=raw_text,
                    raw_text=raw_text,
                    start=match.start(),
                    end=match.end(),
                    confidence=1.0,
                )
                entities.append(entity)

                if entity_type == EntityType.VITAL_BP:
                    vitals["bp"] = {
                        "systolic": int(match.group(1)),
                        "diastolic": int(match.group(2)),
                    }
                elif entity_type == EntityType.VITAL_TEMP:
                    vitals["temp"] = float(match.group(1))
                elif entity_type == EntityType.VITAL_SPO2:
                    vitals["spo2"] = int(match.group(1))
                elif entity_type == EntityType.VITAL_RR:
                    vitals["rr"] = int(match.group(1))
                elif entity_type == EntityType.VITAL_HR:
                    vitals["hr"] = int(match.group(1))
                elif entity_type == EntityType.VITAL_WEIGHT:
                    vitals["weight"] = {
                        "value": float(match.group(1)),
                        "unit": match.group(2).lower(),
                    }
                elif entity_type == EntityType.PATIENT_ROOM:
                    patient_identifiers["room"] = match.group(1)

        for match in _MED_PATTERN.finditer(text):
            raw_text = match.group(0)
            name = match.group(1)
            entities.append(
                Entity(
                    entity_type=EntityType.MEDICATION_NAME,
                    value=name,
                    raw_text=raw_text,
                    start=match.start(1),
                    end=match.end(1),
                    confidence=1.0,
                )
            )
            medications["name"] = name

        matched_spans = set()
        for entity in entities:
            for i in range(entity.start, entity.end):
                matched_spans.add(i)
        unmatched_text = "".join(
            char for i, char in enumerate(text) if i not in matched_spans
        ).strip()

        return ExtractionResult(
            entities=entities,
            vitals=vitals,
            medications=medications,
            patient_identifiers=patient_identifiers,
            time_references=time_references,
            unmatched_text=unmatched_text,
        )
