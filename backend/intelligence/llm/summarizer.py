from typing import Dict, List, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass


@dataclass
class PatientSummary:
    patient_id: str
    summary_type: str
    content: str
    generated_at: datetime
    data_points_used: int
    time_range_hours: int


class Summarizer:
    def __init__(self):
        self.summary_templates = self._load_templates()
    
    def _load_templates(self) -> Dict[str, str]:
        return {
            "sbar": """
SITUATION:
{situation}

BACKGROUND:
{background}

ASSESSMENT:
{assessment}

RECOMMENDATION:
{recommendation}
""",
            "shift_handoff": """
PATIENT: {patient_name} | Room: {room} | Age: {age} {gender}
DIAGNOSIS: {diagnosis}
CODE STATUS: {code_status}

VITAL SIGNS TREND:
{vitals_summary}

MEDICATIONS:
{medications_summary}

KEY EVENTS THIS SHIFT:
{events}

PENDING TASKS:
{pending_tasks}

CONCERNS/RECOMMENDATIONS:
{concerns}
""",
            "brief": """
{patient_name} ({age}{gender}) - Room {room}
Dx: {diagnosis}
Current: {current_status}
Trend: {trend_summary}
Action: {action_items}
""",
            "vitals_summary": """
VITAL SIGNS SUMMARY - {time_range}

Current Values:
{current_vitals}

Changes from Baseline:
{delta_summary}

Clinical Significance:
{significance}

Trending:
{trends}
"""
        }
    
    def generate_sbar(
        self,
        patient_data: Dict,
        vitals: List[Dict],
        medications: List[Dict],
        recent_events: List[str] = None
    ) -> PatientSummary:
        situation = self._build_situation(patient_data, vitals)
        background = self._build_background(patient_data, medications)
        assessment = self._build_assessment(vitals, patient_data)
        recommendation = self._build_recommendation(vitals, medications)
        
        content = self.summary_templates["sbar"].format(
            situation=situation,
            background=background,
            assessment=assessment,
            recommendation=recommendation
        )
        
        return PatientSummary(
            patient_id=patient_data.get("id", ""),
            summary_type="sbar",
            content=content.strip(),
            generated_at=datetime.utcnow(),
            data_points_used=len(vitals) + len(medications),
            time_range_hours=24
        )
    
    def generate_shift_handoff(
        self,
        patient_data: Dict,
        vitals: List[Dict],
        medications: List[Dict],
        events: List[str] = None,
        pending_tasks: List[str] = None
    ) -> PatientSummary:
        vitals_summary = self._summarize_vitals_trend(vitals)
        meds_summary = self._summarize_medications(medications)
        
        content = self.summary_templates["shift_handoff"].format(
            patient_name=patient_data.get("name", "Unknown"),
            room=patient_data.get("room", "N/A"),
            age=patient_data.get("age", "N/A"),
            gender=patient_data.get("gender", "")[0] if patient_data.get("gender") else "",
            diagnosis=patient_data.get("primary_diagnosis", "N/A"),
            code_status=patient_data.get("code_status", "Full Code"),
            vitals_summary=vitals_summary,
            medications_summary=meds_summary,
            events="\n".join(f"- {e}" for e in (events or ["No significant events"])),
            pending_tasks="\n".join(f"- {t}" for t in (pending_tasks or ["None pending"])),
            concerns=self._identify_concerns(vitals, medications)
        )
        
        return PatientSummary(
            patient_id=patient_data.get("id", ""),
            summary_type="shift_handoff",
            content=content.strip(),
            generated_at=datetime.utcnow(),
            data_points_used=len(vitals) + len(medications) + len(events or []),
            time_range_hours=12
        )
    
    def generate_brief_summary(
        self,
        patient_data: Dict,
        vitals: List[Dict],
        delta_metrics: Dict = None
    ) -> PatientSummary:
        current_status = self._get_current_status(vitals)
        trend_summary = self._get_trend_summary(delta_metrics)
        action_items = self._get_action_items(vitals, delta_metrics)
        
        content = self.summary_templates["brief"].format(
            patient_name=patient_data.get("name", "Unknown"),
            age=patient_data.get("age", ""),
            gender=patient_data.get("gender", "")[0] if patient_data.get("gender") else "",
            room=patient_data.get("room", "N/A"),
            diagnosis=patient_data.get("primary_diagnosis", "N/A"),
            current_status=current_status,
            trend_summary=trend_summary,
            action_items=action_items
        )
        
        return PatientSummary(
            patient_id=patient_data.get("id", ""),
            summary_type="brief",
            content=content.strip(),
            generated_at=datetime.utcnow(),
            data_points_used=len(vitals),
            time_range_hours=24
        )
    
    def generate_vitals_summary(
        self,
        patient_id: str,
        vitals: List[Dict],
        delta_metrics: Dict = None,
        hours: int = 24
    ) -> PatientSummary:
        current_vitals = self._format_current_vitals(vitals)
        delta_summary = self._format_delta_summary(delta_metrics)
        significance = self._assess_clinical_significance(delta_metrics)
        trends = self._format_trends(delta_metrics)
        
        content = self.summary_templates["vitals_summary"].format(
            time_range=f"Last {hours} hours",
            current_vitals=current_vitals,
            delta_summary=delta_summary,
            significance=significance,
            trends=trends
        )
        
        return PatientSummary(
            patient_id=patient_id,
            summary_type="vitals_summary",
            content=content.strip(),
            generated_at=datetime.utcnow(),
            data_points_used=len(vitals),
            time_range_hours=hours
        )
    
    def _build_situation(self, patient: Dict, vitals: List[Dict]) -> str:
        name = patient.get("name", "Unknown patient")
        room = patient.get("room", "unknown room")
        age = patient.get("age", "unknown age")
        
        latest_vitals = vitals[0] if vitals else {}
        bp_str = ""
        if latest_vitals.get("systolic") and latest_vitals.get("diastolic"):
            bp_str = f"BP {latest_vitals['systolic']}/{latest_vitals['diastolic']}"
        
        return f"{name} in room {room}, {age} years old. {bp_str}"
    
    def _build_background(self, patient: Dict, medications: List[Dict]) -> str:
        diagnosis = patient.get("primary_diagnosis", "No diagnosis listed")
        allergies = patient.get("allergies", "No known allergies")
        
        med_count = len(medications)
        med_str = f"{med_count} active medications" if med_count > 0 else "No active medications"
        
        return f"Admitted with {diagnosis}. Allergies: {allergies}. {med_str}."
    
    def _build_assessment(self, vitals: List[Dict], patient: Dict) -> str:
        if not vitals:
            return "No recent vital signs available for assessment."
        
        assessments = []
        latest = vitals[0] if vitals else {}
        
        systolic = latest.get("systolic")
        if systolic:
            if systolic >= 180:
                assessments.append("Critically elevated blood pressure")
            elif systolic >= 140:
                assessments.append("Elevated blood pressure")
            elif systolic < 90:
                assessments.append("Hypotension noted")
        
        hr = latest.get("heart_rate")
        if hr:
            if hr >= 120:
                assessments.append("Tachycardia")
            elif hr < 60:
                assessments.append("Bradycardia")
        
        spo2 = latest.get("spo2")
        if spo2 and spo2 < 92:
            assessments.append(f"Hypoxemia (SpO2 {spo2}%)")
        
        if not assessments:
            assessments.append("Vital signs within acceptable parameters")
        
        return ". ".join(assessments) + "."
    
    def _build_recommendation(self, vitals: List[Dict], medications: List[Dict]) -> str:
        recommendations = []
        
        if vitals:
            latest = vitals[0]
            if latest.get("systolic", 0) >= 160:
                recommendations.append("Consider antihypertensive intervention")
            if latest.get("spo2", 100) < 92:
                recommendations.append("Assess respiratory status and oxygen needs")
        
        if not recommendations:
            recommendations.append("Continue current monitoring and care plan")
        
        return ". ".join(recommendations) + "."
    
    def _summarize_vitals_trend(self, vitals: List[Dict]) -> str:
        if not vitals:
            return "No vital signs recorded"
        
        latest = vitals[0] if vitals else {}
        
        lines = []
        if latest.get("systolic") and latest.get("diastolic"):
            lines.append(f"BP: {latest['systolic']}/{latest['diastolic']} mmHg")
        if latest.get("heart_rate"):
            lines.append(f"HR: {latest['heart_rate']} bpm")
        if latest.get("temperature"):
            lines.append(f"Temp: {latest['temperature']}C")
        if latest.get("spo2"):
            lines.append(f"SpO2: {latest['spo2']}%")
        if latest.get("respiratory_rate"):
            lines.append(f"RR: {latest['respiratory_rate']}/min")
        
        return "\n".join(lines) if lines else "No data available"
    
    def _summarize_medications(self, medications: List[Dict]) -> str:
        if not medications:
            return "No active medications"
        
        lines = []
        for med in medications[:10]:
            line = f"- {med.get('name', 'Unknown')}"
            if med.get("dose"):
                line += f" {med['dose']}"
            if med.get("frequency"):
                line += f" {med['frequency']}"
            lines.append(line)
        
        if len(medications) > 10:
            lines.append(f"... and {len(medications) - 10} more")
        
        return "\n".join(lines)
    
    def _identify_concerns(self, vitals: List[Dict], medications: List[Dict]) -> str:
        concerns = []
        
        if vitals:
            latest = vitals[0]
            if latest.get("systolic", 0) >= 160:
                concerns.append("Elevated blood pressure requires monitoring")
            if latest.get("spo2", 100) < 94:
                concerns.append("Low oxygen saturation")
            if latest.get("heart_rate", 0) >= 110:
                concerns.append("Tachycardia")
        
        if not concerns:
            return "No immediate concerns identified"
        
        return "\n".join(f"- {c}" for c in concerns)
    
    def _get_current_status(self, vitals: List[Dict]) -> str:
        if not vitals:
            return "No recent data"
        
        latest = vitals[0]
        parts = []
        
        if latest.get("systolic") and latest.get("diastolic"):
            parts.append(f"BP {latest['systolic']}/{latest['diastolic']}")
        if latest.get("heart_rate"):
            parts.append(f"HR {latest['heart_rate']}")
        if latest.get("spo2"):
            parts.append(f"O2 {latest['spo2']}%")
        
        return ", ".join(parts) if parts else "Vitals pending"
    
    def _get_trend_summary(self, delta_metrics: Dict) -> str:
        if not delta_metrics or not delta_metrics.get("deltas"):
            return "Insufficient data for trending"
        
        trends = []
        for vital, data in delta_metrics.get("deltas", {}).items():
            trend = data.get("trend", "stable")
            if trend != "stable":
                trends.append(f"{vital}: {trend}")
        
        return ", ".join(trends) if trends else "All parameters stable"
    
    def _get_action_items(self, vitals: List[Dict], delta_metrics: Dict) -> str:
        actions = []
        
        if delta_metrics and delta_metrics.get("alerts"):
            actions.extend(delta_metrics["alerts"][:2])
        
        if not actions:
            actions.append("Continue routine monitoring")
        
        return "; ".join(actions)
    
    def _format_current_vitals(self, vitals: List[Dict]) -> str:
        if not vitals:
            return "No current vital signs available"
        
        latest = vitals[0]
        lines = []
        
        vital_labels = {
            "systolic": ("Blood Pressure", "/{diastolic} mmHg"),
            "heart_rate": ("Heart Rate", " bpm"),
            "temperature": ("Temperature", " C"),
            "spo2": ("Oxygen Saturation", "%"),
            "respiratory_rate": ("Respiratory Rate", "/min"),
            "weight": ("Weight", " kg"),
            "glucose": ("Blood Glucose", " mg/dL")
        }
        
        for key, (label, suffix) in vital_labels.items():
            value = latest.get(key)
            if value is not None:
                if key == "systolic" and latest.get("diastolic"):
                    lines.append(f"{label}: {value}/{latest['diastolic']} mmHg")
                elif key != "diastolic":
                    lines.append(f"{label}: {value}{suffix}")
        
        return "\n".join(lines) if lines else "No data"
    
    def _format_delta_summary(self, delta_metrics: Dict) -> str:
        if not delta_metrics or not delta_metrics.get("deltas"):
            return "No comparison data available"
        
        lines = []
        for vital, data in delta_metrics.get("deltas", {}).items():
            if data.get("vs_yesterday"):
                change = data["vs_yesterday"].get("absolute_change", 0)
                if change != 0:
                    sign = "+" if change > 0 else ""
                    lines.append(f"{vital}: {sign}{change:.1f} from yesterday")
        
        return "\n".join(lines) if lines else "No significant changes"
    
    def _assess_clinical_significance(self, delta_metrics: Dict) -> str:
        if not delta_metrics or not delta_metrics.get("clinical_status"):
            return "Unable to assess"
        
        critical = []
        elevated = []
        
        for vital, status in delta_metrics.get("clinical_status", {}).items():
            if status in ["critical", "critical_low"]:
                critical.append(vital)
            elif status in ["high", "elevated"]:
                elevated.append(vital)
        
        if critical:
            return f"CRITICAL: {', '.join(critical)}"
        elif elevated:
            return f"Elevated: {', '.join(elevated)}"
        else:
            return "All values within normal limits"
    
    def _format_trends(self, delta_metrics: Dict) -> str:
        if not delta_metrics or not delta_metrics.get("deltas"):
            return "Trending data unavailable"
        
        lines = []
        for vital, data in delta_metrics.get("deltas", {}).items():
            trend = data.get("trend", "stable")
            if trend != "stable":
                arrow = "↑" if "increasing" in trend else "↓"
                speed = "rapidly " if "rapidly" in trend else ""
                lines.append(f"{vital}: {arrow} {speed}{trend.replace('rapidly_', '').replace('_', ' ')}")
        
        return "\n".join(lines) if lines else "All parameters trending stable"