from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from enum import Enum


class ClinicalSignificance(Enum):
    NORMAL = "normal"
    BORDERLINE = "borderline"
    ELEVATED = "elevated"
    HIGH = "high"
    CRITICAL = "critical"
    LOW = "low"
    CRITICAL_LOW = "critical_low"


class TrendDirection(Enum):
    STABLE = "stable"
    INCREASING = "increasing"
    DECREASING = "decreasing"
    RAPIDLY_INCREASING = "rapidly_increasing"
    RAPIDLY_DECREASING = "rapidly_decreasing"


@dataclass
class VitalDelta:
    current_value: float
    previous_value: Optional[float]
    absolute_change: Optional[float]
    percent_change: Optional[float]
    time_span_hours: Optional[float]
    significance: ClinicalSignificance
    trend: TrendDirection


@dataclass
class DeltaMetrics:
    patient_id: str
    timestamp: datetime
    bp_systolic: Optional[VitalDelta]
    bp_diastolic: Optional[VitalDelta]
    heart_rate: Optional[VitalDelta]
    temperature: Optional[VitalDelta]
    spo2: Optional[VitalDelta]
    respiratory_rate: Optional[VitalDelta]
    weight: Optional[VitalDelta]
    glucose: Optional[VitalDelta]
    alerts: List[str]
    vs_yesterday: Dict[str, float]
    vs_7day_avg: Dict[str, float]
    vs_baseline: Dict[str, float]


class ChangeDetector:
    def __init__(self):
        self.metric_aliases = {
            "systolic": "bp_systolic",
            "diastolic": "bp_diastolic",
            "bp_systolic": "bp_systolic",
            "bp_diastolic": "bp_diastolic",
            "heart_rate": "heart_rate",
            "temperature": "temperature",
            "spo2": "spo2",
            "respiratory_rate": "respiratory_rate",
            "glucose": "glucose",
            "weight": "weight",
            "height": "height",
        }

        self.thresholds = {
            "bp_systolic": {
                "normal": (90, 120),
                "elevated": (120, 130),
                "high_stage1": (130, 140),
                "high_stage2": (140, 180),
                "critical": (180, float("inf")),
                "low": (0, 90),
            },
            "bp_diastolic": {
                "normal": (60, 80),
                "elevated": (80, 85),
                "high_stage1": (85, 90),
                "high_stage2": (90, 120),
                "critical": (120, float("inf")),
                "low": (0, 60),
            },
            "heart_rate": {
                "critical_low": (0, 40),
                "low": (40, 60),
                "normal": (60, 100),
                "elevated": (100, 120),
                "high": (120, 150),
                "critical": (150, float("inf")),
            },
            "temperature": {
                "critical_low": (0, 35.0),
                "low": (35.0, 36.1),
                "normal": (36.1, 37.2),
                "elevated": (37.2, 38.0),
                "high": (38.0, 39.5),
                "critical": (39.5, float("inf")),
            },
            "spo2": {
                "normal": (95, 100),
                "borderline": (92, 95),
                "low": (88, 92),
                "critical_low": (0, 88),
            },
            "respiratory_rate": {
                "critical_low": (0, 8),
                "low": (8, 12),
                "normal": (12, 20),
                "elevated": (20, 25),
                "high": (25, 30),
                "critical": (30, float("inf")),
            },
            "glucose": {
                "critical_low": (0, 54),
                "low": (54, 70),
                "normal": (70, 100),
                "elevated": (100, 126),
                "high": (126, 200),
                "critical": (200, float("inf")),
            },
        }
        
        self.significant_change = {
            "bp_systolic": 20,
            "bp_diastolic": 15,
            "heart_rate": 20,
            "temperature": 0.5,
            "spo2": 3,
            "respiratory_rate": 5,
            "glucose": 30,
            "weight": 2.0,
        }
    
    def get_delta_metrics(self, patient_id: str) -> Dict:
        from database.repo.vitals_repo import VitalsRepository

        repo = VitalsRepository()
        
        current = repo.get_latest_vitals(patient_id)
        yesterday = repo.get_vitals_at_time(
            patient_id, 
            datetime.utcnow() - timedelta(days=1)
        )
        week_ago = repo.get_average_vitals(patient_id, days=7)
        baseline = repo.get_baseline_vitals(patient_id)
        
        if not current:
            return {"patient_id": patient_id, "has_data": False}
        
        metrics = {
            "patient_id": patient_id,
            "has_data": True,
            "timestamp": datetime.utcnow().isoformat(),
            "current": current,
            "deltas": {},
            "alerts": [],
            "clinical_status": {},
        }
        
        vital_mappings = [
            ("bp_systolic", "systolic"),
            ("bp_diastolic", "diastolic"),
            ("heart_rate", "heart_rate"),
            ("temperature", "temperature"),
            ("spo2", "spo2"),
            ("respiratory_rate", "respiratory_rate"),
            ("glucose", "glucose"),
            ("weight", "weight"),
        ]
        
        for metric_key, data_key in vital_mappings:
            curr_val = current.get(data_key)
            if curr_val is None:
                continue

            significance = self._get_significance(metric_key, curr_val).value

            delta_data = {
                "current": curr_val,
                "significance": significance,
            }
            
            if yesterday and yesterday.get(data_key) is not None:
                prev = yesterday[data_key]
                delta_data["vs_yesterday"] = {
                    "value": prev,
                    "absolute_change": round(curr_val - prev, 2),
                    "percent_change": round(((curr_val - prev) / prev) * 100, 1) if prev != 0 else 0,
                }
            
            if week_ago and week_ago.get(data_key) is not None:
                avg = week_ago[data_key]
                delta_data["vs_7day_avg"] = {
                    "value": round(avg, 2),
                    "absolute_change": round(curr_val - avg, 2),
                    "percent_change": round(((curr_val - avg) / avg) * 100, 1) if avg != 0 else 0,
                }
            
            if baseline and baseline.get(data_key) is not None:
                base = baseline[data_key]
                delta_data["vs_baseline"] = {
                    "value": base,
                    "absolute_change": round(curr_val - base, 2),
                    "percent_change": round(((curr_val - base) / base) * 100, 1) if base != 0 else 0,
                }
            
            trend = self._calculate_trend(patient_id, data_key, metric_key=metric_key)
            delta_data["trend"] = trend.value

            metrics["deltas"][metric_key] = delta_data
            metrics["clinical_status"][metric_key] = significance

            alerts = self._check_for_alerts(metric_key, curr_val, delta_data)
            metrics["alerts"].extend(alerts)

        return metrics

    def _get_significance(self, vital_type: str, value: float) -> ClinicalSignificance:
        canonical_key = self._canonical_metric_key(vital_type)
        if canonical_key not in self.thresholds:
            return ClinicalSignificance.NORMAL

        ranges = self.thresholds[canonical_key]
        
        if "critical" in ranges:
            low, high = ranges["critical"]
            if low <= value < high:
                return ClinicalSignificance.CRITICAL
        
        if "critical_low" in ranges:
            low, high = ranges["critical_low"]
            if low <= value < high:
                return ClinicalSignificance.CRITICAL_LOW
        
        if "high" in ranges:
            low, high = ranges["high"]
            if low <= value < high:
                return ClinicalSignificance.HIGH

        if "high_stage2" in ranges:
            low, high = ranges["high_stage2"]
            if low <= value < high:
                return ClinicalSignificance.HIGH

        if "high_stage1" in ranges:
            low, high = ranges["high_stage1"]
            if low <= value < high:
                return ClinicalSignificance.ELEVATED

        if "low" in ranges:
            low, high = ranges["low"]
            if low <= value < high:
                return ClinicalSignificance.LOW
        
        if "elevated" in ranges:
            low, high = ranges["elevated"]
            if low <= value < high:
                return ClinicalSignificance.ELEVATED
        
        if "borderline" in ranges:
            low, high = ranges["borderline"]
            if low <= value < high:
                return ClinicalSignificance.BORDERLINE

        return ClinicalSignificance.NORMAL

    def _calculate_trend(
        self,
        patient_id: str,
        vital_key: str,
        metric_key: Optional[str] = None
    ) -> TrendDirection:
        from database.repo.vitals_repo import VitalsRepository

        repo = VitalsRepository()
        readings = repo.get_recent_readings(patient_id, vital_key, count=7)
        
        if len(readings) < 3:
            return TrendDirection.STABLE
        
        values = [r["value"] for r in readings]

        diffs = [values[i] - values[i + 1] for i in range(len(values) - 1)]
        avg_diff = sum(diffs) / len(diffs) if diffs else 0

        threshold_key = self._canonical_metric_key(metric_key or vital_key)
        threshold = self.significant_change.get(threshold_key, 5) / 7
        
        if abs(avg_diff) < threshold * 0.5:
            return TrendDirection.STABLE
        elif avg_diff > threshold * 2:
            return TrendDirection.RAPIDLY_INCREASING
        elif avg_diff > threshold * 0.5:
            return TrendDirection.INCREASING
        elif avg_diff < -threshold * 2:
            return TrendDirection.RAPIDLY_DECREASING
        elif avg_diff < -threshold * 0.5:
            return TrendDirection.DECREASING
        
        return TrendDirection.STABLE
    
    def _check_for_alerts(
        self, 
        vital_type: str, 
        current_value: float, 
        delta_data: Dict
    ) -> List[str]:
        alerts = []
        
        significance = self._get_significance(vital_type, current_value)
        
        if significance == ClinicalSignificance.CRITICAL:
            alerts.append(f"CRITICAL: {vital_type.replace('_', ' ').title()} is critically high at {current_value}")
        elif significance == ClinicalSignificance.CRITICAL_LOW:
            alerts.append(f"CRITICAL: {vital_type.replace('_', ' ').title()} is critically low at {current_value}")
        
        if "vs_yesterday" in delta_data:
            change = abs(delta_data["vs_yesterday"]["absolute_change"])
            threshold = self.significant_change.get(vital_type, float("inf"))
            if change >= threshold:
                direction = "increased" if delta_data["vs_yesterday"]["absolute_change"] > 0 else "decreased"
                alerts.append(
                    f"Significant change: {vital_type.replace('_', ' ').title()} "
                    f"{direction} by {change} since yesterday"
                )
        
        return alerts
    
    def detect_clinical_change(
        self, 
        patient_id: str, 
        new_vitals: Dict
    ) -> Tuple[bool, List[str]]:
        from database.repo.vitals_repo import VitalsRepository
        
        repo = VitalsRepository()
        previous = repo.get_latest_vitals(patient_id)
        
        if not previous:
            return False, []
        
        changes = []
        significant = False
        
        for vital_key, new_value in new_vitals.items():
            if new_value is None:
                continue

            old_value = previous.get(vital_key)
            if old_value is None:
                continue

            metric_key = self._canonical_metric_key(vital_key)
            change = new_value - old_value
            threshold = self.significant_change.get(metric_key, float("inf"))

            if abs(change) >= threshold:
                significant = True
                direction = "increased" if change > 0 else "decreased"
                changes.append(
                    f"{vital_key.replace('_', ' ').title()} {direction} "
                    f"by {abs(change):.1f} (was {old_value}, now {new_value})"
                )
            
            old_sig = self._get_significance(vital_key, old_value)
            new_sig = self._get_significance(vital_key, new_value)
            
            if old_sig != new_sig:
                significant = True
                changes.append(
                    f"{vital_key.replace('_', ' ').title()} clinical status changed "
                    f"from {old_sig.value} to {new_sig.value}"
                )

        return significant, changes

    def _canonical_metric_key(self, vital_type: str) -> str:
        return self.metric_aliases.get(vital_type, vital_type)
