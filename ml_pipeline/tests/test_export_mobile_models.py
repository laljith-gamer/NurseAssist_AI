import pytest
import json
import pickle
import hashlib
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.neural_network import MLPClassifier

from scripts.export_mobile_models import export_observation_model

def test_export_observation_model(tmp_path):
    vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 3), max_features=3)
    features = vectorizer.fit_transform(["abc def", "abc xyz"])
    
    mlp = MLPClassifier(hidden_layer_sizes=(2, 2), max_iter=1, random_state=42)
    targets = [[0, 1], [1, 0]]
    import warnings
    from sklearn.exceptions import ConvergenceWarning
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=ConvergenceWarning)
        mlp.fit(features, targets)
        
    labels = ["ClassA", "ClassB"]
    threshold = 0.5
    
    artifact = {
        "vectorizer": vectorizer,
        "mlp_model": mlp,
        "labels": labels,
        "threshold": threshold,
        "used_bert": False,
        "bert_pca": None
    }
    
    model_path = tmp_path / "clinical_observation_model.pkl"
    output_path = tmp_path / "observations.json"
    
    with model_path.open("wb") as f:
        pickle.dump(artifact, f)
        
    returned_sha = export_observation_model(model_path, output_path)
    
    with output_path.open("r", encoding="utf-8") as f:
        payload = json.load(f)
        
    assert payload["type"] == "compact_clinical_mlp"
    assert payload["format_version"] == 2
    assert payload["classes"] == labels
    assert payload["threshold"] == threshold
    
    assert np.array(payload["mlp"]["layer1_weight"]).shape == mlp.coefs_[0].T.shape
    assert np.array(payload["mlp"]["layer2_weight"]).shape == mlp.coefs_[1].T.shape
    assert np.array(payload["mlp"]["output_weight"]).shape == mlp.coefs_[2].T.shape
    
    assert np.allclose(payload["mlp"]["layer1_weight"][0][0], mlp.coefs_[0].T[0][0])
    
    with output_path.open("rb") as f:
        actual_sha = hashlib.sha256(f.read()).hexdigest()
    assert returned_sha == actual_sha
