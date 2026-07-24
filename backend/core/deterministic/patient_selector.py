from dataclasses import dataclass
from typing import Dict, Optional, List
from datetime import datetime
import re


@dataclass
class PatientMatch:
    patient_id: str
    name: str
    room: Optional[str]
    mrn: Optional[str]
    match_score: float
    match_type: str


@dataclass
class SelectionResult:
    success: bool
    patient: Optional[PatientMatch]
    alternatives: List[PatientMatch]
    message: str
    patient_summary: Optional[Dict]


class PatientSelector:
    def __init__(self):
        self.selection_cache = {}
    
    def select(
        self,
        identifier: str,
        selection_type: str,
        context: Optional[Dict] = None
    ) -> SelectionResult:
        from database.repo.patient_repo import PatientRepository
        
        repo = PatientRepository()
        identifier = identifier.strip()
        
        if selection_type == "room":
            return self._select_by_room(repo, identifier)
        
        if self._is_mrn(identifier):
            return self._select_by_mrn(repo, identifier)
        
        return self._select_by_name(repo, identifier)
    
    def _is_mrn(self, identifier: str) -> bool:
        return bool(re.match(r'^[A-Z]?\d{6,10}$', identifier.upper()))
    
    def _select_by_room(
        self, 
        repo, 
        room_number: str
    ) -> SelectionResult:
        room_number = room_number.upper().strip()
        
        patient = repo.get_patient_by_room(room_number)
        
        if patient:
            match = PatientMatch(
                patient_id=patient["id"],
                name=patient["name"],
                room=patient.get("room"),
                mrn=patient.get("mrn"),
                match_score=1.0,
                match_type="room"
            )
            
            summary = self._get_patient_summary(patient["id"])
            
            return SelectionResult(
                success=True,
                patient=match,
                alternatives=[],
                message=f"Selected patient: {patient['name']} (Room {room_number})",
                patient_summary=summary
            )
        
        return SelectionResult(
            success=False,
            patient=None,
            alternatives=[],
            message=f"No patient found in room {room_number}",
            patient_summary=None
        )
    
    def _select_by_mrn(
        self, 
        repo, 
        mrn: str
    ) -> SelectionResult:
        patient = repo.get_patient_by_mrn(mrn.upper())
        
        if patient:
            match = PatientMatch(
                patient_id=patient["id"],
                name=patient["name"],
                room=patient.get("room"),
                mrn=patient.get("mrn"),
                match_score=1.0,
                match_type="mrn"
            )
            
            summary = self._get_patient_summary(patient["id"])
            
            return SelectionResult(
                success=True,
                patient=match,
                alternatives=[],
                message=f"Selected patient: {patient['name']} (MRN: {mrn})",
                patient_summary=summary
            )
        
        return SelectionResult(
            success=False,
            patient=None,
            alternatives=[],
            message=f"No patient found with MRN {mrn}",
            patient_summary=None
        )
    
    def _select_by_name(
        self, 
        repo, 
        name: str
    ) -> SelectionResult:
        matches = repo.search_patients_by_name(name)
        
        if not matches:
            return SelectionResult(
                success=False,
                patient=None,
                alternatives=[],
                message=f"No patients found matching '{name}'",
                patient_summary=None
            )
        
        scored_matches = []
        for patient in matches:
            score = self._calculate_name_match_score(name, patient["name"])
            scored_matches.append(
                PatientMatch(
                    patient_id=patient["id"],
                    name=patient["name"],
                    room=patient.get("room"),
                    mrn=patient.get("mrn"),
                    match_score=score,
                    match_type="name"
                )
            )
        
        scored_matches.sort(key=lambda x: x.match_score, reverse=True)
        
        if len(scored_matches) == 1 or scored_matches[0].match_score > 0.9:
            best_match = scored_matches[0]
            summary = self._get_patient_summary(best_match.patient_id)
            
            return SelectionResult(
                success=True,
                patient=best_match,
                alternatives=scored_matches[1:5],
                message=f"Selected patient: {best_match.name}",
                patient_summary=summary
            )
        
        return SelectionResult(
            success=False,
            patient=None,
            alternatives=scored_matches[:5],
            message=f"Multiple patients match '{name}'. Please be more specific.",
            patient_summary=None
        )
    
    def _calculate_name_match_score(self, query: str, name: str) -> float:
        query = query.lower().strip()
        name = name.lower().strip()
        
        if query == name:
            return 1.0
        
        if query in name:
            return 0.9
        
        query_parts = query.split()
        name_parts = name.split()
        
        matches = 0
        for qp in query_parts:
            for np in name_parts:
                if qp == np:
                    matches += 1
                    break
                elif qp in np or np in qp:
                    matches += 0.5
                    break
        
        if query_parts:
            return matches / len(query_parts)
        
        return 0.0
    
    def _get_patient_summary(self, patient_id: str) -> Dict:
        from database.repo.patient_repo import PatientRepository
        from database.repo.vitals_repo import VitalsRepository
        from database.repo.meds_repo import MedicationRepository
        from core.change_detector import ChangeDetector
        
        patient_repo = PatientRepository()
        vitals_repo = VitalsRepository()
        meds_repo = MedicationRepository()
        detector = ChangeDetector()
        
        patient = patient_repo.get_patient(patient_id)
        latest_vitals = vitals_repo.get_latest_vitals(patient_id)
        active_meds = meds_repo.get_active_medications(patient_id)
        delta_metrics = detector.get_delta_metrics(patient_id)
        
        summary = {
            "patient_id": patient_id,
            "demographics": {
                "name": patient.get("name") if patient else None,
                "age": patient.get("age") if patient else None,
                "gender": patient.get("gender") if patient else None,
                "room": patient.get("room") if patient else None,
            },
            "latest_vitals": latest_vitals,
            "active_medications_count": len(active_meds) if active_meds else 0,
            "alerts": delta_metrics.get("alerts", []) if delta_metrics else [],
            "clinical_status": delta_metrics.get("clinical_status", {}) if delta_metrics else {},
        }
        
        return summary
    
    def get_formatted_response(self, result: SelectionResult) -> Dict:
        response = {
            "success": result.success,
            "message": result.message,
            "patient": None,
            "alternatives": [],
            "summary": result.patient_summary
        }
        
        if result.patient:
            response["patient"] = {
                "id": result.patient.patient_id,
                "name": result.patient.name,
                "room": result.patient.room,
                "mrn": result.patient.mrn,
                "match_score": result.patient.match_score
            }
        
        for alt in result.alternatives:
            response["alternatives"].append({
                "id": alt.patient_id,
                "name": alt.name,
                "room": alt.room,
                "mrn": alt.mrn
            })
        
        return response