import sys
import warnings
warnings.filterwarnings("ignore")

print("Initializing testing environment...")
print("Downloading model (this may take a minute)...")
try:
    from transformers import pipeline
except ImportError:
    print("Please install transformers: pip install transformers torch")
    sys.exit(1)

# Using Qwen 2.5 0.5B as a proxy for the Gemma mobile model (which requires an auth token)
model_id = "Qwen/Qwen2.5-0.5B-Instruct" 
generator = pipeline("text-generation", model=model_id, device=-1) # CPU

system_prompt = """You are NurseAssist AI, a warm, professional, and highly intelligent clinical nursing assistant running on-device.
You help nurses chart vitals, medications, and notes. You can also answer clinical questions, summarize patients, and have friendly conversations.

RULES:
1. Output ONLY valid JSON. No markdown fences, no extra text.
2. ALWAYS include a "reply" field with a friendly, concise, natural response for the nurse.
3. For clinical data (vitals, meds, notes), ALSO include the structured fields.
4. Be warm and professional. Use the patient context to give informed answers.
5. If the nurse just wants to chat or asks a question, use action "conversation".
6. If the nurse describes a new diagnosis, patient symptoms, complaints, or complex medical history, use action record_note to document them using category "diagnosis", "medical_history", or "nursing_observation".

JSON Schema:
Clinical writes: {"v":1,"action":"record_vitals|record_medication|record_note","reply":"Your friendly response","timestamp":"...","vitals":[{...}]}
Queries: {"v":1,"action":"query_vitals|query_trends|query_medications|summarize","reply":"Your informed answer"}
Conversation: {"v":1,"action":"conversation|greeting|help|cancel","reply":"Your natural response"}
"""

print("\n--- MODEL READY ---")
print("Type your prompt and press Enter. Type 'exit' to quit.")

while True:
    try:
        user_input = input("Nurse: ")
        if user_input.strip().lower() == "exit":
            break
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_input}
        ]
        
        output = generator(messages, max_new_tokens=200, do_sample=False)
        print("\nAI:", output[0]['generated_text'][-1]['content'])
        print("-" * 20)
    except Exception as e:
        print("Error:", e)
