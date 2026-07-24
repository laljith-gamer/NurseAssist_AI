from dataclasses import dataclass
from typing import Dict, Optional, List, Tuple
from datetime import datetime
from enum import Enum


class VitalType(Enum):
    BP_SYSTOLIC = "systolic"
    BP_DIASTOLIC = "diastolic"
    HEART_RATE = "heart_rate"
    TEMPERATURE = "temperature"
    SPO2 = "spo2"
    RESPIRATORY_RATE = "respiratory_rate"
    WEIGHT = "weight"
    HEIGHT = "height"
    GLUCOSE = "glucose"


@dataclass
class VitalReading:
    vital_type: VitalType
    value: float
    unit: str
    timestamp: datetime
    is_valid: bool
    validation_message: Optional[str] = None


@dataclass
class RecordingResult:
    success: bool
    patient_id: str
    readings: List[VitalReading]
    warnings: List[str]
    clinical_alerts: List[str]
    delta_info: Dict
    timestamp: datetime


class VitalsRecorder:
    def __init__(self):
        self.validation_rules = {
            VitalType.BP_SYSTOLIC: {"min": 50, "max": 300, "unit": "mmHg"},
            VitalType.BP_DIASTOLIC: {"min": 30, "max": 200, "unit": "mmHg"},
            VitalType.HEART_RATE: {"min": 20, "max": 250, "unit": "bpm"},
            VitalType.TEMPERATURE: {"min": 30.0, "max": 45.0, "unit": "C"},
            VitalType.SPO2: {"min": 50, "max": 100, "unit": "%"},
            VitalType.RESPIRATORY_RATE: {"min": 4, "max": 60, "unit": "/min"},
            VitalType.WEIGHT: {"min": 0.5, "max": 500, "unit": "kg"},
            VitalType.HEIGHT: {"min": 30, "max": 250, "unit": "cm"},
            VitalType.GLUCOSE: {"min": 20, "max": 800, "unit": "mg/dL"},
        }
    
    def record(
        self, 
        patient_id: str, 
        vitals_data: Dict,
        source: str = "voice"
    ) -> RecordingResult:
        from database.repo.vitals_repo import VitalsRepository
        from core.change_detector import ChangeDetector
        
        readings = []
        warnings = []
        clinical_alerts = []
        
        if "bp" in vitals_data:
            bp = vitals_data["bp"]
            sys_reading = self._validate_and_create_reading(
                VitalType.BP_SYSTOLIC, 
                bp["systolic"]
            )
            dia_reading = self._validate_and_create_reading(
                VitalType.BP_DIASTOLIC, 
                bp["diastolic"]
            )
            readings.extend([sys_reading, dia_reading])
            
            if sys_reading.is_valid and dia_reading.is_valid:
                bp_warnings = self._check_bp_consistency(
                    bp["systolic"], 
                    bp["diastolic"]
                )
                warnings.extend(bp_warnings)
        
        vital_type_map = {
            "hr": VitalType.HEART_RATE,
            "temp": VitalType.TEMPERATURE,
            "spo2": VitalType.SPO2,
            "rr": VitalType.RESPIRATORY_RATE,
            "weight": VitalType.WEIGHT,
            "height": VitalType.HEIGHT,
            "glucose": VitalType.GLUCOSE,
        }
        
        for key, vital_type in vital_type_map.items():
            if key in vitals_data:
                reading = self._validate_and_create_reading(
                    vital_type, 
                    vitals_data[key]
                )
                readings.append(reading)
        
        valid_readings = [r for r in readings if r.is_valid]
        invalid_readings = [r for r in readings if not r.is_valid]
        
        for r in invalid_readings:
            warnings.append(f"Invalid {r.vital_type.value}: {r.validation_message}")
        
        if not valid_readings:
            return RecordingResult(
                success=False,
                patient_id=patient_id,
                readings=readings,
                warnings=warnings,
                clinical_alerts=[],
                delta_info={},
                timestamp=datetime.utcnow()
            )
        
        detector = ChangeDetector()
        vitals_for_detection = {}
        for r in valid_readings:
            vitals_for_detection[r.vital_type.value] = r.value
        
        has_significant_change, change_alerts = detector.detect_clinical_change(
            patient_id, 
            vitals_for_detection
        )
        clinical_alerts.extend(change_alerts)
        
        repo = VitalsRepository()
        
        for reading in valid_readings:
            repo.save_vital(
                patient_id=patient_id,
                vital_type=reading.vital_type.value,
                value=reading.value,
                unit=reading.unit,
                timestamp=reading.timestamp,
                source=source
            )
        
        delta_info = detector.get_delta_metrics(patient_id)
        
        return RecordingResult(
            success=True,
            patient_id=patient_id,
            readings=readings,
            warnings=warnings,
            clinical_alerts=clinical_alerts,
            delta_info=delta_info,
            timestamp=datetime.utcnow()
        )
    
    def _validate_and_create_reading(
        self, 
        vital_type: VitalType, 
        value: float
    ) -> VitalReading:
        rules = self.validation_rules.get(vital_type)
        normalized_value = float(value)

        # Allow common Fahrenheit voice/text input (e.g., "temp 98.6")
        # while storing standardized Celsius values.
        if vital_type == VitalType.TEMPERATURE and normalized_value > 70:
            normalized_value = round((normalized_value - 32) * 5 / 9, 1)
        
        if rules is None:
            return VitalReading(
                vital_type=vital_type,
                value=normalized_value,
                unit="",
                timestamp=datetime.utcnow(),
                is_valid=False,
                validation_message="Unknown vital type"
            )
        
        if normalized_value < rules["min"]:
            return VitalReading(
                vital_type=vital_type,
                value=normalized_value,
                unit=rules["unit"],
                timestamp=datetime.utcnow(),
                is_valid=False,
                validation_message=f"Value {normalized_value} below minimum {rules['min']}"
            )
        
        if normalized_value > rules["max"]:
            return VitalReading(
                vital_type=vital_type,
                value=normalized_value,
                unit=rules["unit"],
                timestamp=datetime.utcnow(),
                is_valid=False,
                validation_message=f"Value {normalized_value} above maximum {rules['max']}"
            )
        
        return VitalReading(
            vital_type=vital_type,
            value=normalized_value,
            unit=rules["unit"],
            timestamp=datetime.utcnow(),
            is_valid=True
        )
    
    def _check_bp_consistency(
        self, 
        systolic: float, 
        diastolic: float
    ) -> List[str]:
        warnings = []
        
        if diastolic >= systolic:
            warnings.append(
                f"Diastolic ({diastolic}) should be less than systolic ({systolic})"
            )
        
        pulse_pressure = systolic - diastolic
        if pulse_pressure < 20:
            warnings.append(
                f"Pulse pressure ({pulse_pressure}) is abnormally narrow"
            )
        elif pulse_pressure > 100:
            warnings.append(
                f"Pulse pressure ({pulse_pressure}) is abnormally wide"
            )
        
        return warnings
    
    def get_formatted_response(self, result: RecordingResult) -> Dict:
        valid_readings = [r for r in result.readings if r.is_valid]
        
        response = {
            "success": result.success,
            "message": "",
            "recorded_vitals": [],
            "warnings": result.warnings,
            "clinical_alerts": result.clinical_alerts,
            "delta_summary": {},
        }
        
        if not result.success:
            response["message"] = "Failed to record vitals"
            return response
        
        for reading in valid_readings:
            response["recorded_vitals"].append({
                "type": reading.vital_type.value,
                "value": reading.value,
                "unit": reading.unit,
            })
        
        vitals_str = ", ".join(
            f"{r['type']}: {r['value']} {r['unit']}" 
            for r in response["recorded_vitals"]
        )
        response["message"] = f"Recorded: {vitals_str}"
        
        if result.delta_info.get("deltas"):
            delta_parts = []
            for vital_key, delta_data in result.delta_info["deltas"].items():
                if "vs_yesterday" in delta_data:
                    change = delta_data["vs_yesterday"]["absolute_change"]
                    if change != 0:
                        sign = "+" if change > 0 else ""
                        delta_parts.append(f"{vital_key}: {sign}{change}")
            
            if delta_parts:
                response["delta_summary"] = {
                    "vs_yesterday": ", ".join(delta_parts)
                }
        
        return response
