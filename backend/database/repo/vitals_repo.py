from typing import List, Optional, Dict
from datetime import datetime, timedelta
from sqlmodel import Session, select, and_, func, desc

from database.models import Vital, VitalBaseline, get_engine


class VitalsRepository:
    def __init__(self):
        self.engine = get_engine()
    
    def save_vital(
        self,
        patient_id: str,
        vital_type: str,
        value: float,
        unit: Optional[str] = None,
        timestamp: Optional[datetime] = None,
        source: str = "manual",
        recorded_by: Optional[str] = None,
        notes: Optional[str] = None
    ) -> Dict:
        with Session(self.engine) as session:
            vital = Vital(
                patient_id=patient_id,
                vital_type=vital_type,
                value=value,
                unit=unit,
                timestamp=timestamp or datetime.utcnow(),
                source=source,
                recorded_by=recorded_by,
                notes=notes
            )
            session.add(vital)
            session.commit()
            session.refresh(vital)
            return self._to_dict(vital)
    
    def get_latest_vitals(self, patient_id: str) -> Optional[Dict]:
        with Session(self.engine) as session:
            vital_types = [
                "systolic", "diastolic", "heart_rate", "temperature",
                "spo2", "respiratory_rate", "weight", "height", "glucose"
            ]
            
            result = {}
            latest_timestamp = None
            
            for vital_type in vital_types:
                statement = select(Vital).where(
                    and_(
                        Vital.patient_id == patient_id,
                        Vital.vital_type == vital_type,
                        Vital.is_valid == True
                    )
                ).order_by(desc(Vital.timestamp)).limit(1)
                
                vital = session.exec(statement).first()
                if vital:
                    result[vital_type] = vital.value
                    if latest_timestamp is None or vital.timestamp > latest_timestamp:
                        latest_timestamp = vital.timestamp
            
            if result:
                result["timestamp"] = latest_timestamp.isoformat() if latest_timestamp else None
                return result
            
            return None
    
    def get_vitals_at_time(
        self, 
        patient_id: str, 
        target_time: datetime,
        tolerance_hours: int = 4
    ) -> Optional[Dict]:
        with Session(self.engine) as session:
            min_time = target_time - timedelta(hours=tolerance_hours)
            max_time = target_time + timedelta(hours=tolerance_hours)
            
            vital_types = [
                "systolic", "diastolic", "heart_rate", "temperature",
                "spo2", "respiratory_rate", "weight", "glucose"
            ]
            
            result = {}
            
            for vital_type in vital_types:
                statement = select(Vital).where(
                    and_(
                        Vital.patient_id == patient_id,
                        Vital.vital_type == vital_type,
                        Vital.is_valid == True,
                        Vital.timestamp >= min_time,
                        Vital.timestamp <= max_time
                    )
                ).order_by(
                    func.abs(func.julianday(Vital.timestamp) - func.julianday(target_time))
                ).limit(1)
                
                vital = session.exec(statement).first()
                if vital:
                    result[vital_type] = vital.value
            
            return result if result else None
    
    def get_average_vitals(self, patient_id: str, days: int = 7) -> Optional[Dict]:
        with Session(self.engine) as session:
            cutoff = datetime.utcnow() - timedelta(days=days)
            
            vital_types = [
                "systolic", "diastolic", "heart_rate", "temperature",
                "spo2", "respiratory_rate", "weight", "glucose"
            ]
            
            result = {}
            
            for vital_type in vital_types:
                statement = select(func.avg(Vital.value)).where(
                    and_(
                        Vital.patient_id == patient_id,
                        Vital.vital_type == vital_type,
                        Vital.is_valid == True,
                        Vital.timestamp >= cutoff
                    )
                )
                
                avg_value = session.exec(statement).first()
                if avg_value is not None:
                    result[vital_type] = float(avg_value)
            
            return result if result else None
    
    def get_baseline_vitals(self, patient_id: str) -> Optional[Dict]:
        with Session(self.engine) as session:
            statement = select(VitalBaseline).where(
                VitalBaseline.patient_id == patient_id
            )
            
            baseline = session.exec(statement).first()
            
            if baseline:
                return {
                    "systolic": baseline.systolic,
                    "diastolic": baseline.diastolic,
                    "heart_rate": baseline.heart_rate,
                    "temperature": baseline.temperature,
                    "spo2": baseline.spo2,
                    "respiratory_rate": baseline.respiratory_rate,
                    "weight": baseline.weight,
                    "height": baseline.height,
                    "glucose": baseline.glucose,
                    "baseline_date": baseline.baseline_date.isoformat() if baseline.baseline_date else None
                }
            
            return None
    
    def set_baseline_vitals(self, patient_id: str, vitals: Dict) -> Dict:
        with Session(self.engine) as session:
            statement = select(VitalBaseline).where(
                VitalBaseline.patient_id == patient_id
            )
            existing = session.exec(statement).first()
            
            if existing:
                for key, value in vitals.items():
                    if hasattr(existing, key) and value is not None:
                        setattr(existing, key, value)
                existing.updated_at = datetime.utcnow()
                session.add(existing)
            else:
                baseline = VitalBaseline(
                    patient_id=patient_id,
                    baseline_date=datetime.utcnow(),
                    **vitals
                )
                session.add(baseline)
            
            session.commit()
            return self.get_baseline_vitals(patient_id)
    
    def get_vitals_history(
        self, 
        patient_id: str, 
        days: int = 30,
        vital_type: Optional[str] = None
    ) -> List[Dict]:
        with Session(self.engine) as session:
            cutoff = datetime.utcnow() - timedelta(days=days)
            
            if vital_type:
                statement = select(Vital).where(
                    and_(
                        Vital.patient_id == patient_id,
                        Vital.vital_type == vital_type,
                        Vital.is_valid == True,
                        Vital.timestamp >= cutoff
                    )
                ).order_by(desc(Vital.timestamp))
            else:
                statement = select(Vital).where(
                    and_(
                        Vital.patient_id == patient_id,
                        Vital.is_valid == True,
                        Vital.timestamp >= cutoff
                    )
                ).order_by(desc(Vital.timestamp))
            
            vitals = session.exec(statement).all()
            return [self._to_dict(v) for v in vitals]
    
    def get_recent_readings(
        self, 
        patient_id: str, 
        vital_type: str, 
        count: int = 7
    ) -> List[Dict]:
        with Session(self.engine) as session:
            statement = select(Vital).where(
                and_(
                    Vital.patient_id == patient_id,
                    Vital.vital_type == vital_type,
                    Vital.is_valid == True
                )
            ).order_by(desc(Vital.timestamp)).limit(count)
            
            vitals = session.exec(statement).all()
            return [{"value": v.value, "timestamp": v.timestamp} for v in vitals]
    
    def get_updates_since(
        self, 
        patient_id: str, 
        since: datetime
    ) -> List[Dict]:
        with Session(self.engine) as session:
            statement = select(Vital).where(
                and_(
                    Vital.patient_id == patient_id,
                    Vital.created_at > since
                )
            ).order_by(Vital.created_at)
            
            vitals = session.exec(statement).all()
            return [self._to_dict(v) for v in vitals]
    
    def get_vital_statistics(
        self, 
        patient_id: str, 
        vital_type: str, 
        days: int = 30
    ) -> Dict:
        with Session(self.engine) as session:
            cutoff = datetime.utcnow() - timedelta(days=days)
            
            base_query = select(Vital).where(
                and_(
                    Vital.patient_id == patient_id,
                    Vital.vital_type == vital_type,
                    Vital.is_valid == True,
                    Vital.timestamp >= cutoff
                )
            )
            
            vitals = session.exec(base_query).all()
            
            if not vitals:
                return {}
            
            values = [v.value for v in vitals]
            
            return {
                "count": len(values),
                "min": min(values),
                "max": max(values),
                "avg": sum(values) / len(values),
                "latest": values[0] if values else None,
                "period_days": days
            }
    
    def invalidate_vital(self, vital_id: int, reason: Optional[str] = None) -> bool:
        with Session(self.engine) as session:
            vital = session.get(Vital, vital_id)
            if vital:
                vital.is_valid = False
                vital.notes = f"{vital.notes or ''} [Invalidated: {reason or 'No reason provided'}]"
                session.add(vital)
                session.commit()
                return True
            return False
    
    def _to_dict(self, vital: Vital) -> Dict:
        return {
            "id": vital.id,
            "patient_id": vital.patient_id,
            "vital_type": vital.vital_type,
            "value": vital.value,
            "unit": vital.unit,
            "timestamp": vital.timestamp.isoformat() if vital.timestamp else None,
            "source": vital.source,
            "recorded_by": vital.recorded_by,
            "notes": vital.notes,
            "is_valid": vital.is_valid,
            "created_at": vital.created_at.isoformat() if vital.created_at else None
        }