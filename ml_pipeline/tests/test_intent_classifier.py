import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nlp.intent_classifier import IntentClassifier, Intent


def make_classifier() -> IntentClassifier:
    return IntentClassifier()


def test_record_vitals():
    ic = make_classifier()
    assert ic.classify("Patient BP is 150/90").intent == Intent.RECORD_VITALS


def test_record_medication():
    ic = make_classifier()
    assert ic.classify("Gave patient 500mg Tylenol").intent == Intent.RECORD_MEDICATION


def test_query_medications():
    ic = make_classifier()
    assert ic.classify("What meds are due?").intent == Intent.QUERY_MEDICATIONS


def test_command_cancel():
    ic = make_classifier()
    assert ic.classify("Cancel that").intent == Intent.COMMAND_CANCEL


def test_command_save():
    ic = make_classifier()
    assert ic.classify("Save the data").intent == Intent.COMMAND_SAVE


def test_greeting():
    ic = make_classifier()
    assert ic.classify("Hello").intent == Intent.GREETING


def test_summarize():
    ic = make_classifier()
    assert ic.classify("Give me a quick summary of the patient").intent == Intent.SUMMARIZE


def test_empty_string_is_unknown():
    ic = make_classifier()
    result = ic.classify("")
    assert result.intent == Intent.UNKNOWN
    assert result.confidence == 0.0


def test_unmatched_text_is_unknown():
    ic = make_classifier()
    result = ic.classify("Tell me a joke")
    assert result.intent == Intent.UNKNOWN
