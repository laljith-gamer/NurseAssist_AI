from typing import List, Optional, Dict
from datetime import datetime, timedelta
from sqlmodel import Session, select, and_, desc

from database.models import ChangeLog, get_engine


class ChangeLogRepository:
    def __init__(self):
        self.engine = get_engine()
    
    def log_change(
        self,
        patient_id: str,
        change_type: str,
        entity_type: str,
        entity_id: Optional[str] = None,
        old_value: Optional[str] = None,
        new_value: Optional[str] = None,
        significance: Optional[str] = None
    ) -> Dict:
        with Session(self.engine) as session:
            log = ChangeLog(
                patient_id=patient_id,
                change_type=change_type,
                entity_type=entity_type,
                entity_id=entity_id,
                old_value=old_value,
                new_value=new_value,
                significance=significance,
                detected_at=datetime.utcnow()
            )
            session.add(log)
            session.commit()
            session.refresh(log)
            return self._to_dict(log)
    
    def get_patient_changes(
        self,
        patient_id: str,
        hours: int = 24,
        unacknowledged_only: bool = False
    ) -> List[Dict]:
        with Session(self.engine) as session:
            cutoff = datetime.utcnow() - timedelta(hours=hours)
            
            conditions = [
                ChangeLog.patient_id == patient_id,
                ChangeLog.detected_at >= cutoff
            ]
            
            if unacknowledged_only:
                conditions.append(ChangeLog.acknowledged == False)
            
            statement = select(ChangeLog).where(
                and_(*conditions)
            ).order_by(desc(ChangeLog.detected_at))
            
            logs = session.exec(statement).all()
            return [self._to_dict(log) for log in logs]
    
    def get_unacknowledged_changes(
        self, 
        patient_id: Optional[str] = None
    ) -> List[Dict]:
        with Session(self.engine) as session:
            conditions = [ChangeLog.acknowledged == False]
            
            if patient_id:
                conditions.append(ChangeLog.patient_id == patient_id)
            
            statement = select(ChangeLog).where(
                and_(*conditions)
            ).order_by(desc(ChangeLog.detected_at))
            
            logs = session.exec(statement).all()
            return [self._to_dict(log) for log in logs]
    
    def get_critical_changes(
        self, 
        patient_id: Optional[str] = None,
        hours: int = 24
    ) -> List[Dict]:
        with Session(self.engine) as session:
            cutoff = datetime.utcnow() - timedelta(hours=hours)
            
            conditions = [
                ChangeLog.significance.in_(["critical", "critical_low", "high"]),
                ChangeLog.detected_at >= cutoff
            ]
            
            if patient_id:
                conditions.append(ChangeLog.patient_id == patient_id)
            
            statement = select(ChangeLog).where(
                and_(*conditions)
            ).order_by(desc(ChangeLog.detected_at))
            
            logs = session.exec(statement).all()
            return [self._to_dict(log) for log in logs]
    
    def acknowledge_change(
        self,
        change_id: int,
        acknowledged_by: Optional[str] = None
    ) -> bool:
        with Session(self.engine) as session:
            log = session.get(ChangeLog, change_id)
            if log:
                log.acknowledged = True
                log.acknowledged_by = acknowledged_by
                log.acknowledged_at = datetime.utcnow()
                session.add(log)
                session.commit()
                return True
            return False
    
    def acknowledge_all_for_patient(
        self,
        patient_id: str,
        acknowledged_by: Optional[str] = None
    ) -> int:
        with Session(self.engine) as session:
            statement = select(ChangeLog).where(
                and_(
                    ChangeLog.patient_id == patient_id,
                    ChangeLog.acknowledged == False
                )
            )
            
            logs = session.exec(statement).all()
            count = 0
            
            for log in logs:
                log.acknowledged = True
                log.acknowledged_by = acknowledged_by
                log.acknowledged_at = datetime.utcnow()
                session.add(log)
                count += 1
            
            session.commit()
            return count
    
    def get_change_summary(
        self, 
        patient_id: str, 
        hours: int = 24
    ) -> Dict:
        with Session(self.engine) as session:
            cutoff = datetime.utcnow() - timedelta(hours=hours)
            
            statement = select(ChangeLog).where(
                and_(
                    ChangeLog.patient_id == patient_id,
                    ChangeLog.detected_at >= cutoff
                )
            )
            
            logs = session.exec(statement).all()
            
            summary = {
                "patient_id": patient_id,
                "period_hours": hours,
                "total_changes": len(logs),
                "unacknowledged": 0,
                "by_type": {},
                "by_significance": {},
                "critical_count": 0
            }
            
            for log in logs:
                if not log.acknowledged:
                    summary["unacknowledged"] += 1
                
                if log.change_type not in summary["by_type"]:
                    summary["by_type"][log.change_type] = 0
                summary["by_type"][log.change_type] += 1
                
                sig = log.significance or "normal"
                if sig not in summary["by_significance"]:
                    summary["by_significance"][sig] = 0
                summary["by_significance"][sig] += 1
                
                if sig in ["critical", "critical_low"]:
                    summary["critical_count"] += 1
            
            return summary
    
    def get_changes_by_type(
        self,
        patient_id: str,
        change_type: str,
        days: int = 7
    ) -> List[Dict]:
        with Session(self.engine) as session:
            cutoff = datetime.utcnow() - timedelta(days=days)
            
            statement = select(ChangeLog).where(
                and_(
                    ChangeLog.patient_id == patient_id,
                    ChangeLog.change_type == change_type,
                    ChangeLog.detected_at >= cutoff
                )
            ).order_by(desc(ChangeLog.detected_at))
            
            logs = session.exec(statement).all()
            return [self._to_dict(log) for log in logs]
    
    def delete_old_logs(self, days: int = 90) -> int:
        with Session(self.engine) as session:
            cutoff = datetime.utcnow() - timedelta(days=days)
            
            statement = select(ChangeLog).where(
                and_(
                    ChangeLog.detected_at < cutoff,
                    ChangeLog.acknowledged == True
                )
            )
            
            logs = session.exec(statement).all()
            count = len(logs)
            
            for log in logs:
                session.delete(log)
            
            session.commit()
            return count
    
    def get_recent_activity(
        self,
        limit: int = 50
    ) -> List[Dict]:
        with Session(self.engine) as session:
            statement = select(ChangeLog).order_by(
                desc(ChangeLog.detected_at)
            ).limit(limit)
            
            logs = session.exec(statement).all()
            return [self._to_dict(log) for log in logs]
    
    def _to_dict(self, log: ChangeLog) -> Dict:
        return {
            "id": log.id,
            "patient_id": log.patient_id,
            "change_type": log.change_type,
            "entity_type": log.entity_type,
            "entity_id": log.entity_id,
            "old_value": log.old_value,
            "new_value": log.new_value,
            "significance": log.significance,
            "detected_at": log.detected_at.isoformat() if log.detected_at else None,
            "acknowledged": log.acknowledged,
            "acknowledged_by": log.acknowledged_by,
            "acknowledged_at": log.acknowledged_at.isoformat() if log.acknowledged_at else None,
            "created_at": log.created_at.isoformat() if log.created_at else None
        }