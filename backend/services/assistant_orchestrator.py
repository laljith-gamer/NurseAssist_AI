from typing import Dict, Optional, Any
from datetime import datetime
import math
import re

from core.router import InputRouter, RouteType
from core.deterministic.vitals_recorder import VitalsRecorder
from core.deterministic.medication_recorder import MedicationRecorder
from core.deterministic.patient_selector import PatientSelector
from core.deterministic.command_executor import CommandExecutor
from core.change_detector import ChangeDetector
from nlp.preprocessor import TextPreprocessor
from nlp.intent_classifier import IntentClassifier, Intent
from nlp.entity_extractor import EntityExtractor
from config import settings


class AssistantOrchestrator:
    def __init__(self):
        self.router = InputRouter()
        self.preprocessor = TextPreprocessor()
        self.intent_classifier = IntentClassifier()
        self.entity_extractor = EntityExtractor()
        
        self.vitals_recorder = VitalsRecorder()
        self.medication_recorder = MedicationRecorder()
        self.patient_selector = PatientSelector()
        self.command_executor = CommandExecutor()
        self.change_detector = ChangeDetector()
        
        self.session_context = {}
        self._llm = None
        self._retriever = None
    
    async def process_input(
        self,
        text: str,
        patient_id: Optional[str] = None,
        context: Optional[Dict] = None
    ) -> Dict[str, Any]:
        if not text or not text.strip():
            return self._create_response(
                success=False,
                message="No input provided",
                response_type="error"
            )
        
        context = context or {}
        patient_id = patient_id or context.get("patient_id")
        normalized_text = self.preprocessor.preprocess(text).normalized or text

        if self._is_simple_greeting(normalized_text):
            return self._create_response(
                success=True,
                message=self._build_greeting_response(patient_id),
                response_type="greeting",
                data={
                    "suggestions": [
                        "Show current vitals",
                        "List due medications",
                        "Summarize overnight changes",
                    ]
                }
            )

        if self._is_summary_request(normalized_text):
            return await self._handle_fast_summary(patient_id, normalized_text)

        if self._is_patient_name_request(normalized_text):
            return await self._handle_patient_name_query(patient_id)

        if self._is_vitals_history_request(normalized_text):
            return await self._handle_vitals_history_query(patient_id, normalized_text)
        
        routing_result = self.router.route(text)
        
        if routing_result.route_type == RouteType.DETERMINISTIC_VITALS:
            return await self._handle_vitals(
                routing_result.extracted_data,
                patient_id,
                context
            )
        
        elif routing_result.route_type == RouteType.DETERMINISTIC_MEDS:
            return await self._handle_medication(
                routing_result.extracted_data,
                patient_id,
                context
            )
        
        elif routing_result.route_type == RouteType.DETERMINISTIC_PATIENT:
            return await self._handle_patient_selection(
                routing_result.extracted_data,
                context
            )
        
        elif routing_result.route_type == RouteType.DETERMINISTIC_COMMAND:
            return await self._handle_command(
                routing_result.extracted_data,
                patient_id,
                context
            )
        
        elif routing_result.route_type == RouteType.NLP_REQUIRED:
            return await self._handle_nlp_path(text, patient_id, context)
        
        elif routing_result.route_type == RouteType.LLM_REQUIRED:
            return await self._run_llm_with_deadline(text, patient_id, context)
        
        return self._create_response(
            success=False,
            message="Unable to process request",
            response_type="error"
        )
    
    async def _handle_vitals(
        self,
        extracted_data: Dict,
        patient_id: Optional[str],
        context: Dict
    ) -> Dict[str, Any]:
        if not patient_id:
            return self._create_response(
                success=False,
                message="Please select a patient first",
                response_type="error",
                requires_patient=True
            )
        
        result = self.vitals_recorder.record(patient_id, extracted_data)
        response = self.vitals_recorder.get_formatted_response(result)
        
        return self._create_response(
            success=result.success,
            message=response["message"],
            response_type="vitals_recorded",
            data={
                "recorded_vitals": response["recorded_vitals"],
                "warnings": response["warnings"],
                "clinical_alerts": response["clinical_alerts"],
                "delta_summary": response.get("delta_summary", {}),
            },
            broadcast=result.success,
            broadcast_data={
                "type": "vitals_update",
                "patient_id": patient_id,
                "vitals": response["recorded_vitals"],
                "timestamp": datetime.utcnow().isoformat()
            }
        )
    
    async def _handle_medication(
        self,
        extracted_data: Dict,
        patient_id: Optional[str],
        context: Dict
    ) -> Dict[str, Any]:
        if not patient_id:
            return self._create_response(
                success=False,
                message="Please select a patient first",
                response_type="error",
                requires_patient=True
            )
        
        action = extracted_data.get("action", "given")
        medication = extracted_data.get("medication", "")
        
        result = self.medication_recorder.record(
            patient_id=patient_id,
            action=action,
            medication_text=medication
        )
        
        response = self.medication_recorder.get_formatted_response(result)
        
        return self._create_response(
            success=result.success,
            message=response["message"],
            response_type="medication_recorded",
            data={
                "medication": response["medication"],
                "warnings": response["warnings"],
                "next_due": response["next_due"],
                "adherence": response["adherence"]
            },
            broadcast=result.success,
            broadcast_data={
                "type": "medication_update",
                "patient_id": patient_id,
                "medication": response["medication"],
                "timestamp": datetime.utcnow().isoformat()
            }
        )
    
    async def _handle_patient_selection(
        self,
        extracted_data: Dict,
        context: Dict
    ) -> Dict[str, Any]:
        selection_type = extracted_data.get("selection_type", "name")
        identifier = extracted_data.get("identifier", "")
        
        result = self.patient_selector.select(
            identifier=identifier,
            selection_type=selection_type,
            context=context
        )
        
        response = self.patient_selector.get_formatted_response(result)
        
        if result.success and result.patient:
            self.session_context["current_patient_id"] = result.patient.patient_id
        
        return self._create_response(
            success=result.success,
            message=response["message"],
            response_type="patient_selected" if result.success else "patient_selection_needed",
            data={
                "patient": response["patient"],
                "alternatives": response["alternatives"],
                "summary": response["summary"]
            },
            patient_id=result.patient.patient_id if result.patient else None
        )
    
    async def _handle_command(
        self,
        extracted_data: Dict,
        patient_id: Optional[str],
        context: Dict
    ) -> Dict[str, Any]:
        command = extracted_data.get("command", "help")
        
        result = self.command_executor.execute(
            command=command,
            patient_id=patient_id,
            context=context
        )
        
        response = self.command_executor.get_formatted_response(result)
        
        return self._create_response(
            success=result.success,
            message=response["message"],
            response_type=f"command_{command}",
            data=response["data"]
        )
    
    async def _handle_nlp_path(
        self,
        text: str,
        patient_id: Optional[str],
        context: Dict
    ) -> Dict[str, Any]:
        preprocessed = self.preprocessor.preprocess(text)
        normalized_text = preprocessed.normalized or text
        intent_result = self.intent_classifier.classify(normalized_text)
        extraction_result = self.entity_extractor.extract(normalized_text)
        
        if intent_result.intent == Intent.RECORD_VITALS:
            if extraction_result.vitals:
                return await self._handle_vitals(
                    extraction_result.vitals,
                    patient_id,
                    context
                )
        
        elif intent_result.intent == Intent.RECORD_MEDICATION:
            if extraction_result.medications.get("name"):
                return await self._handle_medication(
                    {
                        "action": "given",
                        "medication": extraction_result.medications.get("name")
                    },
                    patient_id,
                    context
                )
        
        elif intent_result.intent == Intent.SELECT_PATIENT:
            if extraction_result.patient_identifiers:
                return await self._handle_patient_selection(
                    {
                        "selection_type": "room" if "patient_room" in extraction_result.patient_identifiers else "name",
                        "identifier": list(extraction_result.patient_identifiers.values())[0]
                    },
                    context
                )
        
        elif intent_result.intent in (
            Intent.QUERY_VITALS,
            Intent.QUERY_MEDICATIONS,
            Intent.QUERY_PATIENT_INFO,
            Intent.QUERY_TRENDS
        ):
            return await self._handle_query(
                intent_result.intent,
                extraction_result,
                patient_id,
                context
            )

        elif intent_result.intent == Intent.SUMMARIZE:
            return await self._handle_fast_summary(patient_id, normalized_text)
        
        elif intent_result.intent in (
            Intent.COMMAND_SAVE,
            Intent.COMMAND_CANCEL,
            Intent.COMMAND_HELP,
            Intent.COMMAND_LIST,
            Intent.COMMAND_STATUS
        ):
            command = intent_result.intent.value.replace("command_", "")
            return await self._handle_command(
                {"command": command},
                patient_id,
                context
            )
        
        if (
            intent_result.intent == Intent.UNKNOWN
            or intent_result.confidence < settings.INTENT_CONFIDENCE_THRESHOLD
        ):
            return await self._run_llm_with_deadline(text, patient_id, context)

        return await self._run_llm_with_deadline(text, patient_id, context)

    async def _handle_fast_summary(
        self,
        patient_id: Optional[str],
        request_text: str = ""
    ) -> Dict[str, Any]:
        if not patient_id:
            return self._create_response(
                success=False,
                message="Please select a patient first",
                response_type="error",
                requires_patient=True
            )
        try:
            from database.repo.patient_repo import PatientRepository
            from database.repo.vitals_repo import VitalsRepository
            from database.repo.meds_repo import MedicationRepository

            patient_repo = PatientRepository()
            vitals_repo = VitalsRepository()
            meds_repo = MedicationRepository()

            patient = patient_repo.get_patient(patient_id)
            latest_vitals = vitals_repo.get_latest_vitals(patient_id)
            delta = self.change_detector.get_delta_metrics(patient_id)
            due_meds = meds_repo.get_due_medications(patient_id)

            if not patient:
                return self._create_response(
                    success=False,
                    message="Patient not found",
                    response_type="error"
                )

            patient_name = patient.get("name", "Unknown")
            room = patient.get("room", "N/A")
            diagnosis = patient.get("primary_diagnosis", "N/A")

            bp_text = "N/A"
            hr_text = "N/A"
            temp_text = "N/A"
            spo2_text = "N/A"
            if latest_vitals:
                systolic = latest_vitals.get("systolic", "N/A")
                diastolic = latest_vitals.get("diastolic", "N/A")
                bp_text = f"{self._format_numeric(systolic)}/{self._format_numeric(diastolic)} mmHg"
                hr_text = f"{self._format_numeric(latest_vitals.get('heart_rate', 'N/A'))} bpm"
                temp_text = f"{self._format_numeric(latest_vitals.get('temperature', 'N/A'))} C"
                spo2_text = f"{self._format_numeric(latest_vitals.get('spo2', 'N/A'))}%"

            alerts = (delta or {}).get("alerts") or []
            alert_text = "no active clinical alerts"
            if alerts:
                lead_alert = alerts[0]
                alert_text = f"{len(alerts)} alert(s), including {lead_alert}"

            med_names = [med.get("name", "Medication") for med in due_meds[:3]]
            meds_text = "no medications currently due"
            if due_meds:
                meds_text = f"{len(due_meds)} medication(s) due"
                if med_names:
                    meds_text += f": {', '.join(med_names)}"

            one_line = self._is_one_line_request(request_text)
            if one_line:
                message = (
                    f"{patient_name} (Room {room}) has {diagnosis}; latest vitals: BP {bp_text}, "
                    f"HR {hr_text}, Temp {temp_text}, SpO2 {spo2_text}; {alert_text}; {meds_text}."
                )
            else:
                message = (
                    f"{patient_name} in Room {room} has {diagnosis}. "
                    f"Latest vitals are BP {bp_text}, HR {hr_text}, temperature {temp_text}, and SpO2 {spo2_text}. "
                    f"There are {alert_text}. "
                    f"Current medication status: {meds_text}."
                )

            return self._create_response(
                success=True,
                message=message,
                response_type="summary_fast",
                data={
                    "patient_id": patient_id,
                    "alerts_count": len(alerts),
                    "due_medications_count": len(due_meds),
                    "one_line": one_line,
                }
            )
        except Exception:
            return self._create_response(
                success=True,
                message="Quick summary is temporarily unavailable. Try: vitals, due meds, or trends.",
                response_type="summary_fast_fallback"
            )

    def _format_numeric(self, value: Any) -> str:
        try:
            numeric = float(value)
            if numeric.is_integer():
                return str(int(numeric))
            return f"{numeric:.1f}".rstrip("0").rstrip(".")
        except Exception:
            return str(value)

    async def _run_llm_with_deadline(
        self,
        text: str,
        patient_id: Optional[str],
        context: Dict
    ) -> Dict[str, Any]:
        # User requested no hard timeout for assistant responses.
        return await self._handle_llm_path(text, patient_id, context)
    
    async def _handle_query(
        self,
        intent: Intent,
        extraction_result: Any,
        patient_id: Optional[str],
        context: Dict
    ) -> Dict[str, Any]:
        if not patient_id:
            return self._create_response(
                success=False,
                message="Please select a patient first",
                response_type="error",
                requires_patient=True
            )
        
        if intent == Intent.QUERY_VITALS:
            from database.repo.vitals_repo import VitalsRepository
            repo = VitalsRepository()
            vitals = repo.get_latest_vitals(patient_id)
            delta = self.change_detector.get_delta_metrics(patient_id)
            
            return self._create_response(
                success=True,
                message="Current vitals retrieved",
                response_type="vitals_query",
                data={
                    "vitals": vitals,
                    "delta_metrics": delta
                }
            )
        
        elif intent == Intent.QUERY_MEDICATIONS:
            from database.repo.meds_repo import MedicationRepository
            repo = MedicationRepository()
            
            active_meds = repo.get_active_medications(patient_id)
            due_meds = repo.get_due_medications(patient_id)
            
            return self._create_response(
                success=True,
                message=f"Found {len(active_meds)} active medications, {len(due_meds)} due",
                response_type="medications_query",
                data={
                    "active_medications": active_meds,
                    "due_medications": due_meds
                }
            )
        
        elif intent == Intent.QUERY_PATIENT_INFO:
            from database.repo.patient_repo import PatientRepository
            repo = PatientRepository()
            patient = repo.get_patient(patient_id)
            
            return self._create_response(
                success=True,
                message="Patient information retrieved",
                response_type="patient_info_query",
                data={"patient": patient}
            )
        
        elif intent == Intent.QUERY_TRENDS:
            delta = self.change_detector.get_delta_metrics(patient_id)
            
            from database.repo.vitals_repo import VitalsRepository
            repo = VitalsRepository()
            history = repo.get_vitals_history(patient_id, days=7)
            
            return self._create_response(
                success=True,
                message="Trends retrieved",
                response_type="trends_query",
                data={
                    "delta_metrics": delta,
                    "history": history[:50]
                }
            )
        
        return self._create_response(
            success=False,
            message="Query type not supported",
            response_type="error"
        )
    
    async def _handle_llm_path(
        self,
        text: str,
        patient_id: Optional[str],
        context: Dict
    ) -> Dict[str, Any]:
        try:
            llm, retriever = self._get_llm_components()
            normalized_text = self.preprocessor.preprocess(text).normalized or text
            
            patient_context = ""
            if patient_id:
                from database.repo.patient_repo import PatientRepository
                from database.repo.vitals_repo import VitalsRepository
                from database.repo.chat_repo import ChatRepository
                
                patient_repo = PatientRepository()
                vitals_repo = VitalsRepository()
                chat_repo = ChatRepository()
                
                patient = patient_repo.get_patient(patient_id)
                vitals = vitals_repo.get_latest_vitals(patient_id)
                
                # Fetch recent chat history
                chat_history_text = ""
                sessions = chat_repo.list_sessions(patient_id)
                if sessions:
                    session_data = chat_repo.get_session(patient_id, sessions[0]["id"], include_messages=True)
                    if session_data and session_data.get("messages"):
                        recent_messages = session_data["messages"][-10:]
                        chat_history_text = "\nRecent Conversation History:\n"
                        for msg in recent_messages:
                            role = "User" if msg.get("role") == "user" else "Assistant"
                            chat_history_text += f"{role}: {msg.get('content', '')}\n"
                
                if patient:
                    patient_context = f"""
Current Patient: {patient.get('name', 'Unknown')}
Age: {patient.get('age', 'Unknown')} | Gender: {patient.get('gender', 'Unknown')}
Room: {patient.get('room', 'N/A')}
Diagnosis: {patient.get('primary_diagnosis', 'N/A')}
Allergies: {patient.get('allergies', 'None known')}
"""
                if vitals:
                    patient_context += f"""
Latest Vitals:
- BP: {vitals.get('systolic', 'N/A')}/{vitals.get('diastolic', 'N/A')} mmHg
- HR: {vitals.get('heart_rate', 'N/A')} bpm
- Temp: {vitals.get('temperature', 'N/A')} C
- SpO2: {vitals.get('spo2', 'N/A')}%
"""
                if chat_history_text:
                    patient_context += f"\n{chat_history_text}"
            
            relevant_docs = retriever.retrieve(normalized_text)
            
            response = await llm.generate(
                query=normalized_text,
                context=patient_context,
                retrieved_docs=relevant_docs
            )
            
            return self._create_response(
                success=True,
                message=response,
                response_type="llm_response",
                data={
                    "query": text,
                    "sources_used": len(relevant_docs)
                }
            )
        
        except Exception as e:
            return self._create_response(
                success=True,
                message="I can help with recording vitals, medications, and answering questions about patients. Try commands like 'BP 120/80', 'gave metformin', or 'select room 101'.",
                response_type="fallback_response",
                data={"error": str(e)}
            )

    def _is_simple_greeting(self, text: str) -> bool:
        normalized = re.sub(r"[^\w\s]", " ", text.lower())
        normalized = re.sub(r"\s+", " ", normalized).strip()

        greeting_phrases = {
            "hi",
            "hello",
            "hey",
            "hey there",
            "hi there",
            "good morning",
            "good afternoon",
            "good evening",
        }
        return normalized in greeting_phrases

    def _build_greeting_response(self, patient_id: Optional[str]) -> str:
        if patient_id:
            return (
                "Hi. I am ready to assist. "
                "Ask for vitals, medication schedule, or a specific clinical summary when needed."
            )
        return (
            "Hi. I can help record vitals, review medications, and answer clinical questions. "
            "Please select a patient to get started."
        )

    async def _handle_patient_name_query(self, patient_id: Optional[str]) -> Dict[str, Any]:
        if not patient_id:
            return self._create_response(
                success=False,
                message="Please select a patient first",
                response_type="error",
                requires_patient=True
            )

        try:
            from database.repo.patient_repo import PatientRepository
            repo = PatientRepository()
            patient = repo.get_patient(patient_id)

            if not patient:
                return self._create_response(
                    success=False,
                    message="Patient not found",
                    response_type="error"
                )

            patient_name = patient.get("name", "Unknown")
            room = patient.get("room")
            if room:
                message = f"Current patient is {patient_name} (Room {room})."
            else:
                message = f"Current patient is {patient_name}."

            return self._create_response(
                success=True,
                message=message,
                response_type="patient_name",
                data={
                    "patient_id": patient_id,
                    "patient_name": patient_name,
                    "room": room
                }
            )
        except Exception:
            return self._create_response(
                success=True,
                message="I can help with the current patient identity, but that data is temporarily unavailable.",
                response_type="patient_name_fallback"
            )

    async def _handle_vitals_history_query(
        self,
        patient_id: Optional[str],
        request_text: str = ""
    ) -> Dict[str, Any]:
        if not patient_id:
            return self._create_response(
                success=False,
                message="Please select a patient first",
                response_type="error",
                requires_patient=True
            )

        try:
            from database.repo.patient_repo import PatientRepository
            from database.repo.vitals_repo import VitalsRepository

            patient_repo = PatientRepository()
            vitals_repo = VitalsRepository()

            patient = patient_repo.get_patient(patient_id)
            patient_name = patient.get("name", "Current patient") if patient else "Current patient"

            days = self._extract_history_days(request_text)
            history = vitals_repo.get_vitals_history(patient_id, days=days)

            if not history:
                return self._create_response(
                    success=True,
                    message=f"No vitals history found for {patient_name} in the last {days} day(s).",
                    response_type="vitals_history"
                )

            snapshots = self._build_vitals_snapshots(history)
            if not snapshots:
                return self._create_response(
                    success=True,
                    message=f"No complete vitals history entries found for {patient_name}.",
                    response_type="vitals_history"
                )

            lines = [f"Vitals history for {patient_name} (last {days} day(s)), one by one:"]
            for idx, snap in enumerate(snapshots, start=1):
                parts = []
                systolic = snap.get("systolic")
                diastolic = snap.get("diastolic")
                if systolic is not None or diastolic is not None:
                    systolic_text = self._format_numeric(systolic if systolic is not None else "N/A")
                    diastolic_text = self._format_numeric(diastolic if diastolic is not None else "N/A")
                    parts.append(f"BP {systolic_text}/{diastolic_text} mmHg")
                if snap.get("heart_rate") is not None:
                    parts.append(f"HR {self._format_numeric(snap['heart_rate'])} bpm")
                if snap.get("temperature") is not None:
                    parts.append(f"Temp {self._format_numeric(snap['temperature'])} C")
                if snap.get("spo2") is not None:
                    parts.append(f"SpO2 {self._format_numeric(snap['spo2'])}%")
                if snap.get("respiratory_rate") is not None:
                    parts.append(f"RR {self._format_numeric(snap['respiratory_rate'])}/min")
                if snap.get("glucose") is not None:
                    parts.append(f"Glucose {self._format_numeric(snap['glucose'])}")
                if snap.get("weight") is not None:
                    parts.append(f"Weight {self._format_numeric(snap['weight'])}")

                if not parts:
                    parts.append("No supported vitals in this entry")

                lines.append(f"{idx}. {snap['display_time']}: " + ", ".join(parts))

            lines.append(f"Showing {len(snapshots)} timeline point(s) from {len(history)} recorded vital entries.")

            return self._create_response(
                success=True,
                message="\n".join(lines),
                response_type="vitals_history",
                data={
                    "patient_id": patient_id,
                    "days": days,
                    "total_entries": len(history),
                    "snapshots": snapshots,
                }
            )
        except Exception:
            return self._create_response(
                success=True,
                message="Vitals history is temporarily unavailable. Try 'vitals' for latest readings.",
                response_type="vitals_history_fallback"
            )

    def _is_summary_request(self, text: str) -> bool:
        normalized = text.lower().strip()
        summary_terms = ("summary", "summarize", "overview", "recap")
        if any(term in normalized for term in summary_terms):
            return True
        return "patient status" in normalized or "clinical status" in normalized

    def _is_patient_name_request(self, text: str) -> bool:
        normalized = re.sub(r"[^\w\s]", " ", text.lower())
        normalized = re.sub(r"\s+", " ", normalized).strip()

        explicit_patterns = (
            "tell me patient name",
            "tell me the patient name",
            "what is patient name",
            "what is the patient name",
            "name of patient",
            "patient name",
            "current patient name",
            "who is this patient",
            "who is the patient",
            "who is current patient",
        )
        if any(pattern in normalized for pattern in explicit_patterns):
            return True

        return "patient" in normalized and "name" in normalized

    def _is_vitals_history_request(self, text: str) -> bool:
        normalized = re.sub(r"[^\w\s]", " ", text.lower())
        normalized = re.sub(r"\s+", " ", normalized).strip()

        vitals_terms = (
            "vital",
            "vitals",
            "blood pressure",
            "heart rate",
            "spo2",
            "temperature",
            "respiratory",
        )
        history_terms = (
            "history",
            "historical",
            "trend",
            "trends",
            "over time",
            "previous",
            "past",
            "one by one",
            "line by line",
        )

        has_vitals_term = any(term in normalized for term in vitals_terms)
        has_history_term = any(term in normalized for term in history_terms)
        return has_vitals_term and has_history_term

    def _extract_history_days(self, text: str) -> int:
        normalized = text.lower().strip()

        if "today" in normalized:
            return 1
        if "yesterday" in normalized:
            return 2
        if "week" in normalized:
            return 7
        if "month" in normalized:
            return 30

        day_match = re.search(r"\b(\d{1,2})\s*(?:day|days|d)\b", normalized)
        if day_match:
            days = int(day_match.group(1))
            return min(max(days, 1), 30)

        hour_match = re.search(r"\b(\d{1,3})\s*(?:hour|hours|hr|hrs)\b", normalized)
        if hour_match:
            hours = int(hour_match.group(1))
            days = max(1, math.ceil(hours / 24))
            return min(days, 30)

        return 7

    def _build_vitals_snapshots(self, history: list, max_snapshots: Optional[int] = None) -> list:
        grouped = {}
        ordered_timestamps = []

        for item in history:
            ts = item.get("timestamp")
            if not ts:
                continue
            if ts not in grouped:
                grouped[ts] = {"timestamp": ts}
                ordered_timestamps.append(ts)

            vital_type = item.get("vital_type")
            if not vital_type:
                continue
            grouped[ts][vital_type] = item.get("value")

        snapshots = []
        target_timestamps = ordered_timestamps if max_snapshots is None else ordered_timestamps[:max_snapshots]
        for ts in target_timestamps:
            row = grouped.get(ts, {})
            row["display_time"] = self._format_history_time(ts)
            snapshots.append(row)

        return snapshots

    def _format_history_time(self, timestamp: str) -> str:
        if not timestamp:
            return "Unknown time"
        try:
            parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            return parsed.strftime("%b %d %H:%M:%S")
        except Exception:
            return timestamp

    def _is_one_line_request(self, text: str) -> bool:
        normalized = text.lower().strip()
        one_line_terms = (
            "one line",
            "single line",
            "oneline",
            "one sentence",
            "single sentence",
            "brief",
            "short",
        )
        return any(term in normalized for term in one_line_terms)

    def _get_llm_components(self):
        if self._llm is None or self._retriever is None:
            from intelligence.llm.local_inference import LocalLLM
            from intelligence.rag.retriever import RAGRetriever

            self._llm = LocalLLM()
            self._retriever = RAGRetriever()

        return self._llm, self._retriever
    
    def _create_response(
        self,
        success: bool,
        message: str,
        response_type: str,
        data: Optional[Dict] = None,
        broadcast: bool = False,
        broadcast_data: Optional[Dict] = None,
        patient_id: Optional[str] = None,
        requires_patient: bool = False
    ) -> Dict[str, Any]:
        return {
            "success": success,
            "message": message,
            "type": response_type,
            "data": data or {},
            "timestamp": datetime.utcnow().isoformat(),
            "broadcast": broadcast,
            "broadcast_data": broadcast_data,
            "patient_id": patient_id,
            "requires_patient": requires_patient
        }
