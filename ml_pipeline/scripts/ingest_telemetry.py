"""Ingest implicit usage telemetry to adapt the observation model.

This script simulates receiving anonymized, privacy-scrubbed telemetry logs
from the field. It reads JSON logs from the `telemetry_drop/` directory,
where each log represents an interaction: a transcript and the set of
AI-proposed chart labels that the nurse *actually accepted* (implicit positive
feedback).

These telemetry logs are converted into SYNUR-compatible examples and saved
to a local cache, allowing the weekly GitHub Action to combine them with the
base synthetic dataset for continual reinforcement learning.
"""

from __future__ import annotations

import json
import pickle
import sys
import uuid
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))
from config import settings
from scripts.synur_dataset import SynurExample


def ingest_telemetry_directory(drop_dir: Path, output_path: Path) -> int:
    """Read all JSON telemetry files, convert to SynurExamples, and save."""
    if not drop_dir.exists():
        print(f"Telemetry directory {drop_dir} does not exist.")
        return 0

    examples: list[SynurExample] = []
    
    for file_path in drop_dir.glob("*.json"):
        try:
            data = json.loads(file_path.read_text(encoding="utf-8"))
            # Expecting a format like:
            # {
            #   "transcript": "patient reports fever",
            #   "accepted_labels": ["Fever", "Chills"]
            # }
            if isinstance(data, list):
                logs = data
            elif isinstance(data, dict):
                logs = [data]
            else:
                continue

            for log in logs:
                transcript = log.get("transcript")
                accepted_labels = log.get("accepted_labels", [])
                
                if not transcript or not isinstance(transcript, str):
                    continue
                
                # Convert into SYNUR observation format
                observations = tuple(
                    {"name": label, "value": "Present"}
                    for label in accepted_labels
                )
                
                example = SynurExample(
                    identifier=f"telemetry-{uuid.uuid4().hex[:8]}",
                    transcript=transcript,
                    observations=observations
                )
                examples.append(example)
        except Exception as error:
            print(f"Error parsing telemetry file {file_path.name}: {error}")

    if examples:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("wb") as file:
            pickle.dump(examples, file)
        print(f"Ingested {len(examples)} telemetry examples to {output_path}")
    else:
        print("No valid telemetry examples found.")

    return len(examples)


if __name__ == "__main__":
    drop_dir = settings.BASE_DIR / "telemetry_drop"
    output_path = settings.DATA_DIR / ".cache" / "telemetry" / "telemetry_examples.pkl"
    ingested_count = ingest_telemetry_directory(drop_dir, output_path)
    if ingested_count == 0:
        sys.exit(0)  # Normal exit, workflow handles conditional training
