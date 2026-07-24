from typing import List, Optional, Dict
from datetime import datetime
from sqlmodel import Session, select, and_, desc

from database.models import Visit, get_engine


class VisitRepository:
    def __init__(self):
        self.engine = get_engine()
    
    def create_visit(self, visit_data: Dict) -> Dict:
        with Session(self.engine) as session:
            visit = Visit(**visit_data)
            session.add(visit)
            session.commit()
            session.refresh(visit)
            return self._to_dict(visit)
    
    def get_visit(self, visit_id: str) -> Optional[Dict]:
        with Session(self.engine) as session:
            visit = session.get(Visit, visit_id)
            if visit:
                return self._to_dict(visit)
            return None
    
    def get_active_visit(self, patient_id: str) -> Optional[Dict]:
        with Session(self.engine) as session:
            statement = select(Visit).where(
                and_(
                    Visit.patient_id == patient_id,
                    Visit.status == "active"
                )
            ).order_by(desc(Visit.admission_date)).limit(1)
            
            visit = session.exec(statement).first()
            if visit:
                return self._to_dict(visit)
            return None
    
    def get_patient_visits(
        self, 
        patient_id: str, 
        include_discharged: bool = False
    ) -> List[Dict]:
        with Session(self.engine) as session:
            if include_discharged:
                statement = select(Visit).where(
                    Visit.patient_id == patient_id
                ).order_by(desc(Visit.admission_date))
            else:
                statement = select(Visit).where(
                    and_(
                        Visit.patient_id == patient_id,
                        Visit.status == "active"
                    )
                ).order_by(desc(Visit.admission_date))
            
            visits = session.exec(statement).all()
            return [self._to_dict(v) for v in visits]
    
    def update_visit(self, visit_id: str, update_data: Dict) -> Optional[Dict]:
        with Session(self.engine) as session:
            visit = session.get(Visit, visit_id)
            if not visit:
                return None
            
            for key, value in update_data.items():
                if hasattr(visit, key):
                    setattr(visit, key, value)
            
            visit.updated_at = datetime.utcnow()
            session.add(visit)
            session.commit()
            session.refresh(visit)
            return self._to_dict(visit)
    
    def discharge_visit(
        self, 
        visit_id: str, 
        discharge_date: Optional[datetime] = None
    ) -> Optional[Dict]:
        return self.update_visit(visit_id, {
            "status": "discharged",
            "discharge_date": discharge_date or datetime.utcnow()
        })
    
    def get_all_active_visits(self) -> List[Dict]:
        with Session(self.engine) as session:
            statement = select(Visit).where(
                Visit.status == "active"
            ).order_by(Visit.admission_date)
            
            visits = session.exec(statement).all()
            return [self._to_dict(v) for v in visits]
    
    def get_visits_by_department(self, department: str) -> List[Dict]:
        with Session(self.engine) as session:
            statement = select(Visit).where(
                and_(
                    Visit.department == department,
                    Visit.status == "active"
                )
            ).order_by(Visit.admission_date)
            
            visits = session.exec(statement).all()
            return [self._to_dict(v) for v in visits]
    
    def get_visit_count(
        self, 
        patient_id: Optional[str] = None, 
        active_only: bool = True
    ) -> int:
        with Session(self.engine) as session:
            conditions = []
            
            if patient_id:
                conditions.append(Visit.patient_id == patient_id)
            
            if active_only:
                conditions.append(Visit.status == "active")
            
            if conditions:
                statement = select(Visit).where(and_(*conditions))
            else:
                statement = select(Visit)
            
            return len(session.exec(statement).all())
    
    def get_length_of_stay(self, visit_id: str) -> Optional[Dict]:
        with Session(self.engine) as session:
            visit = session.get(Visit, visit_id)
            if not visit:
                return None
            
            end_date = visit.discharge_date or datetime.utcnow()
            delta = end_date - visit.admission_date
            
            return {
                "visit_id": visit_id,
                "admission_date": visit.admission_date.isoformat(),
                "discharge_date": visit.discharge_date.isoformat() if visit.discharge_date else None,
                "days": delta.days,
                "hours": int(delta.total_seconds() / 3600),
                "is_discharged": visit.status == "discharged"
            }
    
    def add_diagnosis_code(self, visit_id: str, code: str) -> Optional[Dict]:
        with Session(self.engine) as session:
            visit = session.get(Visit, visit_id)
            if not visit:
                return None
            
            existing_codes = []
            if visit.diagnosis_codes:
                existing_codes = visit.diagnosis_codes.split(",")
            
            if code not in existing_codes:
                existing_codes.append(code)
                visit.diagnosis_codes = ",".join(existing_codes)
                visit.updated_at = datetime.utcnow()
                session.add(visit)
                session.commit()
                session.refresh(visit)
            
            return self._to_dict(visit)
    
    def _to_dict(self, visit: Visit) -> Dict:
        return {
            "id": visit.id,
            "patient_id": visit.patient_id,
            "visit_type": visit.visit_type,
            "admission_date": visit.admission_date.isoformat() if visit.admission_date else None,
            "discharge_date": visit.discharge_date.isoformat() if visit.discharge_date else None,
            "attending_physician": visit.attending_physician,
            "department": visit.department,
            "chief_complaint": visit.chief_complaint,
            "diagnosis_codes": visit.diagnosis_codes.split(",") if visit.diagnosis_codes else [],
            "status": visit.status,
            "created_at": visit.created_at.isoformat() if visit.created_at else None,
            "updated_at": visit.updated_at.isoformat() if visit.updated_at else None
        }