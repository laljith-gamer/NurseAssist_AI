import asyncio
import sys
from datetime import datetime

from core.router import InputRouter
from services.assistant_orchestrator import AssistantOrchestrator
from database.models import init_database
from database.repo.patient_repo import PatientRepository


class NurseCLI:
    def __init__(self):
        self.orchestrator = AssistantOrchestrator()
        self.patient_repo = PatientRepository()
        self.current_patient_id = None
        self.running = True
    
    def print_header(self):
        print("\n" + "=" * 60)
        print("  Digital Clinical Nurse Assistant - Command Line Interface")
        print("=" * 60)
        print("Natural language chat is enabled (commands still supported).")
        print("Type 'help' for examples, 'quit' to exit\n")
    
    def print_patient_context(self):
        if self.current_patient_id:
            patient = self.patient_repo.get_patient(self.current_patient_id)
            if patient:
                print(f"[Current Patient: {patient['name']} - Room {patient.get('room', 'N/A')}]")
            else:
                print("[No patient selected]")
        else:
            print("[No patient selected]")
    
    def show_help(self):
        help_text = """
AVAILABLE COMMANDS:
==================

PATIENT SELECTION:
  select <name/room>    - Select a patient by name or room number
  room <number>         - Select patient by room number
  patients              - List all active patients
  
VITAL SIGNS:
  <systolic>/<diastolic> - Record blood pressure (e.g., 120/80)
  hr <value>            - Record heart rate
  temp <value>          - Record temperature
  spo2 <value>          - Record oxygen saturation
  rr <value>            - Record respiratory rate
  vitals                - Show current vitals
  
MEDICATIONS:
  gave <medication>     - Record medication given
  held <medication>     - Record medication held
  meds                  - List active medications
  due                   - Show medications due
  
QUERIES:
  status                - Show patient status summary
  trends                - Show vital sign trends
  delta                 - Show changes from baseline
  "How is room 101?"    - Natural-language patient question
  "What changed since yesterday?" - Natural-language trend question
  
SYSTEM:
  help                  - Show this help message
  clear                 - Clear screen
  quit/exit             - Exit the application
"""
        print(help_text)
    
    def list_patients(self):
        patients = self.patient_repo.get_all_patients()
        if not patients:
            print("No active patients found.")
            return
        
        print("\nACTIVE PATIENTS:")
        print("-" * 50)
        for p in patients:
            status = "*" if p["id"] == self.current_patient_id else " "
            print(f"{status} Room {p.get('room', 'N/A'):5} | {p['name']:20} | {p.get('primary_diagnosis', 'N/A')[:25]}")
        print("-" * 50)
        print(f"Total: {len(patients)} patients (* = currently selected)\n")
    
    async def process_input(self, text: str):
        if not text.strip():
            return
        
        cmd = text.strip().lower()
        
        if cmd in ['quit', 'exit', 'q']:
            self.running = False
            print("Goodbye!")
            return
        
        if cmd == 'help':
            self.show_help()
            return
        
        if cmd == 'clear':
            print("\033[H\033[J")
            self.print_header()
            return
        
        if cmd == 'patients':
            self.list_patients()
            return
        
        response = await self.orchestrator.process_input(
            text=text,
            patient_id=self.current_patient_id,
            context={}
        )
        
        self.display_response(response)
        
        if response.get("type") == "patient_selected" and response.get("patient_id"):
            self.current_patient_id = response["patient_id"]
    
    def display_response(self, response: dict):
        success = response.get("success", False)
        message = response.get("message", "")
        response_type = response.get("type", "")
        data = response.get("data", {})
        
        status_icon = "[OK]" if success else "[!!]"
        print(f"\n{status_icon} {message}")
        
        if response_type == "vitals_recorded":
            recorded = data.get("recorded_vitals", [])
            if recorded:
                print("  Recorded:")
                for v in recorded:
                    print(f"    - {v['type']}: {v['value']} {v['unit']}")
            
            warnings = data.get("warnings", [])
            for w in warnings:
                print(f"  [WARN] {w}")
            
            alerts = data.get("clinical_alerts", [])
            for a in alerts:
                print(f"  [ALERT] {a}")
        
        elif response_type == "patient_selected":
            summary = data.get("summary", {})
            if summary:
                vitals = summary.get("latest_vitals", {})
                if vitals:
                    print("  Latest Vitals:")
                    if vitals.get("systolic") and vitals.get("diastolic"):
                        print(f"    BP: {vitals['systolic']}/{vitals['diastolic']} mmHg")
                    if vitals.get("heart_rate"):
                        print(f"    HR: {vitals['heart_rate']} bpm")
                    if vitals.get("temperature"):
                        print(f"    Temp: {vitals['temperature']} C")
                    if vitals.get("spo2"):
                        print(f"    SpO2: {vitals['spo2']}%")
                
                alerts = summary.get("alerts", [])
                if alerts:
                    print("  Alerts:")
                    for a in alerts:
                        print(f"    [!] {a}")
        
        elif response_type == "medications_query":
            active = data.get("active_medications", [])
            due = data.get("due_medications", [])
            
            if active:
                print("  Active Medications:")
                for m in active[:10]:
                    print(f"    - {m['name']} {m.get('dose', '')} {m.get('frequency', '')}")
            
            if due:
                print("  Due Now:")
                for m in due:
                    print(f"    - {m['name']} (due: {m.get('scheduled_time', 'N/A')})")
        
        elif response_type == "vitals_query":
            vitals = data.get("vitals", {})
            if vitals:
                print("  Current Vitals:")
                for key, value in vitals.items():
                    if value is not None and key != "timestamp":
                        print(f"    {key}: {value}")
            
            delta = data.get("delta_metrics", {})
            if delta and delta.get("alerts"):
                print("  Alerts:")
                for a in delta["alerts"]:
                    print(f"    [!] {a}")
        
        elif response_type == "command_help":
            self.show_help()
        
        print()
    
    async def run(self):
        init_database()
        
        self.print_header()
        
        while self.running:
            try:
                self.print_patient_context()
                user_input = input("> ").strip()
                
                if user_input:
                    await self.process_input(user_input)
                    
            except KeyboardInterrupt:
                print("\n\nInterrupted. Type 'quit' to exit.")
            except EOFError:
                self.running = False
                print("\nGoodbye!")
            except Exception as e:
                print(f"[ERROR] {str(e)}")


def main():
    cli = NurseCLI()
    asyncio.run(cli.run())


if __name__ == "__main__":
    main()
