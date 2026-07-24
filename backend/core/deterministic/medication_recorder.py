from dataclasses import dataclass
from typing import Dict, Optional, List
from datetime import datetime, timedelta
from enum import Enum


class MedicationAction(Enum):
    GIVEN = "given"
    DUE = "due"
    HELD = "held"
    DISCONTINUED = "discontinued"
    SCHEDULED = "scheduled"


class MedicationStatus(Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    HELD = "held"
    DISCONTINUED = "discontinued"


@dataclass
class MedicationRecord:
    medication_id: Optional[str]
    medication_name: str
    action: MedicationAction
    dose: Optional[str]
    route: Optional[str]
    timestamp: datetime
    recorded_by: Optional[str]
    notes: Optional[str]


@dataclass
class MedicationResult:
    success: bool
    patient_id: str
    record: Optional[MedicationRecord]
    message: str
    warnings: List[str]
    next_due: Optional[datetime]
    adherence_info: Dict


class MedicationRecorder:
    def __init__(self):
        self.common_medications = self._load_common_medications()
        self.route_abbreviations = {
            "po": "oral",
            "iv": "intravenous",
            "im": "intramuscular",
            "sc": "subcutaneous",
            "sq": "subcutaneous",
            "sl": "sublingual",
            "pr": "rectal",
            "top": "topical",
            "inh": "inhalation",
            "neb": "nebulizer",
        }
    
    def _load_common_medications(self) -> Dict:
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
        }
    
    def record(
        self,
        patient_id: str,
        action: str,
        medication_text: str,
        recorded_by: Optional[str] = None
    ) -> MedicationResult:
        from database.repo.meds_repo import MedicationRepository
        
        parsed = self._parse_medication_text(medication_text)
        
        if not parsed["name"]:
            return MedicationResult(
                success=False,
                patient_id=patient_id,
                record=None,
                message="Could not identify medication name",
                warnings=[],
                next_due=None,
                adherence_info={}
            )
        
        repo = MedicationRepository()
        
        medication_action = MedicationAction(action)
        
        matched_med = repo.find_medication_by_name(patient_id, parsed["name"])
        
        warnings = []
        resolved_next_due: Optional[datetime] = None
        
        if medication_action == MedicationAction.GIVEN:
            if matched_med:
                last_given = repo.get_last_administration(patient_id, matched_med["id"])
                if last_given:
                    hours_since = (datetime.utcnow() - last_given).total_seconds() / 3600
                    if hours_since < 1:
                        warnings.append(
                            f"Warning: {parsed['name']} was given {int(hours_since * 60)} minutes ago"
                        )
        
        record = MedicationRecord(
            medication_id=matched_med["id"] if matched_med else None,
            medication_name=parsed["name"],
            action=medication_action,
            dose=parsed.get("dose"),
            route=parsed.get("route"),
            timestamp=datetime.utcnow(),
            recorded_by=recorded_by,
            notes=parsed.get("notes")
        )
        
        if medication_action == MedicationAction.GIVEN:
            repo.record_administration(
                patient_id=patient_id,
                medication_id=record.medication_id,
                medication_name=record.medication_name,
                dose=record.dose,
                route=record.route,
                timestamp=record.timestamp,
                recorded_by=recorded_by
            )
            message = f"Recorded: {record.medication_name}"
            if record.dose:
                message += f" {record.dose}"
            message += " given"
            
        elif medication_action == MedicationAction.HELD:
            repo.record_hold(
                patient_id=patient_id,
                medication_id=record.medication_id,
                medication_name=record.medication_name,
                reason=record.notes,
                timestamp=record.timestamp,
                recorded_by=recorded_by
            )
            message = f"Recorded: {record.medication_name} held"
            
        elif medication_action == MedicationAction.DUE:
            due_meds = repo.get_due_medications(patient_id)
            matching = [m for m in due_meds if parsed["name"].lower() in m["name"].lower()]
            if matching:
                next_due_raw = matching[0].get("next_due")
                resolved_next_due = self._parse_datetime(next_due_raw)
                message = f"{record.medication_name} is due"
                if resolved_next_due:
                    message += f" at {resolved_next_due.strftime('%H:%M')}"
            else:
                message = f"{record.medication_name} - no scheduled dose found"
        else:
            message = f"Action {action} recorded for {record.medication_name}"
        
        if resolved_next_due is None and matched_med:
            schedule = repo.get_medication_schedule(patient_id, matched_med["id"])
            if schedule:
                resolved_next_due = self._calculate_next_due(schedule)
        
        adherence_info = {}
        if matched_med:
            adherence_info = repo.get_adherence_stats(patient_id, matched_med["id"])
        
        return MedicationResult(
            success=True,
            patient_id=patient_id,
            record=record,
            message=message,
            warnings=warnings,
            next_due=resolved_next_due,
            adherence_info=adherence_info
        )
    
    def _parse_medication_text(self, text: str) -> Dict:
        result = {
            "name": None,
            "dose": None,
            "route": None,
            "notes": None
        }
        
        text = text.strip().lower()
        
        import re
        
        dose_pattern = re.compile(r'(\d+(?:\.\d+)?)\s*(mg|mcg|g|ml|units?|iu)', re.IGNORECASE)
        dose_match = dose_pattern.search(text)
        if dose_match:
            result["dose"] = dose_match.group(0)
            text = text.replace(dose_match.group(0), " ")
        
        for abbrev, full in self.route_abbreviations.items():
            if re.search(rf'\b{abbrev}\b', text, re.IGNORECASE):
                result["route"] = full
                text = re.sub(rf'\b{abbrev}\b', '', text, flags=re.IGNORECASE)
                break
        
        text = re.sub(r'\s+', ' ', text).strip()
        
        for med_name in self.common_medications:
            if med_name in text:
                result["name"] = med_name
                break
        
        if not result["name"]:
            words = text.split()
            if words:
                result["name"] = words[0]
        
        return result
    
    def _calculate_next_due(self, schedule: Dict) -> Optional[datetime]:
        if not schedule:
            return None
        
        frequency = schedule.get("frequency", "daily")
        last_given = schedule.get("last_given")
        scheduled_times = schedule.get("times", [])
        
        now = datetime.utcnow()
        
        if isinstance(scheduled_times, list) and scheduled_times:
            for time_str in scheduled_times:
                try:
                    hour, minute = map(int, time_str.split(":"))
                    scheduled = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                    if scheduled > now:
                        return scheduled
                except ValueError:
                    continue
            
            try:
                hour, minute = map(int, scheduled_times[0].split(":"))
                return (now + timedelta(days=1)).replace(hour=hour, minute=minute, second=0, microsecond=0)
            except (TypeError, ValueError, IndexError):
                return None
        
        if last_given:
            if frequency == "daily":
                return last_given + timedelta(days=1)
            elif frequency == "bid":
                return last_given + timedelta(hours=12)
            elif frequency == "tid":
                return last_given + timedelta(hours=8)
            elif frequency == "qid":
                return last_given + timedelta(hours=6)
            elif frequency == "q4h":
                return last_given + timedelta(hours=4)
            elif frequency == "q6h":
                return last_given + timedelta(hours=6)
            elif frequency == "q8h":
                return last_given + timedelta(hours=8)
            elif frequency == "weekly":
                return last_given + timedelta(weeks=1)
        
        return None

    def _parse_datetime(self, value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value)
        except (TypeError, ValueError):
            return None
    
    def get_formatted_response(self, result: MedicationResult) -> Dict:
        response = {
            "success": result.success,
            "message": result.message,
            "warnings": result.warnings,
            "medication": None,
            "next_due": None,
            "adherence": result.adherence_info
        }
        
        if result.record:
            response["medication"] = {
                "name": result.record.medication_name,
                "action": result.record.action.value,
                "dose": result.record.dose,
                "route": result.record.route,
                "timestamp": result.record.timestamp.isoformat()
            }
        
        if result.next_due:
            response["next_due"] = result.next_due.isoformat()
        
        return response
