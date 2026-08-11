import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nlp.entity_extractor import EntityExtractor


def make_extractor() -> EntityExtractor:
    return EntityExtractor()


def test_extracts_blood_pressure():
    ex = make_extractor()
    result = ex.extract("Patient BP is 150/90")
    assert result.vitals["bp"] == {"systolic": 150, "diastolic": 90}


def test_extracts_heart_rate():
    ex = make_extractor()
    result = ex.extract("Heart rate 85 bpm")
    assert result.vitals["hr"] == 85


def test_extracts_temperature():
    ex = make_extractor()
    result = ex.extract("Temperature 39.5")
    assert result.vitals["temp"] == 39.5


def test_extracts_spo2():
    ex = make_extractor()
    result = ex.extract("SpO2 is 91%")
    assert result.vitals["spo2"] == 91


def test_extracts_known_medication():
    ex = make_extractor()
    result = ex.extract("Gave patient 500mg Tylenol")
    assert result.medications["name"] == "Tylenol"


def test_unknown_medication_not_extracted():
    ex = make_extractor()
    result = ex.extract("Gave patient 500mg Frobenizine")
    assert "name" not in result.medications


def test_extracts_room_number():
    ex = make_extractor()
    result = ex.extract("Select room 204")
    assert result.patient_identifiers["room"] == "204"


def test_no_entities_in_unrelated_text():
    ex = make_extractor()
    result = ex.extract("The weather is nice today")
    assert result.vitals == {}
    assert result.medications == {}
    assert result.patient_identifiers == {}
