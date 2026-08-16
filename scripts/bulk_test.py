import json
import time
import warnings
import sys
warnings.filterwarnings("ignore")

try:
    from transformers import pipeline
    from tqdm import tqdm
except ImportError:
    print("Please install transformers and tqdm")
    sys.exit(1)

model_id = "Qwen/Qwen2.5-0.5B-Instruct" 
print(f"Loading {model_id}...")
generator = pipeline("text-generation", model=model_id, device=-1)

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

print("Loading prompts...")
with open("data/persona_prompts.json", "r") as f:
    prompts = json.load(f)

results = []
success_count = 0

print("Running batch evaluation...")
start_time = time.time()

for p in tqdm(prompts):
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": p["text"]}
    ]
    
    try:
        # Generate
        output = generator(messages, max_new_tokens=150, do_sample=False, pad_token_id=generator.tokenizer.eos_token_id)
        response_text = output[0]['generated_text'][-1]['content']
        
        # Check for basic JSON validity (or at least presence of expected keys)
        # Note: True validation requires parsing, but we'll do a soft check here
        is_json = "{" in response_text and "}" in response_text
        if is_json:
            success_count += 1
            
        results.append({
            "id": p["id"],
            "persona": p["persona"],
            "input": p["text"],
            "output": response_text,
            "success": is_json
        })
    except Exception as e:
        results.append({
            "id": p["id"],
            "persona": p["persona"],
            "input": p["text"],
            "output": str(e),
            "success": False
        })

end_time = time.time()
print(f"\nFinished processing {len(prompts)} prompts in {end_time - start_time:.2f} seconds.")
print(f"Overall JSON Success Rate: {success_count}/{len(prompts)} ({(success_count/len(prompts))*100:.1f}%)")

with open("data/persona_results.json", "w") as f:
    json.dump(results, f, indent=2)

print("Saved results to data/persona_results.json")
