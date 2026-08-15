import pytest
import numpy as np
from sklearn.neural_network import MLPClassifier

from scripts.train_observation_model import (
    _select_labels,
    _verify_parameter_budget,
    _best_threshold,
)

def test_select_labels():
    labels = ["A", "B", "C", "D"]
    
    # 5 examples total. A, B, C have support=5. D has support=1.
    targets = [
        [1, 1, 1, 1],
        [1, 1, 1, 0],
        [1, 1, 1, 0],
        [1, 1, 1, 0],
        [1, 1, 1, 0]
    ]
    
    probabilities = [
        [0.9, 0.9, 0.9, 0.9],
        [0.9, 0.9, 0.9, 0.1],
        [0.9, 0.9, 0.9, 0.1],
        [0.9, 0.9, 0.9, 0.1],
        [0.9, 0.9, 0.9, 0.1],
    ]
    threshold = 0.5
    
    chosen, details = _select_labels(labels, targets, probabilities, threshold)
    assert "A" in chosen
    assert "B" in chosen
    assert "C" in chosen
    assert "D" not in chosen
    
    with pytest.raises(RuntimeError, match="Validation did not yield three sufficiently reliable"):
        _select_labels(["A", "B"], targets, probabilities, threshold)

def test_verify_parameter_budget():
    class MockMLP:
        def __init__(self, size):
            self.coefs_ = [np.ones(size)]
            self.intercepts_ = [np.ones(1)]
            
    under_budget = MockMLP(499999)
    _verify_parameter_budget(under_budget)
    
    over_budget = MockMLP(500000)
    with pytest.raises(ValueError, match="Model exceeds 500K parameter budget"):
        _verify_parameter_budget(over_budget)

def test_best_threshold():
    targets = [[1], [1], [0], [0]]
    probabilities = [[0.52], [0.52], [0.48], [0.48]]
    
    best = _best_threshold(targets, probabilities)
    assert best == 0.50
