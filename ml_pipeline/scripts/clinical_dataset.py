"""Real clinical dataset processor for MTSamples.

This module downloads the public MTSamples dataset (real, de-identified 
medical transcriptions) from Hugging Face and uses weak-supervision 
(Regex/Keyword mapping) to label it with nursing observations for ML training.
"""

import re
from typing import List, Dict, Any, Tuple
from dataclasses import dataclass
from datasets import load_dataset

@dataclass(frozen=True)
class SynurExample:
    identifier: str
    transcript: str
    observations: tuple[Dict[str, Any], ...]

    @property
    def observation_names(self) -> set:
        return {
            obs["name"].strip()
            for obs in self.observations
            if isinstance(obs.get("name"), str) and obs["name"].strip()
        }

# Weak supervision rules mapping Regex patterns to Clinical Observations
LABELING_RULES: List[Tuple[re.Pattern, str]] = [
    (re.compile(r'\b(hypertension|bp\s*(is\s*)?(elevated|high)|\b1[4-9]\d/[9-9]\d)\b', re.IGNORECASE), "Hypertension"),
    (re.compile(r'\b(hypoxia|spO2\s*(is\s*)?(low|drop|<90|8[0-9])|oxygen\s*desat)\b', re.IGNORECASE), "Hypoxia"),
    (re.compile(r'\b(tachycardia|hr\s*(is\s*)?(elevated|high|>100))\b', re.IGNORECASE), "Tachycardia"),
    (re.compile(r'\b(chest\s*pain|angina|cp)\b', re.IGNORECASE), "Chest pain"),
    (re.compile(r'\b(nausea|vomiting|emesis)\b', re.IGNORECASE), "Nausea"),
    (re.compile(r'\b(severe\s*pain|pain\s*(of\s*)?[7-9]/10|pain\s*(of\s*)?10/10)\b', re.IGNORECASE), "Severe pain"),
    (re.compile(r'\b(denies\s*pain|no\s*pain|pain\s*(of\s*)?0/10|pain\s*free)\b', re.IGNORECASE), "No pain"),
    (re.compile(r'\b(agitated|combative|restless)\b', re.IGNORECASE), "Agitated"),
    (re.compile(r'\b(anxious|anxiety|nervous)\b', re.IGNORECASE), "Anxious"),
    (re.compile(r'\b(alert\s*(and|&)\s*oriented|a&o|a\+o|oriented\s*x\s*3)\b', re.IGNORECASE), "Alert and oriented"),
    (re.compile(r'\b(sleeping|asleep|resting\s*comfortably)\b', re.IGNORECASE), "Sleeping"),
    (re.compile(r'\b(ambulating|ambulated|walking|gait\s*steady)\b', re.IGNORECASE), "Ambulating"),
    (re.compile(r'\b(tolerating\s*diet|eating\s*well|po\s*intake\s*good)\b', re.IGNORECASE), "Tolerating diet"),
    (re.compile(r'\b(dressing\s*(is\s*)?(clean|dry|intact)|cdi)\b', re.IGNORECASE), "Dressing CDI"),
    (re.compile(r'\b(respirations\s*(are\s*)?(even|unlabored|normal)|breathing\s*normally)\b', re.IGNORECASE), "Normal respirations"),
    (re.compile(r'\b(respiratory\s*distress|labored\s*breathing|sob|shortness\s*of\s*breath)\b', re.IGNORECASE), "Respiratory Distress"),
    (re.compile(r'\b(foley\s*(is\s*)?(patent|draining)|catheter\s*draining)\b', re.IGNORECASE), "Foley patent"),
    (re.compile(r'\b(voiding|urine\s*clear)\b', re.IGNORECASE), "Normal voiding"),
]

def load_mtsamples_dataset(max_records: int = 5000) -> List[SynurExample]:
    """Loads and labels real clinical transcriptions from MTSamples."""
    print("Downloading real MTSamples dataset from Hugging Face...")
    try:
        # The dataset is hosted on Hugging Face Hub
        dataset = load_dataset('NickyNicky/medical_mtsamples', split='train')
    except Exception as e:
        print(f"Failed to load dataset from Hugging Face: {e}")
        print("Returning empty dataset.")
        return []

    examples = []
    skipped = 0
    count = 0

    print("Applying weak-supervision clinical labels to real transcriptions...")
    for record in dataset:
        if count >= max_records:
            break
            
        transcription = record.get('transcription')
        if not transcription or not isinstance(transcription, str) or len(transcription.strip()) < 20:
            skipped += 1
            continue
            
        # Apply Regex Rules to find observation labels
        labels = set()
        for pattern, label_name in LABELING_RULES:
            if pattern.search(transcription):
                labels.add(label_name)
                
        # Only keep records where we extracted at least one relevant observation
        if len(labels) == 0:
            skipped += 1
            continue
            
        observations = tuple([{"name": label} for label in labels])
        examples.append(
            SynurExample(
                identifier=f"mtsamples_{record.get('Unnamed: 0', count)}",
                transcript=transcription,
                observations=observations
            )
        )
        count += 1
        
    print(f"Loaded {len(examples)} real clinical notes with extracted labels (skipped {skipped} without targets).")
    return examples
