from typing import Dict, List, Optional, Callable, Any
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum
import asyncio
from collections import defaultdict


class NotificationPriority(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class NotificationType(Enum):
    VITAL_ALERT = "vital_alert"
    MEDICATION_DUE = "medication_due"
    MEDICATION_OVERDUE = "medication_overdue"
    PATIENT_UPDATE = "patient_update"
    CLINICAL_CHANGE = "clinical_change"
    SYSTEM_MESSAGE = "system_message"
    TASK_REMINDER = "task_reminder"


@dataclass
class Notification:
    id: str
    notification_type: NotificationType
    priority: NotificationPriority
    title: str
    message: str
    patient_id: Optional[str]
    data: Dict
    created_at: datetime
    expires_at: Optional[datetime]
    acknowledged: bool = False
    acknowledged_at: Optional[datetime] = None
    acknowledged_by: Optional[str] = None


@dataclass
class NotificationRule:
    rule_id: str
    name: str
    condition: Callable[[Dict], bool]
    notification_type: NotificationType
    priority: NotificationPriority
    title_template: str
    message_template: str
    cooldown_minutes: int = 30
    enabled: bool = True


class NotificationEngine:
    def __init__(self):
        self.notifications: Dict[str, Notification] = {}
        self.rules: Dict[str, NotificationRule] = {}
        self.subscribers: Dict[str, List[Callable]] = defaultdict(list)
        self.cooldowns: Dict[str, datetime] = {}
        self.notification_counter = 0
        
        self._register_default_rules()
    
    def _register_default_rules(self):
        self.register_rule(NotificationRule(
            rule_id="critical_bp",
            name="Critical Blood Pressure",
            condition=lambda d: (
                d.get("vital_type") == "systolic" and 
                (d.get("value", 0) >= 180 or d.get("value", 0) <= 70)
            ),
            notification_type=NotificationType.VITAL_ALERT,
            priority=NotificationPriority.CRITICAL,
            title_template="Critical BP Alert",
            message_template="Blood pressure {value} mmHg requires immediate attention",
            cooldown_minutes=15
        ))
        
        self.register_rule(NotificationRule(
            rule_id="critical_hr",
            name="Critical Heart Rate",
            condition=lambda d: (
                d.get("vital_type") == "heart_rate" and
                (d.get("value", 0) >= 150 or d.get("value", 0) <= 40)
            ),
            notification_type=NotificationType.VITAL_ALERT,
            priority=NotificationPriority.CRITICAL,
            title_template="Critical HR Alert",
            message_template="Heart rate {value} bpm requires immediate attention",
            cooldown_minutes=15
        ))
        
        self.register_rule(NotificationRule(
            rule_id="low_spo2",
            name="Low Oxygen Saturation",
            condition=lambda d: (
                d.get("vital_type") == "spo2" and
                d.get("value", 100) < 90
            ),
            notification_type=NotificationType.VITAL_ALERT,
            priority=NotificationPriority.CRITICAL,
            title_template="Low SpO2 Alert",
            message_template="Oxygen saturation {value}% - consider supplemental O2",
            cooldown_minutes=10
        ))
        
        self.register_rule(NotificationRule(
            rule_id="elevated_bp",
            name="Elevated Blood Pressure",
            condition=lambda d: (
                d.get("vital_type") == "systolic" and
                140 <= d.get("value", 0) < 180
            ),
            notification_type=NotificationType.VITAL_ALERT,
            priority=NotificationPriority.HIGH,
            title_template="Elevated BP",
            message_template="Blood pressure elevated at {value} mmHg",
            cooldown_minutes=60
        ))
        
        self.register_rule(NotificationRule(
            rule_id="fever",
            name="Fever Detection",
            condition=lambda d: (
                d.get("vital_type") == "temperature" and
                d.get("value", 0) >= 38.5
            ),
            notification_type=NotificationType.VITAL_ALERT,
            priority=NotificationPriority.HIGH,
            title_template="Fever Alert",
            message_template="Temperature elevated at {value}C",
            cooldown_minutes=60
        ))
        
        self.register_rule(NotificationRule(
            rule_id="hypoglycemia",
            name="Hypoglycemia",
            condition=lambda d: (
                d.get("vital_type") == "glucose" and
                d.get("value", 100) < 70
            ),
            notification_type=NotificationType.VITAL_ALERT,
            priority=NotificationPriority.CRITICAL,
            title_template="Hypoglycemia Alert",
            message_template="Blood glucose {value} mg/dL - treat immediately",
            cooldown_minutes=15
        ))
        
        self.register_rule(NotificationRule(
            rule_id="significant_change",
            name="Significant Clinical Change",
            condition=lambda d: d.get("significance") in ["critical", "critical_low", "high"],
            notification_type=NotificationType.CLINICAL_CHANGE,
            priority=NotificationPriority.HIGH,
            title_template="Clinical Change Detected",
            message_template="{change_description}",
            cooldown_minutes=30
        ))
    
    def register_rule(self, rule: NotificationRule) -> None:
        self.rules[rule.rule_id] = rule
    
    def unregister_rule(self, rule_id: str) -> bool:
        if rule_id in self.rules:
            del self.rules[rule_id]
            return True
        return False
    
    def subscribe(
        self,
        event_type: str,
        callback: Callable[[Notification], Any]
    ) -> str:
        subscription_id = f"sub_{len(self.subscribers[event_type])}"
        self.subscribers[event_type].append(callback)
        return subscription_id
    
    async def evaluate_and_notify(
        self,
        data: Dict,
        patient_id: Optional[str] = None
    ) -> List[Notification]:
        generated_notifications = []
        
        for rule in self.rules.values():
            if not rule.enabled:
                continue
            
            cooldown_key = f"{rule.rule_id}:{patient_id or 'global'}"
            if cooldown_key in self.cooldowns:
                if datetime.utcnow() < self.cooldowns[cooldown_key]:
                    continue
            
            try:
                if rule.condition(data):
                    notification = self._create_notification(rule, data, patient_id)
                    generated_notifications.append(notification)
                    
                    self.cooldowns[cooldown_key] = (
                        datetime.utcnow() + timedelta(minutes=rule.cooldown_minutes)
                    )
                    
                    await self._dispatch_notification(notification)
            except Exception:
                continue
        
        return generated_notifications
    
    def _create_notification(
        self,
        rule: NotificationRule,
        data: Dict,
        patient_id: Optional[str]
    ) -> Notification:
        self.notification_counter += 1
        notification_id = f"notif_{self.notification_counter}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
        
        title = rule.title_template
        message = rule.message_template
        
        for key, value in data.items():
            title = title.replace(f"{{{key}}}", str(value))
            message = message.replace(f"{{{key}}}", str(value))
        
        notification = Notification(
            id=notification_id,
            notification_type=rule.notification_type,
            priority=rule.priority,
            title=title,
            message=message,
            patient_id=patient_id,
            data=data,
            created_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(hours=24)
        )
        
        self.notifications[notification_id] = notification
        return notification
    
    async def _dispatch_notification(self, notification: Notification) -> None:
        event_types = [
            notification.notification_type.value,
            notification.priority.value,
            "all"
        ]
        
        for event_type in event_types:
            for callback in self.subscribers.get(event_type, []):
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(notification)
                    else:
                        callback(notification)
                except Exception:
                    continue
    
    def acknowledge_notification(
        self,
        notification_id: str,
        acknowledged_by: Optional[str] = None
    ) -> bool:
        if notification_id in self.notifications:
            notification = self.notifications[notification_id]
            notification.acknowledged = True
            notification.acknowledged_at = datetime.utcnow()
            notification.acknowledged_by = acknowledged_by
            return True
        return False
    
    def get_active_notifications(
        self,
        patient_id: Optional[str] = None,
        priority: Optional[NotificationPriority] = None,
        notification_type: Optional[NotificationType] = None
    ) -> List[Notification]:
        now = datetime.utcnow()
        
        notifications = [
            n for n in self.notifications.values()
            if not n.acknowledged and (n.expires_at is None or n.expires_at > now)
        ]
        
        if patient_id:
            notifications = [n for n in notifications if n.patient_id == patient_id]
        
        if priority:
            notifications = [n for n in notifications if n.priority == priority]
        
        if notification_type:
            notifications = [n for n in notifications if n.notification_type == notification_type]
        
        priority_order = {
            NotificationPriority.CRITICAL: 0,
            NotificationPriority.HIGH: 1,
            NotificationPriority.MEDIUM: 2,
            NotificationPriority.LOW: 3
        }
        
        notifications.sort(key=lambda n: (
            priority_order.get(n.priority, 4),
            n.created_at
        ))
        
        return notifications
    
    def get_notification_count(
        self,
        patient_id: Optional[str] = None
    ) -> Dict[str, int]:
        notifications = self.get_active_notifications(patient_id)
        
        counts = {
            "total": len(notifications),
            "critical": 0,
            "high": 0,
            "medium": 0,
            "low": 0
        }
        
        for n in notifications:
            counts[n.priority.value] += 1
        
        return counts
    
    async def create_medication_reminder(
        self,
        patient_id: str,
        medication_name: str,
        due_time: datetime
    ) -> Notification:
        self.notification_counter += 1
        notification_id = f"med_{self.notification_counter}"
        
        notification = Notification(
            id=notification_id,
            notification_type=NotificationType.MEDICATION_DUE,
            priority=NotificationPriority.MEDIUM,
            title="Medication Due",
            message=f"{medication_name} is due for administration",
            patient_id=patient_id,
            data={
                "medication_name": medication_name,
                "due_time": due_time.isoformat()
            },
            created_at=datetime.utcnow(),
            expires_at=due_time + timedelta(hours=2)
        )
        
        self.notifications[notification_id] = notification
        await self._dispatch_notification(notification)
        
        return notification
    
    async def check_overdue_medications(self, patient_id: str) -> List[Notification]:
        from database.repo.meds_repo import MedicationRepository
        
        repo = MedicationRepository()
        due_meds = repo.get_due_medications(patient_id, window_hours=0)
        
        notifications = []
        for med in due_meds:
            if med.get("hours_until", 0) < 0:
                notification = await self._create_overdue_notification(
                    patient_id,
                    med.get("name", "Unknown medication"),
                    abs(med.get("hours_until", 0))
                )
                notifications.append(notification)
        
        return notifications
    
    async def _create_overdue_notification(
        self,
        patient_id: str,
        medication_name: str,
        hours_overdue: float
    ) -> Notification:
        self.notification_counter += 1
        notification_id = f"overdue_{self.notification_counter}"
        
        notification = Notification(
            id=notification_id,
            notification_type=NotificationType.MEDICATION_OVERDUE,
            priority=NotificationPriority.HIGH,
            title="Medication Overdue",
            message=f"{medication_name} is {hours_overdue:.1f} hours overdue",
            patient_id=patient_id,
            data={
                "medication_name": medication_name,
                "hours_overdue": hours_overdue
            },
            created_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(hours=4)
        )
        
        self.notifications[notification_id] = notification
        await self._dispatch_notification(notification)
        
        return notification
    
    def clear_expired_notifications(self) -> int:
        now = datetime.utcnow()
        expired_ids = [
            nid for nid, n in self.notifications.items()
            if n.expires_at and n.expires_at < now
        ]
        
        for nid in expired_ids:
            del self.notifications[nid]
        
        return len(expired_ids)
    
    def to_dict(self, notification: Notification) -> Dict:
        return {
            "id": notification.id,
            "type": notification.notification_type.value,
            "priority": notification.priority.value,
            "title": notification.title,
            "message": notification.message,
            "patient_id": notification.patient_id,
            "data": notification.data,
            "created_at": notification.created_at.isoformat(),
            "expires_at": notification.expires_at.isoformat() if notification.expires_at else None,
            "acknowledged": notification.acknowledged,
            "acknowledged_at": notification.acknowledged_at.isoformat() if notification.acknowledged_at else None,
            "acknowledged_by": notification.acknowledged_by
        }