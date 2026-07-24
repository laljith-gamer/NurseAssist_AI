from typing import List, Optional, Dict
from datetime import datetime
from sqlmodel import Session, select, or_, and_

from database.models import Patient, get_engine


class PatientRepository:
    def __init__(self):
        self.engine = get_engine()
    
    def get_patient(self, patient_id: str) -> Optional[Dict]:
        with Session(self.engine) as session:
            patient = session.get(Patient, patient_id)
            if patient:
                return self._to_dict(patient)
            return None
    
    def get_patient_by_mrn(self, mrn: str) -> Optional[Dict]:
        with Session(self.engine) as session:
            statement = select(Patient).where(Patient.mrn == mrn)
            patient = session.exec(statement).first()
            if patient:
                return self._to_dict(patient)
            return None
    
    def get_patient_by_room(self, room: str) -> Optional[Dict]:
        with Session(self.engine) as session:
            statement = select(Patient).where(
                and_(
                    Patient.room == room,
                    Patient.is_active == True
                )
            )
            patient = session.exec(statement).first()
            if patient:
                return self._to_dict(patient)
            return None
    
    def get_all_patients(self, active_only: bool = True) -> List[Dict]:
        with Session(self.engine) as session:
            if active_only:
                statement = select(Patient).where(Patient.is_active == True)
            else:
                statement = select(Patient)
            
            patients = session.exec(statement).all()
            result = []
            for p in patients:
                result.append(self._to_dict(p))
            return result
    
    def search_patients_by_name(self, name: str) -> List[Dict]:
        with Session(self.engine) as session:
            name_lower = name.lower()
            name_parts = name_lower.split()
            
            statement = select(Patient).where(Patient.is_active == True)
            patients = session.exec(statement).all()
            
            results = []
            for patient in patients:
                full_name = f"{patient.first_name} {patient.last_name}".lower()
                
                if name_lower in full_name:
                    results.append(patient)
                    continue
                
                match = False
                for part in name_parts:
                    if part in patient.first_name.lower() or part in patient.last_name.lower():
                        match = True
                        break
                
                if match:
                    results.append(patient)
            
            return [self._to_dict(p) for p in results]
    
    def create_patient(self, patient_data: Dict) -> Dict:
        with Session(self.engine) as session:
            patient = Patient(**patient_data)
            session.add(patient)
            session.commit()
            session.refresh(patient)
            return self._to_dict(patient)
    
    def update_patient(self, patient_id: str, update_data: Dict) -> Optional[Dict]:
        with Session(self.engine) as session:
            patient = session.get(Patient, patient_id)
            if not patient:
                return None
            
            for key, value in update_data.items():
                if hasattr(patient, key):
                    setattr(patient, key, value)
            
            patient.updated_at = datetime.utcnow()
            session.add(patient)
            session.commit()
            session.refresh(patient)
            return self._to_dict(patient)
    
    def _to_dict(self, patient: Patient) -> Dict:
        age = None
        if patient.date_of_birth:
            from datetime import date
            today = date.today()
            age = today.year - patient.date_of_birth.year - (
                (today.month, today.day) < (patient.date_of_birth.month, patient.date_of_birth.day)
            )
        
        return {
            "id": patient.id,
            "mrn": patient.mrn,
            "first_name": patient.first_name,
            "last_name": patient.last_name,
            "name": f"{patient.first_name} {patient.last_name}",
            "date_of_birth": patient.date_of_birth.isoformat() if patient.date_of_birth else None,
            "age": age,
            "gender": patient.gender,
            "room": patient.room,
            "bed": patient.bed,
            "admission_date": patient.admission_date.isoformat() if patient.admission_date else None,
            "discharge_date": patient.discharge_date.isoformat() if patient.discharge_date else None,
            "primary_diagnosis": patient.primary_diagnosis,
            "allergies": patient.allergies,
            "code_status": patient.code_status,
            "insurance": patient.insurance,
            "emergency_contact_name": patient.emergency_contact_name,
            "emergency_contact_phone": patient.emergency_contact_phone,
            "is_active": patient.is_active,
            "created_at": patient.created_at.isoformat() if patient.created_at else None,
            "updated_at": patient.updated_at.isoformat() if patient.updated_at else None
        }