import json

with open("data/persona_results.json", "r") as f:
    d = json.load(f)

for p in [1, 2, 3]:
    subset = [x for x in d if x["persona"] == p]
    successes = sum(1 for x in subset if x["success"])
    print(f"Persona {p}: {successes}/{len(subset)} ({successes/len(subset)*100:.1f}%)")
