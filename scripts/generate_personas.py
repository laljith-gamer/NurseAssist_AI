import json
import random
import os

# Ensure data directory exists
os.makedirs("data", exist_ok=True)

# Templates for Persona 1: Calm Veteran (Voice Dictation)
p1_templates = [
    "Patient {name} is resting comfortably, vitals are stable at {bp} blood pressure and {hr} heart rate.",
    "Just checking in on {name}. Temperature is {temp}, feeling a bit better today.",
    "Vitals for {name} just taken. BP is {bp}, pulse {hr}. No acute distress.",
    "Patient is doing well. Recording blood pressure as {bp} and heart rate at {hr}.",
    "Patient reports feeling normal. Vitals: temp {temp}, bp {bp}, pulse {hr}."
]

# Templates for Persona 2: Irritated/Rushed Nurse (Rants/Nonsense)
p2_templates = [
    "Ugh finally got the BP it's {bp} this guy won't stop moving I need a break record this. Pulse {hr}.",
    "Can this shift end already? BP {bp} HR {hr} for {name}, whatever just save it.",
    "Patient {name} is so annoying today complaining about the food. By the way vitals are {bp} and {hr}.",
    "I am so tired. Temp {temp}, BP {bp}. Just put it in the system.",
    "Why is the wifi so slow? Anyway {name} has bp {bp} and hr {hr}, save it now please."
]

# Templates for Persona 3: Silent Typer (Spelling mistakes/abbreviations)
p3_templates = [
    "bld pres {bp} puls {hr} pacetnmnt feelz dizy",
    "bp {bp} hr {hr} tmp {temp} pt ok",
    "vitas: {bp} , {hr} ... {name} slypy",
    "pt {name} bp={bp} hr={hr} t={temp}",
    "record {bp} / {hr} 4 {name} thx"
]

names = ["Smith", "Jones", "Doe", "Williams", "Brown"]
bps = ["120/80", "145/95", "110/70", "130/85", "150/100"]
hrs = ["75", "88", "60", "92", "110"]
temps = ["98.6", "99.1", "101.2", "97.5"]

prompts = []

# Generate 500 prompts (roughly 166 per persona)
for i in range(500):
    persona = (i % 3) + 1
    name = random.choice(names)
    bp = random.choice(bps)
    hr = random.choice(hrs)
    temp = random.choice(temps)
    
    if persona == 1:
        template = random.choice(p1_templates)
    elif persona == 2:
        template = random.choice(p2_templates)
    else:
        template = random.choice(p3_templates)
        
    text = template.format(name=name, bp=bp, hr=hr, temp=temp)
    
    # Introduce random typos for persona 3
    if persona == 3 and random.random() > 0.5:
        text = text.replace("bp", "pb").replace("hr", "rh").replace("temp", "tmp")
        
    prompts.append({
        "id": i,
        "persona": persona,
        "text": text
    })

with open("data/persona_prompts.json", "w") as f:
    json.dump(prompts, f, indent=2)

print(f"Generated {len(prompts)} prompts in data/persona_prompts.json")
