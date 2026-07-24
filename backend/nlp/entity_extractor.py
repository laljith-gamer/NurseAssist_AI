import re
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from enum import Enum


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
        self._compile_patterns()
        self.medication_database = self._load_medication_database()
    
    def _compile_patterns(self):
        self.vital_patterns = {
            EntityType.VITAL_BP: [
                re.compile(r"(?:bp|blood\s*pressure|b\.p\.?)\s*[:=]?\s*(\d{2,3})\s*[/\\]\s*(\d{2,3})", re.I),
                re.compile(r"(\d{2,3})\s*[/\\]\s*(\d{2,3})\s*(?:mmhg)?", re.I),
                re.compile(r"systolic\s*[:=]?\s*(\d{2,3}).*?diastolic\s*[:=]?\s*(\d{2,3})", re.I),
            ],
            EntityType.VITAL_HR: [
                re.compile(r"(?:hr|heart\s*rate|pulse|p)\s*[:=]?\s*(\d{2,3})\s*(?:bpm)?", re.I),
                re.compile(r"(\d{2,3})\s*(?:bpm|beats\s*per\s*minute)", re.I),
            ],
            EntityType.VITAL_TEMP: [
                re.compile(r"(?:temp|temperature|t)\s*[:=]?\s*(\d{2,3}(?:\.\d{1,2})?)\s*(?:degrees?)?\s*([fc])?", re.I),
                re.compile(r"(\d{2,3}(?:\.\d{1,2})?)\s*(?:degrees?)?\s*([fc](?:ahrenheit|elsius)?)", re.I),
            ],
            EntityType.VITAL_SPO2: [
                re.compile(r"(?:spo2|sp02|o2\s*sat|oxygen\s*sat(?:uration)?|sat)\s*[:=]?\s*(\d{2,3})\s*%?", re.I),
                re.compile(r"(\d{2,3})\s*%\s*(?:on\s*(?:room\s*air|ra|\d+l?(?:\s*nc)?))?", re.I),
            ],
            EntityType.VITAL_RR: [
                re.compile(r"(?:rr|resp(?:iratory)?\s*rate|breaths?)\s*[:=]?\s*(\d{1,2})", re.I),
                re.compile(r"(\d{1,2})\s*(?:breaths?\s*per\s*min(?:ute)?|/min)", re.I),
            ],
            EntityType.VITAL_WEIGHT: [
                re.compile(r"(?:weight|wt|w)\s*[:=]?\s*(\d{2,3}(?:\.\d{1,2})?)\s*(kg|lbs?|pounds?|kilos?)?", re.I),
            ],
            EntityType.VITAL_HEIGHT: [
                re.compile(r"(?:height|ht|h)\s*[:=]?\s*(\d{2,3}(?:\.\d{1,2})?)\s*(cm|m|ft|feet|in(?:ches)?)?", re.I),
                re.compile(r"(\d)\'(\d{1,2})\"?", re.I),
            ],
            EntityType.VITAL_GLUCOSE: [
                re.compile(r"(?:glucose|sugar|bs|blood\s*sugar|bg|fs)\s*[:=]?\s*(\d{2,3})", re.I),
            ],
        }
        
        self.medication_patterns = {
            EntityType.MEDICATION_DOSE: [
                re.compile(r"(\d+(?:\.\d+)?)\s*(mg|mcg|g|ml|units?|iu|meq)", re.I),
            ],
            EntityType.MEDICATION_ROUTE: [
                re.compile(r"\b(po|iv|im|sc|sq|sl|pr|topical|inh(?:aled)?|neb|patch|supp)\b", re.I),
                re.compile(r"\b(oral(?:ly)?|intravenous(?:ly)?|intramuscular(?:ly)?|subcutaneous(?:ly)?)\b", re.I),
            ],
            EntityType.MEDICATION_FREQUENCY: [
                re.compile(r"\b(daily|bid|tid|qid|prn|q\d+h|once|twice|weekly)\b", re.I),
                re.compile(r"\b(every\s*\d+\s*hours?|once\s*(?:a|per)\s*day|twice\s*(?:a|per)\s*day)\b", re.I),
            ],
        }
        
        self.patient_patterns = {
            EntityType.PATIENT_ROOM: [
                re.compile(r"(?:room|rm)\s*[:=]?\s*(\d+[a-z]?)", re.I),
                re.compile(r"\broom\s+(\d+[a-z]?)\b", re.I),
            ],
            EntityType.PATIENT_MRN: [
                re.compile(r"(?:mrn|medical\s*record)\s*[:=]?\s*([a-z]?\d{6,10})", re.I),
            ],
        }
        
        self.time_patterns = [
            re.compile(r"\b(\d{1,2}):(\d{2})\s*(am|pm)?\b", re.I),
            re.compile(r"\b(\d{1,2})\s*(am|pm)\b", re.I),
            re.compile(r"\b(now|currently|just\s*now|right\s*now)\b", re.I),
            re.compile(r"\b(\d+)\s*(minutes?|hours?|mins?|hrs?)\s*ago\b", re.I),
            re.compile(r"\b(this\s*morning|this\s*afternoon|this\s*evening|tonight|yesterday|today)\b", re.I),
            re.compile(r"\b(last\s*night|last\s*week|last\s*month)\b", re.I),
        ]
    
    def _load_medication_database(self) -> Dict[str, Dict]:
        return {
            "metformin": {"class": "antidiabetic", "common_doses": ["500mg", "850mg", "1000mg"]},
            "lisinopril": {"class": "ace_inhibitor", "common_doses": ["5mg", "10mg", "20mg", "40mg"]},
            "amlodipine": {"class": "calcium_channel_blocker", "common_doses": ["2.5mg", "5mg", "10mg"]},
            "metoprolol": {"class": "beta_blocker", "common_doses": ["25mg", "50mg", "100mg"]},
            "atorvastatin": {"class": "statin", "common_doses": ["10mg", "20mg", "40mg", "80mg"]},
            "omeprazole": {"class": "ppi", "common_doses": ["20mg", "40mg"]},
            "levothyroxine": {"class": "thyroid", "common_doses": ["25mcg", "50mcg", "75mcg", "100mcg"]},
            "gabapentin": {"class": "anticonvulsant", "common_doses": ["100mg", "300mg", "600mg"]},
            "hydrochlorothiazide": {"class": "diuretic", "common_doses": ["12.5mg", "25mg", "50mg"]},
            "losartan": {"class": "arb", "common_doses": ["25mg", "50mg", "100mg"]},
            "furosemide": {"class": "loop_diuretic", "common_doses": ["20mg", "40mg", "80mg"]},
            "prednisone": {"class": "corticosteroid", "common_doses": ["5mg", "10mg", "20mg"]},
            "aspirin": {"class": "antiplatelet", "common_doses": ["81mg", "325mg"]},
            "warfarin": {"class": "anticoagulant", "common_doses": ["1mg", "2mg", "2.5mg", "5mg"]},
            "insulin": {"class": "antidiabetic", "common_doses": ["units"]},
            "albuterol": {"class": "bronchodilator", "common_doses": ["2 puffs", "90mcg"]},
            "pantoprazole": {"class": "ppi", "common_doses": ["20mg", "40mg"]},
            "clopidogrel": {"class": "antiplatelet", "common_doses": ["75mg"]},
            "carvedilol": {"class": "beta_blocker", "common_doses": ["3.125mg", "6.25mg", "12.5mg", "25mg"]},
            "sertraline": {"class": "ssri", "common_doses": ["25mg", "50mg", "100mg"]},
            "fluoxetine": {"class": "ssri", "common_doses": ["10mg", "20mg", "40mg"]},
            "trazodone": {"class": "antidepressant", "common_doses": ["50mg", "100mg", "150mg"]},
            "acetaminophen": {"class": "analgesic", "common_doses": ["325mg", "500mg", "650mg"]},
            "ibuprofen": {"class": "nsaid", "common_doses": ["200mg", "400mg", "600mg", "800mg"]},
            "morphine": {"class": "opioid", "common_doses": ["2mg", "4mg", "5mg", "10mg"]},
            "oxycodone": {"class": "opioid", "common_doses": ["5mg", "10mg", "15mg", "20mg"]},
            "hydrocodone": {"class": "opioid", "common_doses": ["5mg", "7.5mg", "10mg"]},
            "azithromycin": {"class": "antibiotic", "common_doses": ["250mg", "500mg"]},
            "amoxicillin": {"class": "antibiotic", "common_doses": ["250mg", "500mg", "875mg"]},
            "ciprofloxacin": {"class": "antibiotic", "common_doses": ["250mg", "500mg", "750mg"]},
            "doxycycline": {"class": "antibiotic", "common_doses": ["100mg"]},
        }
    
    def extract(self, text: str) -> ExtractionResult:
        entities = []
        vitals = {}
        medications = {}
        patient_identifiers = {}
        time_references = []
        
        for entity_type, patterns in self.vital_patterns.items():
            for pattern in patterns:
                for match in pattern.finditer(text):
                    entity = self._create_vital_entity(entity_type, match)
                    if entity:
                        entities.append(entity)
                        self._update_vitals_dict(vitals, entity)
        
        for entity_type, patterns in self.medication_patterns.items():
            for pattern in patterns:
                for match in pattern.finditer(text):
                    entity = Entity(
                        entity_type=entity_type,
                        value=match.group(0),
                        raw_text=match.group(0),
                        start=match.start(),
                        end=match.end(),
                        confidence=0.9
                    )
                    entities.append(entity)
                    medications[entity_type.value] = match.group(0)
        
        med_entities = self._extract_medication_names(text)
        entities.extend(med_entities)
        if med_entities:
            medications["name"] = med_entities[0].value
        
        for entity_type, patterns in self.patient_patterns.items():
            for pattern in patterns:
                for match in pattern.finditer(text):
                    entity = Entity(
                        entity_type=entity_type,
                        value=match.group(1) if match.groups() else match.group(0),
                        raw_text=match.group(0),
                        start=match.start(),
                        end=match.end(),
                        confidence=0.95
                    )
                    entities.append(entity)
                    patient_identifiers[entity_type.value] = entity.value
        
        for pattern in self.time_patterns:
            for match in pattern.finditer(text):
                time_ref = {
                    "raw": match.group(0),
                    "start": match.start(),
                    "end": match.end(),
                }
                time_references.append(time_ref)
        
        matched_spans = set()
        for entity in entities:
            for i in range(entity.start, entity.end):
                matched_spans.add(i)
        
        unmatched_chars = []
        for i, char in enumerate(text):
            if i not in matched_spans:
                unmatched_chars.append(char)
        unmatched_text = "".join(unmatched_chars).strip()
        unmatched_text = re.sub(r"\s+", " ", unmatched_text)
        
        return ExtractionResult(
            entities=entities,
            vitals=vitals,
            medications=medications,
            patient_identifiers=patient_identifiers,
            time_references=time_references,
            unmatched_text=unmatched_text
        )
    
    def _create_vital_entity(
        self, 
        entity_type: EntityType, 
        match: re.Match
    ) -> Optional[Entity]:
        try:
            if entity_type == EntityType.VITAL_BP:
                systolic = int(match.group(1))
                diastolic = int(match.group(2))
                
                if not (50 <= systolic <= 300 and 30 <= diastolic <= 200):
                    return None
                
                return Entity(
                    entity_type=entity_type,
                    value={"systolic": systolic, "diastolic": diastolic},
                    raw_text=match.group(0),
                    start=match.start(),
                    end=match.end(),
                    confidence=0.95,
                    unit="mmHg",
                    normalized_value={"systolic": systolic, "diastolic": diastolic}
                )
            
            elif entity_type == EntityType.VITAL_HR:
                value = int(match.group(1))
                if not (20 <= value <= 250):
                    return None
                
                return Entity(
                    entity_type=entity_type,
                    value=value,
                    raw_text=match.group(0),
                    start=match.start(),
                    end=match.end(),
                    confidence=0.95,
                    unit="bpm",
                    normalized_value=value
                )
            
            elif entity_type == EntityType.VITAL_TEMP:
                value = float(match.group(1))
                unit = match.group(2).upper() if match.lastindex >= 2 and match.group(2) else None
                
                if unit == "F" or value > 50:
                    normalized = (value - 32) * 5 / 9
                    unit = "F"
                else:
                    normalized = value
                    unit = "C"
                
                if not (30 <= normalized <= 45):
                    return None
                
                return Entity(
                    entity_type=entity_type,
                    value=value,
                    raw_text=match.group(0),
                    start=match.start(),
                    end=match.end(),
                    confidence=0.9,
                    unit=unit,
                    normalized_value=round(normalized, 1)
                )
            
            elif entity_type == EntityType.VITAL_SPO2:
                value = int(match.group(1))
                if not (50 <= value <= 100):
                    return None
                
                return Entity(
                    entity_type=entity_type,
                    value=value,
                    raw_text=match.group(0),
                    start=match.start(),
                    end=match.end(),
                    confidence=0.95,
                    unit="%",
                    normalized_value=value
                )
            
            elif entity_type == EntityType.VITAL_RR:
                value = int(match.group(1))
                if not (4 <= value <= 60):
                    return None
                
                return Entity(
                    entity_type=entity_type,
                    value=value,
                    raw_text=match.group(0),
                    start=match.start(),
                    end=match.end(),
                    confidence=0.95,
                    unit="/min",
                    normalized_value=value
                )
            
            elif entity_type == EntityType.VITAL_WEIGHT:
                value = float(match.group(1))
                unit = match.group(2).lower() if match.lastindex >= 2 and match.group(2) else "kg"
                
                if unit in ("lbs", "lb", "pounds", "pound"):
                    normalized = value * 0.453592
                    unit = "lbs"
                else:
                    normalized = value
                    unit = "kg"
                
                return Entity(
                    entity_type=entity_type,
                    value=value,
                    raw_text=match.group(0),
                    start=match.start(),
                    end=match.end(),
                    confidence=0.9,
                    unit=unit,
                    normalized_value=round(normalized, 1)
                )
            
            elif entity_type == EntityType.VITAL_HEIGHT:
                if "'" in match.group(0) or "\"" in match.group(0):
                    feet = int(match.group(1))
                    inches = int(match.group(2)) if match.lastindex >= 2 else 0
                    value = feet * 12 + inches
                    normalized = value * 2.54
                    unit = "ft"
                else:
                    value = float(match.group(1))
                    unit = match.group(2).lower() if match.lastindex >= 2 and match.group(2) else "cm"
                    normalized = value
                
                return Entity(
                    entity_type=entity_type,
                    value=value,
                    raw_text=match.group(0),
                    start=match.start(),
                    end=match.end(),
                    confidence=0.9,
                    unit=unit,
                    normalized_value=round(normalized, 1)
                )
            
            elif entity_type == EntityType.VITAL_GLUCOSE:
                value = int(match.group(1))
                if not (20 <= value <= 800):
                    return None
                
                return Entity(
                    entity_type=entity_type,
                    value=value,
                    raw_text=match.group(0),
                    start=match.start(),
                    end=match.end(),
                    confidence=0.95,
                    unit="mg/dL",
                    normalized_value=value
                )
        
        except (ValueError, IndexError):
            return None
        
        return None
    
    def _update_vitals_dict(self, vitals: Dict, entity: Entity) -> None:
        type_mapping = {
            EntityType.VITAL_BP: "bp",
            EntityType.VITAL_HR: "hr",
            EntityType.VITAL_TEMP: "temp",
            EntityType.VITAL_SPO2: "spo2",
            EntityType.VITAL_RR: "rr",
            EntityType.VITAL_WEIGHT: "weight",
            EntityType.VITAL_HEIGHT: "height",
            EntityType.VITAL_GLUCOSE: "glucose",
        }
        
        key = type_mapping.get(entity.entity_type)
        if key:
            vitals[key] = entity.normalized_value or entity.value
    
    def _extract_medication_names(self, text: str) -> List[Entity]:
        entities = []
        text_lower = text.lower()
        
        for med_name in self.medication_database:
            pattern = r"\b" + re.escape(med_name) + r"\b"
            for match in re.finditer(pattern, text_lower):
                entities.append(Entity(
                    entity_type=EntityType.MEDICATION_NAME,
                    value=med_name,
                    raw_text=text[match.start():match.end()],
                    start=match.start(),
                    end=match.end(),
                    confidence=0.95
                ))
        
        if not entities:
            med_suffixes = [
                "pril", "sartan", "olol", "pine", "statin", "prazole",
                "tidine", "azole", "cillin", "mycin", "cycline", "floxacin"
            ]
            
            words = re.finditer(r"\b([a-z]{4,})\b", text_lower)
            for match in words:
                word = match.group(1)
                for suffix in med_suffixes:
                    if word.endswith(suffix):
                        entities.append(Entity(
                            entity_type=EntityType.MEDICATION_NAME,
                            value=word,
                            raw_text=text[match.start():match.end()],
                            start=match.start(),
                            end=match.end(),
                            confidence=0.7
                        ))
                        break
        
        return entities
    
    def extract_for_intent(
        self, 
        text: str, 
        intent: str
    ) -> Dict[str, Any]:
        result = self.extract(text)
        
        if intent in ("record_vitals", "query_vitals"):
            return {
                "vitals": result.vitals,
                "entities": [
                    e for e in result.entities 
                    if e.entity_type.value.startswith("vital_")
                ]
            }
        
        elif intent in ("record_medication", "query_medications"):
            return {
                "medications": result.medications,
                "entities": [
                    e for e in result.entities
                    if e.entity_type.value.startswith("medication_")
                ]
            }
        
        elif intent == "select_patient":
            return {
                "patient": result.patient_identifiers,
                "entities": [
                    e for e in result.entities
                    if e.entity_type.value.startswith("patient_")
                ]
            }
        
        return {
            "all": {
                "vitals": result.vitals,
                "medications": result.medications,
                "patient": result.patient_identifiers,
            },
            "entities": result.entities
        }