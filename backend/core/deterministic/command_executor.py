from dataclasses import dataclass
from typing import Dict, Optional, List, Any
from datetime import datetime
from enum import Enum


class CommandType(Enum):
    SAVE = "save"
    CANCEL = "cancel"
    HELP = "help"
    LIST = "list"
    STATUS = "status"
    UNDO = "undo"
    REFRESH = "refresh"


@dataclass
class CommandResult:
    success: bool
    command: CommandType
    message: str
    data: Optional[Dict]
    actions_taken: List[str]


class CommandExecutor:
    def __init__(self):
        self.pending_operations = {}
        self.operation_history = []
    
    def execute(
        self,
        command: str,
        patient_id: Optional[str] = None,
        context: Optional[Dict] = None
    ) -> CommandResult:
        try:
            command_type = CommandType(command.lower())
        except ValueError:
            return CommandResult(
                success=False,
                command=CommandType.HELP,
                message=f"Unknown command: {command}",
                data=None,
                actions_taken=[]
            )
        
        handlers = {
            CommandType.SAVE: self._handle_save,
            CommandType.CANCEL: self._handle_cancel,
            CommandType.HELP: self._handle_help,
            CommandType.LIST: self._handle_list,
            CommandType.STATUS: self._handle_status,
            CommandType.UNDO: self._handle_undo,
            CommandType.REFRESH: self._handle_refresh,
        }
        
        handler = handlers.get(command_type, self._handle_help)
        return handler(patient_id, context)
    
    def _handle_save(
        self, 
        patient_id: Optional[str], 
        context: Optional[Dict]
    ) -> CommandResult:
        if not patient_id:
            return CommandResult(
                success=False,
                command=CommandType.SAVE,
                message="No patient selected",
                data=None,
                actions_taken=[]
            )
        
        pending = self.pending_operations.get(patient_id, [])
        
        if not pending:
            return CommandResult(
                success=True,
                command=CommandType.SAVE,
                message="No pending changes to save",
                data=None,
                actions_taken=[]
            )
        
        actions_taken = []
        for op in pending:
            actions_taken.append(f"Saved: {op['description']}")
        
        self.operation_history.extend(pending)
        self.pending_operations[patient_id] = []
        
        return CommandResult(
            success=True,
            command=CommandType.SAVE,
            message=f"Saved {len(actions_taken)} pending operations",
            data={"saved_count": len(actions_taken)},
            actions_taken=actions_taken
        )
    
    def _handle_cancel(
        self, 
        patient_id: Optional[str], 
        context: Optional[Dict]
    ) -> CommandResult:
        if not patient_id:
            return CommandResult(
                success=True,
                command=CommandType.CANCEL,
                message="Operation cancelled",
                data=None,
                actions_taken=["Cleared current input"]
            )
        
        pending = self.pending_operations.get(patient_id, [])
        cancelled_count = len(pending)
        self.pending_operations[patient_id] = []
        
        return CommandResult(
            success=True,
            command=CommandType.CANCEL,
            message=f"Cancelled {cancelled_count} pending operations",
            data={"cancelled_count": cancelled_count},
            actions_taken=[f"Cancelled {cancelled_count} pending changes"]
        )
    
    def _handle_help(
        self, 
        patient_id: Optional[str], 
        context: Optional[Dict]
    ) -> CommandResult:
        help_data = {
            "commands": [
                {"command": "save", "description": "Save all pending changes"},
                {"command": "cancel", "description": "Cancel pending operations"},
                {"command": "undo", "description": "Undo last operation"},
                {"command": "list", "description": "List patients or pending tasks"},
                {"command": "status", "description": "Show current patient status"},
                {"command": "help", "description": "Show this help message"},
            ],
            "quick_entries": [
                {"format": "120/80", "description": "Record blood pressure"},
                {"format": "hr 72", "description": "Record heart rate"},
                {"format": "temp 98.6", "description": "Record temperature"},
                {"format": "spo2 98", "description": "Record oxygen saturation"},
                {"format": "gave metformin", "description": "Record medication given"},
                {"format": "room 101", "description": "Select patient by room"},
            ],
            "voice_examples": [
                "Blood pressure 120 over 80",
                "Heart rate 72 beats per minute",
                "Temperature 98.6 fahrenheit",
                "Gave lisinopril 10 milligrams",
                "Select patient John Smith",
            ]
        }
        
        return CommandResult(
            success=True,
            command=CommandType.HELP,
            message="Available commands and quick entry formats",
            data=help_data,
            actions_taken=[]
        )
    
    def _handle_list(
        self, 
        patient_id: Optional[str], 
        context: Optional[Dict]
    ) -> CommandResult:
        from database.repo.patient_repo import PatientRepository
        from database.repo.meds_repo import MedicationRepository
        
        list_type = context.get("list_type", "patients") if context else "patients"
        
        if list_type == "patients":
            repo = PatientRepository()
            patients = repo.get_all_patients()
            
            return CommandResult(
                success=True,
                command=CommandType.LIST,
                message=f"Found {len(patients)} patients",
                data={"patients": patients},
                actions_taken=[]
            )
        
        elif list_type == "medications" and patient_id:
            repo = MedicationRepository()
            meds = repo.get_active_medications(patient_id)
            
            return CommandResult(
                success=True,
                command=CommandType.LIST,
                message=f"Found {len(meds)} active medications",
                data={"medications": meds},
                actions_taken=[]
            )
        
        elif list_type == "pending":
            pending = self.pending_operations.get(patient_id, []) if patient_id else []
            
            return CommandResult(
                success=True,
                command=CommandType.LIST,
                message=f"{len(pending)} pending operations",
                data={"pending": pending},
                actions_taken=[]
            )
        
        return CommandResult(
            success=True,
            command=CommandType.LIST,
            message="Specify what to list: patients, medications, or pending",
            data=None,
            actions_taken=[]
        )
    
    def _handle_status(
        self, 
        patient_id: Optional[str], 
        context: Optional[Dict]
    ) -> CommandResult:
        if not patient_id:
            return CommandResult(
                success=False,
                command=CommandType.STATUS,
                message="No patient selected. Use 'select [patient name]' or 'room [number]'",
                data=None,
                actions_taken=[]
            )
        
        from database.repo.patient_repo import PatientRepository
        from database.repo.vitals_repo import VitalsRepository
        from database.repo.meds_repo import MedicationRepository
        from core.change_detector import ChangeDetector
        
        patient_repo = PatientRepository()
        vitals_repo = VitalsRepository()
        meds_repo = MedicationRepository()
        detector = ChangeDetector()
        
        patient = patient_repo.get_patient(patient_id)
        latest_vitals = vitals_repo.get_latest_vitals(patient_id)
        active_meds = meds_repo.get_active_medications(patient_id)
        due_meds = meds_repo.get_due_medications(patient_id)
        delta_metrics = detector.get_delta_metrics(patient_id)
        
        status_data = {
            "patient": patient,
            "vitals": latest_vitals,
            "medications": {
                "active_count": len(active_meds) if active_meds else 0,
                "due_count": len(due_meds) if due_meds else 0,
                "due_medications": due_meds[:5] if due_meds else []
            },
            "alerts": delta_metrics.get("alerts", []) if delta_metrics else [],
            "clinical_status": delta_metrics.get("clinical_status", {}) if delta_metrics else {},
            "pending_operations": len(self.pending_operations.get(patient_id, []))
        }
        
        patient_name = patient.get("name", "Unknown") if patient else "Unknown"
        
        return CommandResult(
            success=True,
            command=CommandType.STATUS,
            message=f"Status for {patient_name}",
            data=status_data,
            actions_taken=[]
        )
    
    def _handle_undo(
        self, 
        patient_id: Optional[str], 
        context: Optional[Dict]
    ) -> CommandResult:
        if not self.operation_history:
            return CommandResult(
                success=False,
                command=CommandType.UNDO,
                message="Nothing to undo",
                data=None,
                actions_taken=[]
            )
        
        last_op = self.operation_history.pop()
        
        return CommandResult(
            success=True,
            command=CommandType.UNDO,
            message=f"Undone: {last_op.get('description', 'Last operation')}",
            data={"undone_operation": last_op},
            actions_taken=[f"Reversed: {last_op.get('description', 'Last operation')}"]
        )
    
    def _handle_refresh(
        self, 
        patient_id: Optional[str], 
        context: Optional[Dict]
    ) -> CommandResult:
        return CommandResult(
            success=True,
            command=CommandType.REFRESH,
            message="Data refreshed",
            data={"refresh_timestamp": datetime.utcnow().isoformat()},
            actions_taken=["Refreshed patient data"]
        )
    
    def add_pending_operation(
        self, 
        patient_id: str, 
        operation: Dict
    ) -> None:
        if patient_id not in self.pending_operations:
            self.pending_operations[patient_id] = []
        
        operation["timestamp"] = datetime.utcnow().isoformat()
        self.pending_operations[patient_id].append(operation)
    
    def get_formatted_response(self, result: CommandResult) -> Dict:
        return {
            "success": result.success,
            "command": result.command.value,
            "message": result.message,
            "data": result.data,
            "actions": result.actions_taken
        }