import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from synur_dataset import _path_for, _validate_rows  # noqa: E402


def _row(identifier="ex1", transcript="Patient has mobility deficits", observations=None):
    observations = observations if observations is not None else [{"name": "Mobility"}]
    return json.dumps({
        "id": identifier,
        "transcript": transcript,
        "observations": json.dumps(observations),
    })


def test_valid_rows_parse():
    raw = ("\n".join([_row(), _row(identifier="ex2")]) + "\n").encode("utf-8") + b"\n" + b" " * 1024
    examples = _validate_rows(raw, "train")
    assert len(examples) == 2
    assert examples[0].identifier == "ex1"
    assert examples[0].observation_names == {"Mobility"}


def test_rejects_too_small_download():
    with pytest.raises(ValueError, match="unexpectedly small"):
        _validate_rows(b"too small", "train")


def test_rejects_missing_required_key():
    bad = json.dumps({"id": "ex1", "observations": json.dumps([{"name": "Mobility"}])})
    raw = (bad + "\n").encode("utf-8") + b"\n" + b" " * 1024
    with pytest.raises(ValueError, match="Invalid SYNUR"):
        _validate_rows(raw, "train")


def test_rejects_malformed_json():
    raw = b"{not valid json}\n" + b"\n" + b" " * 1024
    with pytest.raises(ValueError, match="Invalid SYNUR"):
        _validate_rows(raw, "train")


def test_rejects_wrong_observations_shape():
    bad = json.dumps({
        "id": "ex1",
        "transcript": "text",
        "observations": json.dumps(["not-a-dict"]),
    })
    raw = (bad + "\n").encode("utf-8") + b"\n" + b" " * 1024
    with pytest.raises(ValueError, match="row shape"):
        _validate_rows(raw, "train")


def test_rejects_empty_after_padding():
    raw = b" " * 1024
    with pytest.raises(ValueError, match="no examples"):
        _validate_rows(raw, "train")


def test_rejects_unknown_split():
    # Split-name validation lives in _path_for, not _validate_rows, which
    # accepts any split label and only uses it for error-message text.
    with pytest.raises(ValueError, match="Unsupported SYNUR split"):
        _path_for("bogus_split")
