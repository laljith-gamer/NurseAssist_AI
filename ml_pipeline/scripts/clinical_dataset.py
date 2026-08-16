"""Real clinical dataset processor for MTSamples.

This module downloads the public MTSamples dataset (real, de-identified 
medical transcriptions) from Hugging Face and uses weak-supervision 
(Regex/Keyword mapping) to label it with nursing observations for ML training.

Negation detection prevents false labels from phrases like "denies chest pain".
"""

import re
import sys
from pathlib import Path
from dataclasses import dataclass
from datasets import load_dataset

sys.path.append(str(Path(__file__).resolve().parent.parent))
from config import settings

@dataclass(frozen=True)
class SynurExample:
    identifier: str
    transcript: str
    observations: tuple[dict[str, object], ...]

    @property
    def observation_names(self) -> set:
        return {
            obs["name"].strip()
            for obs in self.observations
            if isinstance(obs.get("name"), str) and obs["name"].strip()
        }

# Negation detection: check if a match is preceded by negation cues
_NEGATION_CUES = re.compile(
    r'\b(denies|denied|deny|no\b|not\b|without|negative\s+for|absent|none|'
    r'never|neither|nor\b|doesn.t|don.t|didn.t|hasn.t|wasn.t|isn.t|aren.t|'
    r'free\s+of|ruled\s+out|r/o)\b',
    re.IGNORECASE,
)

def _is_negated(text: str, match_start: int) -> bool:
    """Check if a regex match is preceded by negation within a character window."""
    window = settings.NEGATION_WINDOW
    window_start = max(0, match_start - window)
    preceding = text[window_start:match_start]
    return bool(_NEGATION_CUES.search(preceding))


# Weak supervision rules mapping Regex patterns to Clinical Observations
# Each rule is: (pattern, label, negation_aware)
# When negation_aware is True, the label is skipped if negation is detected
LABELING_RULES: list[tuple[re.Pattern, str, bool]] = [
    # --- Cardiovascular ---
    (re.compile(r'\b(hypertension|bp\s*(is\s*)?(elevated|high)|blood\s*pressure\s*(is\s*)?(elevated|high)|\b1[4-9]\d/[89]\d|\b1[4-9]\d/1[0-4]\d)\b', re.IGNORECASE), "Hypertension", True),
    (re.compile(r'\b(tachycardia|hr\s*(is\s*)?(elevated|high|>100)|heart\s*rate\s*(is\s*)?(elevated|high))\b', re.IGNORECASE), "Tachycardia", True),
    (re.compile(r'\bchest\s*pain\b', re.IGNORECASE), "Chest pain", True),
    (re.compile(r'\bangina\b', re.IGNORECASE), "Chest pain", True),

    # --- Respiratory ---
    (re.compile(r'\b(hypoxia|oxygen\s*desat)', re.IGNORECASE), "Hypoxia", True),
    (re.compile(r'\bspO2\s*(is\s*)?(low|drop|decreased|<\s*9[0-3]|8[0-9])', re.IGNORECASE), "Hypoxia", True),
    (re.compile(r'\b(respiratory\s*distress|labored\s*breathing|shortness\s*of\s*breath|dyspnea)\b', re.IGNORECASE), "Respiratory Distress", True),
    (re.compile(r'\bsob\b', re.IGNORECASE), "Respiratory Distress", True),
    (re.compile(r'\b(respirations\s*(are\s*)?(even|unlabored|normal)|breathing\s*normally)\b', re.IGNORECASE), "Normal respirations", True),

    # --- Pain ---
    (re.compile(r'\b(severe\s*pain|pain\s*(of\s*)?[7-9]\s*/\s*10|pain\s*(of\s*)?10\s*/\s*10)\b', re.IGNORECASE), "Severe pain", True),
    (re.compile(r'\b(denies\s*pain|no\s*pain|pain\s*(of\s*)?0\s*/\s*10|pain\s*free)\b', re.IGNORECASE), "No pain", False),  # negation IS the label
    (re.compile(r'\bheadache\b', re.IGNORECASE), "Headache", True),
    (re.compile(r'\b(head\s*pain|cephalgia|cephalalgia|migraine)\b', re.IGNORECASE), "Headache", True),
    (re.compile(r'\b(pain\s*(of\s*)?\d\s*/\s*10|complains?\s*of\s*pain|painful)\b', re.IGNORECASE), "Pain", True),

    # --- GI ---
    (re.compile(r'\bnausea\b', re.IGNORECASE), "Nausea", True),
    (re.compile(r'\bnauseous\b', re.IGNORECASE), "Nausea", True),
    (re.compile(r'\b(vomiting|emesis|vomited)\b', re.IGNORECASE), "Vomiting", True),
    (re.compile(r'\b(tolerating\s*diet|eating\s*well|po\s*intake\s*good)\b', re.IGNORECASE), "Tolerating diet", True),

    # --- Neurological / Mental Status ---
    (re.compile(r'\b(agitated|combative|restless)\b', re.IGNORECASE), "Agitated", True),
    (re.compile(r'\b(anxious|anxiety|nervous)\b', re.IGNORECASE), "Anxious", True),
    (re.compile(r'\b(alert\s*(and|&)\s*oriented|a&o|a\+o|oriented\s*x\s*[34])\b', re.IGNORECASE), "Alert and oriented", True),
    (re.compile(r'\b(sleeping|asleep|resting\s*comfortably)\b', re.IGNORECASE), "Sleeping", True),
    (re.compile(r'\b(confused|confusion|disoriented|altered\s*mental\s*status)\b', re.IGNORECASE), "Confusion", True),

    # --- Mobility ---
    (re.compile(r'\b(ambulating|ambulated|walking|gait\s*steady)\b', re.IGNORECASE), "Ambulating", True),

    # --- Wounds / Lines ---
    (re.compile(r'\b(dressing\s*(is\s*)?(clean|dry|intact))\b', re.IGNORECASE), "Dressing CDI", True),
    (re.compile(r'\b(foley\s*(is\s*)?(patent|draining)|catheter\s*draining)\b', re.IGNORECASE), "Foley patent", True),
    (re.compile(r'\b(voiding|urine\s*clear)\b', re.IGNORECASE), "Normal voiding", True),

    # --- NEW: Fever / Temperature ---
    (re.compile(r'\b(fever|febrile|pyrexia)\b', re.IGNORECASE), "Fever", True),
    (re.compile(r'\b(elevated\s*temp|temp\s*(is\s*)?(elevated|high))\b', re.IGNORECASE), "Fever", True),
    (re.compile(r'\btemp(?:erature)?\s*(?:is\s*|of\s*|:?\s*)3[89](?:\.\d)?\b', re.IGNORECASE), "Fever", True),
    (re.compile(r'\btemp(?:erature)?\s*(?:is\s*|of\s*|:?\s*)4[0-2](?:\.\d)?\b', re.IGNORECASE), "Fever", True),

    # --- NEW: Weakness / Fatigue ---
    (re.compile(r'\b(weak|weakness|fatigue|fatigued|lethargic|lethargy|malaise)\b', re.IGNORECASE), "Weakness", True),

    # --- NEW: Dehydration ---
    (re.compile(r'\b(dehydrat(?:ed|ion)|poor\s*(?:fluid|oral)\s*intake|dry\s*mucous\s*membranes|poor\s*skin\s*turgor)\b', re.IGNORECASE), "Dehydration", True),

    # --- NEW: Insomnia / Sleep disturbance ---
    (re.compile(r'\b(insomnia|unable\s*to\s*sleep|poor\s*sleep|couldn.t\s*sleep|didn.t\s*sleep|difficulty\s*sleeping|sleep\s*disturbance)\b', re.IGNORECASE), "Insomnia", True),

    # --- NEW: Dizziness ---
    (re.compile(r'\b(dizzy|dizziness|lightheaded|light\s*headed|vertigo|orthostatic)\b', re.IGNORECASE), "Dizziness", True),

    # --- NEW: Edema ---
    (re.compile(r'\b(edema|swelling|swollen)\b', re.IGNORECASE), "Edema", True),
    (re.compile(r'\b(pitting\s*edema)\b', re.IGNORECASE), "Edema", True),
]


def load_mtsamples_dataset(max_records: int = 5000) -> list[SynurExample]:
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
            
        # Apply Regex Rules with negation detection
        labels = set()
        for pattern, label_name, negation_aware in LABELING_RULES:
            match = pattern.search(transcription)
            if match:
                # Skip if negation is detected before the match
                if negation_aware and _is_negated(transcription, match.start()):
                    continue
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
