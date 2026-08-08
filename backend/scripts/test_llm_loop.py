import asyncio
import sys
import os
import time

# Add the backend directory to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from database.models import init_database
from services.assistant_orchestrator import AssistantOrchestrator

TEST_CASES = [
    ("Patient BP is 150/90", "vitals_recorded"),
    ("BP 120/80, HR 85", "vitals_recorded"),
    ("Patient is very hot, temperature 39.5", "vitals_recorded"),
    ("Gave patient 500mg Tylenol", "medication_recorded"),
    ("Administered Metformin 1000mg", "medication_recorded"),
    ("What medications are due?", "medications_query"),
    ("Are there any meds due right now?", "medications_query"),
    ("What are the latest vitals?", "vitals_query"),
    ("Did the patient's blood pressure go up?", "trends_query"),
    ("Give me a quick summary of the patient", "summary_fast"),
    ("Select room 101", "patient_selection_needed"),
    ("Switch to John Doe", "patient_selection_needed"),
    ("Cancel that", "command_cancel"),
    ("Help me", "command_help"),
    ("Save the data", "command_save"),
    ("Is the patient allergic to anything?", "llm_response"),
    ("What should I do if the patient complains of severe chest pain?", "llm_response"),
    ("Generate a shift handoff report", "llm_response"),
    ("What is the primary diagnosis?", "llm_response"),
    ("Tell me a joke", "llm_response"),
]

async def run_tests():
    print("Initializing Database and Orchestrator...")
    init_database()
    orch = AssistantOrchestrator()
    
    # Preload the LLM to avoid timeouts on the first test
    print("Preloading LLM...")
    llm, _ = orch._get_llm_components()
    
    # Create test patient
    from database.models import Patient, get_engine
    from sqlmodel import Session
    with Session(get_engine()) as session:
        if not session.get(Patient, "p1"):
            session.add(Patient(id="p1", first_name="Test", last_name="Patient", is_active=True))
            session.commit()
    
    passed = 0
    failed = 0
    
    print("\nStarting Loop Engineering Tests...\n")
    
    for i, (query, expected_type) in enumerate(TEST_CASES):
        print(f"Test {i+1}/{len(TEST_CASES)}")
        print(f"Query: '{query}'")
        
        start_time = time.time()
        try:
            # We use patient_id="p1" to ensure patient-specific intents work
            response = await orch.process_input(query, patient_id="p1", context={})
            elapsed = time.time() - start_time
            
            actual_type = response.get("type", "unknown")
            msg = response.get("message", "")
            
            # For llm_response, check if it's actually hallucinating or providing an empty string
            if expected_type == actual_type:
                if actual_type == "llm_response" and len(msg.strip()) < 10:
                    print(f"[FAILED] (Response too short): {msg}")
                    failed += 1
                else:
                    print(f"[PASSED] (Type: {actual_type}) in {elapsed:.2f}s")
                    if actual_type == "llm_response":
                        print(f"   LLM Output: {msg}")
                    passed += 1
            else:
                print(f"[FAILED] Expected: {expected_type}, Got: {actual_type}")
                print(f"   Message: {msg}")
                failed += 1
                
        except Exception as e:
            print(f"[ERROR] {e}")
            failed += 1
            
        print("-" * 50)
        
    print(f"\nTest Summary: {passed} Passed, {failed} Failed")
    if failed > 0:
        sys.exit(1)
    sys.exit(0)

if __name__ == "__main__":
    asyncio.run(run_tests())
