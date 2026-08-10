"""Fail CI when the JSON export cannot reproduce the training classifiers.

The Flutter runtime uses the same sparse-vector / linear-score calculation
below.  Keeping this test beside the exporter prevents a model release that
looks valid but always predicts an intercept-only class on device.
"""

import json
import math
import pickle
import re
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))
from config import settings


def _load_pickle(filename: str):
    with open(settings.DATA_DIR / filename, "rb") as file:
        return pickle.load(file)


def _load_export(filename: str):
    with open(settings.DATA_DIR / "mobile_export" / filename, encoding="utf-8") as file:
        return json.load(file)


def predict_export(tokens: list[str], model: dict, *, tfidf: bool) -> str:
    vocab = model["vocabulary"]
    counts: dict[int, int] = {}
    for token in tokens:
        index = vocab.get(token)
        if index is not None:
            counts[index] = counts.get(index, 0) + 1

    vector: dict[int, float] = {}
    square_sum = 0.0
    for index, count in counts.items():
        value = count * model["idf"][index] if tfidf else float(count)
        vector[index] = value
        square_sum += value * value
    if tfidf and square_sum:
        norm = math.sqrt(square_sum)
        vector = {index: value / norm for index, value in vector.items()}

    scores = []
    for class_index, coefficients in enumerate(model["coef"]):
        score = model["intercept"][class_index]
        for index, value in vector.items():
            score += coefficients[index] * value
        scores.append(score)
    return model["classes"][max(range(len(scores)), key=scores.__getitem__)]


def intent_tokens(text: str) -> list[str]:
    words = [word for word in re.sub(r"[^\w\s]", " ", text.lower()).split() if word]
    return words + [f"{words[i]} {words[i + 1]}" for i in range(len(words) - 1)]


def ner_features(words: list[str], index: int) -> list[str]:
    word = words[index].lower()
    previous = words[index - 1].lower() if index else "bos"
    following = words[index + 1].lower() if index < len(words) - 1 else "eos"
    numeric = "t" if any(char.isdigit() for char in words[index]) else "f"
    return [f"w:{word}", f"p:{previous}", f"n:{following}", f"num:{numeric}"]


def verify_intent() -> None:
    pipeline = _load_pickle("intent_model.pkl")
    exported = _load_export("intent.json")
    prompts = [
        "BP 120/80",
        "What medications are due?",
        "Summarize the patient",
        "Hello",
        "Cancel that",
    ]
    for prompt in prompts:
        expected = pipeline.predict([prompt])[0]
        actual = predict_export(intent_tokens(prompt), exported, tfidf=True)
        if expected != actual:
            raise AssertionError(f"Intent mismatch for {prompt!r}: {expected} != {actual}")


def verify_ner() -> None:
    pipeline = _load_pickle("ner_model.pkl")
    exported = _load_export("ner.json")
    prompts = [
        "BP 120/80",
        "Gave Zofran 4mg",
        "Heart rate 85 bpm",
        "Temp 38.2",
        "SpO2 94%",
    ]
    for prompt in prompts:
        words = prompt.split()
        python_features = []
        export_predictions = []
        for index, word in enumerate(words):
            # CountVectorizer lowercases and tokenizes this exact whitespace
            # string. The export must receive its four pieces separately.
            features = ner_features(words, index)
            python_features.append(" ".join(features))
            export_predictions.append(predict_export(features, exported, tfidf=False))
        expected = pipeline.predict(python_features).tolist()
        if expected != export_predictions:
            raise AssertionError(
                f"NER mismatch for {prompt!r}: {expected} != {export_predictions}"
            )


if __name__ == "__main__":
    verify_intent()
    verify_ner()
    print("Mobile JSON export matches the training classifiers.")
