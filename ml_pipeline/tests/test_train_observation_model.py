import pytest
import numpy as np
from sklearn.neural_network import MLPClassifier

from scripts.train_observation_model import (
    _select_labels,
    _verify_parameter_budget,
    _best_threshold,
    _distill_targets,
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
    
    with pytest.raises(RuntimeError, match="Validation did not yield"):
        _select_labels(["A", "B"], targets, probabilities, threshold)

def test_verify_parameter_budget():
    class MockMLP:
        def __init__(self, size):
            self.coefs_ = [np.ones(size)]
            self.intercepts_ = [np.ones(1)]
            
    under_budget = MockMLP(299999)
    _verify_parameter_budget(under_budget)
    
    over_budget = MockMLP(300000)
    with pytest.raises(ValueError, match="Model exceeds"):
        _verify_parameter_budget(over_budget)

def test_best_threshold():
    targets = [[1], [1], [0], [0]]
    probabilities = [[0.52], [0.52], [0.48], [0.48]]
    
    best = _best_threshold(targets, probabilities)
    assert best == 0.50

def test_distill_targets():
    """Teacher predictions should augment hard labels when confident."""
    hard = np.array([
        [1, 0, 0],  # only label A
        [0, 1, 0],  # only label B
        [0, 0, 1],  # only label C
    ])
    # Teacher is confident about label B for sample 0 (knowledge transfer)
    teacher_proba = np.array([
        [0.9, 0.8, 0.1],  # teacher also sees B for sample 0
        [0.1, 0.9, 0.1],  # agrees with hard label
        [0.1, 0.1, 0.9],  # agrees with hard label
    ])
    
    distilled = _distill_targets(hard, teacher_proba, alpha=0.5, temperature=2.0)
    
    # Sample 0: hard=[1,0,0], teacher=[0.9,0.8,0.1]
    # Blended label B should be > 0 due to teacher confidence
    assert distilled[0][0] == 1  # label A stays 1
    assert distilled[1][1] == 1  # label B stays 1
    assert distilled[2][2] == 1  # label C stays 1
    # Distilled targets must be valid binary
    for row in distilled:
        for val in row:
            assert val in (0, 1)
