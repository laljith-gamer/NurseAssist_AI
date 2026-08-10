"""Pinned, reproducible loader for Microsoft's public SYNUR dataset.

SYNUR contains synthetic nurse dictations paired with expert-nurse structured
observations.  It is useful for an *advisory* language model; it is not a
source of real patient records and must never be used to auto-chart data.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

sys.path.append(str(Path(__file__).resolve().parent.parent))
from config import settings


DATASET_ID = "microsoft/SYNUR"
DATASET_LICENSE = "CDLA-Permissive-2.0"
# Pin a commit, rather than ``main``, so a later dataset update cannot silently
# change a released model.
DATASET_REVISION = "fc5a8c4882cfc6cd09c87c602dcdb6f3bba905b2"
DATASET_BASE_URL = (
    f"https://huggingface.co/datasets/{DATASET_ID}/resolve/"
    f"{DATASET_REVISION}/data"
)
SPLITS = {
    "train": "mediqa_synur_train-00000-of-00001.jsonl",
    "dev": "mediqa_synur_dev-00000-of-00001.jsonl",
    "test": "mediqa_synur_test-00000-of-00001.jsonl",
}


@dataclass(frozen=True)
class SynurExample:
    identifier: str
    transcript: str
    observations: tuple[dict[str, Any], ...]

    @property
    def observation_names(self) -> set[str]:
        return {
            observation["name"].strip()
            for observation in self.observations
            if isinstance(observation.get("name"), str)
            and observation["name"].strip()
        }


def _cache_dir() -> Path:
    return settings.DATA_DIR / ".cache" / "synur" / DATASET_REVISION


def _path_for(split: str) -> Path:
    if split not in SPLITS:
        raise ValueError(f"Unsupported SYNUR split: {split}")
    return _cache_dir() / SPLITS[split]


def _validate_rows(raw: bytes, split: str) -> list[SynurExample]:
    if len(raw) < 1024:
        raise ValueError(f"SYNUR {split} download is unexpectedly small")
    examples: list[SynurExample] = []
    for line_number, line in enumerate(raw.decode("utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
            observations = json.loads(row["observations"])
        except (KeyError, TypeError, json.JSONDecodeError) as error:
            raise ValueError(
                f"Invalid SYNUR {split} row at line {line_number}"
            ) from error
        if (
            not isinstance(row.get("id"), str)
            or not isinstance(row.get("transcript"), str)
            or not isinstance(observations, list)
            or not all(isinstance(item, dict) for item in observations)
        ):
            raise ValueError(f"Invalid SYNUR {split} row shape at line {line_number}")
        examples.append(
            SynurExample(
                identifier=row["id"],
                transcript=row["transcript"],
                observations=tuple(dict(item) for item in observations),
            )
        )
    if not examples:
        raise ValueError(f"SYNUR {split} contains no examples")
    return examples


def _write_manifest(files: dict[str, Path]) -> None:
    manifest = {
        "dataset_id": DATASET_ID,
        "revision": DATASET_REVISION,
        "license": DATASET_LICENSE,
        "files": {
            split: {
                "filename": path.name,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
            for split, path in files.items()
        },
    }
    manifest_path = _cache_dir() / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def download_split(split: str, *, force: bool = False) -> Path:
    """Download one public, pinned split atomically and validate its shape."""
    destination = _path_for(split)
    if destination.exists() and not force:
        _validate_rows(destination.read_bytes(), split)
        return destination

    destination.parent.mkdir(parents=True, exist_ok=True)
    source_url = f"{DATASET_BASE_URL}/{SPLITS[split]}?download=true"
    request = urllib.request.Request(
        source_url,
        headers={"User-Agent": "NurseAssist-AI-training/1.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            if response.status != 200:
                raise ValueError(f"SYNUR returned HTTP {response.status}")
            raw = response.read()
    except (urllib.error.URLError, TimeoutError) as error:
        raise RuntimeError(
            f"Could not download public SYNUR {split} split from {source_url}"
        ) from error

    _validate_rows(raw, split)
    temporary = destination.with_suffix(".download")
    temporary.write_bytes(raw)
    os.replace(temporary, destination)
    return destination


def load_split(split: str) -> list[SynurExample]:
    path = download_split(split)
    return _validate_rows(path.read_bytes(), split)


def load_all_splits() -> dict[str, list[SynurExample]]:
    paths = {split: download_split(split) for split in SPLITS}
    _write_manifest(paths)
    return {
        split: _validate_rows(path.read_bytes(), split) for split, path in paths.items()
    }


if __name__ == "__main__":
    loaded = load_all_splits()
    print(
        "Downloaded pinned SYNUR dataset "
        f"({DATASET_REVISION[:12]}): "
        + ", ".join(f"{name}={len(rows)}" for name, rows in loaded.items())
    )
