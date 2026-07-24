from typing import List, Optional, Dict
from datetime import datetime, timedelta
import json
from sqlmodel import Session, select, and_, desc

from database.models import (
    Medication, 
    MedicationAdministration, 
    MedicationHold,
    get_engine
)


class MedicationRepository:
    def __init__(self):
        self.engine = get_engine()
    
    def get_active_medications(self, patient_id: str) -> List[Dict]:
        with Session(self.engine) as session:
            statement = select(Medication).where(
                and_(
                    Medication.patient_id == patient_id,
                    Medication.status == "active"
                )
            ).order_by(Medication.name)
            
            meds = session.exec(statement).all()
            
            result = []
            for med in meds:
                med_dict = self._med_to_dict(med)
                med_dict["last_given"] = self._get_last_given(session, med.id)
                result.append(med_dict)
            
            return result
    
    def get_medication(self, medication_id: str) -> Optional[Dict]:
        with Session(self.engine) as session:
            med = session.get(Medication, medication_id)
            if med:
                med_dict = self._med_to_dict(med)
                med_dict["last_given"] = self._get_last_given(session, med.id)
                return med_dict
            return None
    
    def find_medication_by_name(
        self, 
        patient_id: str, 
        name: str
    ) -> Optional[Dict]:
        with Session(self.engine) as session:
            statement = select(Medication).where(
                and_(
                    Medication.patient_id == patient_id,
                    Medication.status == "active"
                )
            )
            
            meds = session.exec(statement).all()
            
            name_lower = name.lower()
            for med in meds:
                if name_lower in med.name.lower():
                    return self._med_to_dict(med)
                if med.generic_name and name_lower in med.generic_name.lower():
                    return self._med_to_dict(med)
            
            return None
    
    def get_due_medications(
        self, 
        patient_id: str, 
        window_hours: int = 2
    ) -> List[Dict]:
        with Session(self.engine) as session:
            statement = select(Medication).where(
                and_(
                    Medication.patient_id == patient_id,
                    Medication.status == "active"
                )
            )
            
            meds = session.exec(statement).all()
            
            now = datetime.utcnow()
            dose_window = timedelta(minutes=90)
            due_meds = []
            
            for med in meds:
                if not med.scheduled_times:
                    continue
                
                try:
                    times = json.loads(med.scheduled_times)
                except json.JSONDecodeError:
                    continue
                if not isinstance(times, list):
                    continue

                last_given = self._get_last_given(session, med.id)
                
                for time_str in sorted(times):
                    try:
                        hour, minute = map(int, time_str.split(":"))
                        scheduled_today = now.replace(
                            hour=hour, 
                            minute=minute, 
                            second=0, 
                            microsecond=0
                        )

                        dose_window_start = scheduled_today - dose_window
                        dose_window_end = scheduled_today + dose_window
                        given_for_today = (
                            last_given is not None
                            and dose_window_start <= last_given <= dose_window_end
                        )

                        # If dose for this scheduled slot was already administered,
                        # the next due occurrence is tomorrow at the same time.
                        due_time = scheduled_today + timedelta(days=1) if given_for_today else scheduled_today
                        hours_until = (due_time - now).total_seconds() / 3600

                        if hours_until <= window_hours:
                            due_meds.append({
                                **self._med_to_dict(med),
                                "scheduled_time": time_str,
                                "next_due": due_time.isoformat(),
                                "hours_until": round(hours_until, 1)
                            })
                    except ValueError:
                        continue
            
            due_meds.sort(key=lambda x: x.get("hours_until", float("inf")))
            return due_meds
    
    def get_medication_schedule(
        self, 
        patient_id: str, 
        medication_id: str
    ) -> Optional[Dict]:
        with Session(self.engine) as session:
            med = session.get(Medication, medication_id)
            if not med or med.patient_id != patient_id:
                return None
            
            times = []
            if med.scheduled_times:
                try:
                    times = json.loads(med.scheduled_times)
                except json.JSONDecodeError:
                    pass
            
            return {
                "medication_id": medication_id,
                "frequency": med.frequency,
                "times": times,
                "last_given": self._get_last_given(session, medication_id)
            }
    
    def record_administration(
        self,
        patient_id: str,
        medication_id: Optional[str],
        medication_name: str,
        dose: Optional[str] = None,
        route: Optional[str] = None,
        timestamp: Optional[datetime] = None,
        recorded_by: Optional[str] = None,
        notes: Optional[str] = None
    ) -> Dict:
        with Session(self.engine) as session:
            admin = MedicationAdministration(
                patient_id=patient_id,
                medication_id=medication_id,
                medication_name=medication_name,
                dose=dose,
                route=route,
                action="given",
                actual_time=timestamp or datetime.utcnow(),
                recorded_by=recorded_by,
                notes=notes
            )
            session.add(admin)
            session.commit()
            session.refresh(admin)
            
            return {
                "id": admin.id,
                "medication_name": admin.medication_name,
                "dose": admin.dose,
                "action": admin.action,
                "actual_time": admin.actual_time.isoformat()
            }
    
    def record_hold(
        self,
        patient_id: str,
        medication_id: Optional[str],
        medication_name: str,
        reason: Optional[str] = None,
        timestamp: Optional[datetime] = None,
        recorded_by: Optional[str] = None
    ) -> Dict:
        with Session(self.engine) as session:
            hold = MedicationHold(
                patient_id=patient_id,
                medication_id=medication_id,
                medication_name=medication_name,
                reason=reason,
                hold_start=timestamp or datetime.utcnow(),
                recorded_by=recorded_by
            )
            session.add(hold)
            session.commit()
            session.refresh(hold)
            
            return {
                "id": hold.id,
                "medication_name": hold.medication_name,
                "reason": hold.reason,
                "hold_start": hold.hold_start.isoformat()
            }
    
    def get_last_administration(
        self, 
        patient_id: str, 
        medication_id: str
    ) -> Optional[datetime]:
        with Session(self.engine) as session:
            return self._get_last_given(session, medication_id)
    
    def get_administration_history(
        self,
        patient_id: str,
        medication_id: Optional[str] = None,
        days: int = 7
    ) -> List[Dict]:
        with Session(self.engine) as session:
            cutoff = datetime.utcnow() - timedelta(days=days)
            
            if medication_id:
                statement = select(MedicationAdministration).where(
                    and_(
                        MedicationAdministration.patient_id == patient_id,
                        MedicationAdministration.medication_id == medication_id,
                        MedicationAdministration.actual_time >= cutoff
                    )
                ).order_by(desc(MedicationAdministration.actual_time))
            else:
                statement = select(MedicationAdministration).where(
                    and_(
                        MedicationAdministration.patient_id == patient_id,
                        MedicationAdministration.actual_time >= cutoff
                    )
                ).order_by(desc(MedicationAdministration.actual_time))
            
            admins = session.exec(statement).all()
            
            return [{
                "id": a.id,
                "medication_id": a.medication_id,
                "medication_name": a.medication_name,
                "dose": a.dose,
                "route": a.route,
                "action": a.action,
                "actual_time": a.actual_time.isoformat(),
                "recorded_by": a.recorded_by,
                "notes": a.notes
            } for a in admins]
    
    def get_adherence_stats(
        self, 
        patient_id: str, 
        medication_id: str,
        days: int = 30
    ) -> Dict:
        with Session(self.engine) as session:
            med = session.get(Medication, medication_id)
            if not med:
                return {}
            
            cutoff = datetime.utcnow() - timedelta(days=days)
            
            statement = select(MedicationAdministration).where(
                and_(
                    MedicationAdministration.medication_id == medication_id,
                    MedicationAdministration.action == "given",
                    MedicationAdministration.actual_time >= cutoff
                )
            )
            
            given_count = len(session.exec(statement).all())
            
            expected_per_day = 1
            if med.frequency:
                freq_map = {
                    "daily": 1,
                    "bid": 2,
                    "tid": 3,
                    "qid": 4,
                    "q4h": 6,
                    "q6h": 4,
                    "q8h": 3,
                    "q12h": 2,
                    "weekly": 0.14
                }
                expected_per_day = freq_map.get(med.frequency.lower(), 1)
            
            expected_total = int(expected_per_day * days)
            
            adherence_rate = 0
            if expected_total > 0:
                adherence_rate = min(100, round((given_count / expected_total) * 100, 1))
            
            return {
                "medication_id": medication_id,
                "medication_name": med.name,
                "period_days": days,
                "doses_given": given_count,
                "doses_expected": expected_total,
                "adherence_rate": adherence_rate
            }
    
    def add_medication(self, patient_id: str, medication_data: Dict) -> Dict:
        with Session(self.engine) as session:
            med = Medication(
                patient_id=patient_id,
                **medication_data
            )
            session.add(med)
            session.commit()
            session.refresh(med)
            return self._med_to_dict(med)
    
    def update_medication(
        self, 
        medication_id: str, 
        update_data: Dict
    ) -> Optional[Dict]:
        with Session(self.engine) as session:
            med = session.get(Medication, medication_id)
            if not med:
                return None
            
            for key, value in update_data.items():
                if hasattr(med, key):
                    setattr(med, key, value)
            
            med.updated_at = datetime.utcnow()
            session.add(med)
            session.commit()
            session.refresh(med)
            return self._med_to_dict(med)
    
    def discontinue_medication(
        self, 
        medication_id: str, 
        reason: Optional[str] = None
    ) -> bool:
        with Session(self.engine) as session:
            med = session.get(Medication, medication_id)
            if med:
                med.status = "discontinued"
                med.end_date = datetime.utcnow()
                if reason:
                    med.instructions = f"{med.instructions or ''} [DC: {reason}]"
                session.add(med)
                session.commit()
                return True
            return False
    
    def _get_last_given(
        self, 
        session: Session, 
        medication_id: str
    ) -> Optional[datetime]:
        statement = select(MedicationAdministration).where(
            and_(
                MedicationAdministration.medication_id == medication_id,
                MedicationAdministration.action == "given"
            )
        ).order_by(desc(MedicationAdministration.actual_time)).limit(1)
        
        admin = session.exec(statement).first()
        return admin.actual_time if admin else None
    
    def _med_to_dict(self, med: Medication) -> Dict:
        times = []
        if med.scheduled_times:
            try:
                times = json.loads(med.scheduled_times)
            except json.JSONDecodeError:
                pass
        
        return {
            "id": med.id,
            "patient_id": med.patient_id,
            "name": med.name,
            "generic_name": med.generic_name,
            "dose": med.dose,
            "unit": med.unit,
            "route": med.route,
            "frequency": med.frequency,
            "scheduled_times": times,
            "start_date": med.start_date.isoformat() if med.start_date else None,
            "end_date": med.end_date.isoformat() if med.end_date else None,
            "prescriber": med.prescriber,
            "indication": med.indication,
            "instructions": med.instructions,
            "status": med.status
        }
