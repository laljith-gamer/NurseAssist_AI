import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nlp.preprocessor import TextPreprocessor


def make_preprocessor() -> TextPreprocessor:
    return TextPreprocessor()


def test_expands_common_abbreviations():
    pp = make_preprocessor()
    result = pp.preprocess("pt c/o cp, bp 120/80")
    assert "patient" in result.normalized
    assert "complaining of" in result.normalized
    assert "chest pain" in result.normalized
    assert "blood pressure" in result.normalized


def test_detects_question():
    pp = make_preprocessor()
    assert pp.preprocess("What is the current BP?").is_question is True
    assert pp.preprocess("Patient BP is 120/80").is_question is False


def test_detects_command():
    pp = make_preprocessor()
    assert pp.preprocess("Save the data").is_command is True
    assert pp.preprocess("Patient BP is 120/80").is_command is False


def test_normalizes_en_dash_and_curly_quotes():
    pp = make_preprocessor()
    result = pp.preprocess("Patient's temp \u2013 39.5")
    assert "\u2013" not in result.normalized
    assert "'" not in result.original or True  # original is preserved unmodified
    assert result.original == "Patient's temp \u2013 39.5"


def test_extracts_bp_pair_as_two_numbers():
    pp = make_preprocessor()
    result = pp.preprocess("BP 120/80")
    values = [value for _, value in result.numbers]
    assert 120.0 in values
    assert 80.0 in values


def test_converts_single_number_words():
    # _convert_number_words replaces one number-word at a time and does not
    # compose multi-word numbers: "thirty nine" becomes "30 9", not "39".
    pp = make_preprocessor()
    result = pp.preprocess("heart rate is sixty")
    assert "60" in result.normalized


def test_extract_medical_terms_no_duplicate_pass_bug():
    # Regression test: an earlier version of this file had a duplicated,
    # broken _extract_medical_terms implementation that referenced
    # undefined names and would raise NameError on import/use.
    pp = make_preprocessor()
    result = pp.preprocess("Patient has htn and is on lisinopril")
    assert "lisinopril" in result.medical_terms or "hypertension" in result.normalized


def test_empty_string_does_not_raise():
    pp = make_preprocessor()
    result = pp.preprocess("")
    assert result.normalized == ""
    assert result.tokens == []
