"""Unit tests for the BioClinicalBERT embedder module.

These tests validate the embedder's interface, caching, and graceful
degradation without requiring the full BioClinicalBERT model download.
Tests that need the actual model are skipped unless NURSEASSIST_RUN_BERT_TESTS=1.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

sys.path.append(str(Path(__file__).resolve().parent.parent))
from nlp.bioclinicalbert_embedder import BioClinicalBertEmbedder


# ---------------------------------------------------------------------------
# Lightweight tests (no model download required)
# ---------------------------------------------------------------------------

class TestEmbedderInterface:
    """Test the embedder's public API without loading the actual model."""

    def test_empty_input_returns_empty_array(self):
        embedder = BioClinicalBertEmbedder()
        result = embedder.encode([])
        assert isinstance(result, np.ndarray)
        assert result.shape == (0, 768)

    def test_content_hash_deterministic(self):
        embedder = BioClinicalBertEmbedder()
        texts = ["patient has fever", "bp is 120/80"]
        hash1 = embedder._content_hash(texts)
        hash2 = embedder._content_hash(texts)
        assert hash1 == hash2

    def test_content_hash_varies_with_input(self):
        embedder = BioClinicalBertEmbedder()
        hash1 = embedder._content_hash(["patient has fever"])
        hash2 = embedder._content_hash(["patient has cough"])
        assert hash1 != hash2

    def test_content_hash_varies_with_model_name(self):
        e1 = BioClinicalBertEmbedder(model_name="model-a")
        e2 = BioClinicalBertEmbedder(model_name="model-b")
        texts = ["same text"]
        assert e1._content_hash(texts) != e2._content_hash(texts)

    def test_cache_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir)
            embedder = BioClinicalBertEmbedder(cache_dir=cache_dir)
            fake_embeddings = np.random.randn(5, 768).astype(np.float32)
            key = "test_cache_key"

            embedder._save_cached(key, fake_embeddings)
            loaded = embedder._load_cached(key)

            assert loaded is not None
            np.testing.assert_array_almost_equal(fake_embeddings, loaded)

    def test_cache_returns_none_when_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir)
            embedder = BioClinicalBertEmbedder(cache_dir=cache_dir)
            result = embedder._load_cached("nonexistent_key")
            assert result is None

    def test_cache_disabled_when_none(self):
        embedder = BioClinicalBertEmbedder(cache_dir=None)
        fake_embeddings = np.random.randn(3, 768).astype(np.float32)
        # Should not raise; just silently skip
        embedder._save_cached("key", fake_embeddings)
        result = embedder._load_cached("key")
        assert result is None

    def test_invalid_pooling_raises(self):
        """Ensure invalid pooling strategy is caught (via mocked model)."""
        embedder = BioClinicalBertEmbedder()
        # Mock the model loading and inference
        embedder._model = MagicMock()
        embedder._tokenizer = MagicMock()
        embedder._device = "cpu"

        with pytest.raises(ValueError, match="Unknown pooling"):
            embedder.encode(["test text"], pooling="invalid")


class TestAvailabilityCheck:
    """Test the is_available property under different import scenarios."""

    def test_is_available_reflects_imports(self):
        embedder = BioClinicalBertEmbedder()
        # The property should return a boolean regardless of whether
        # torch/transformers are installed
        assert isinstance(embedder.is_available, bool)


# ---------------------------------------------------------------------------
# Integration tests (require actual model download)
# ---------------------------------------------------------------------------

_RUN_BERT_TESTS = os.environ.get("NURSEASSIST_RUN_BERT_TESTS", "0") == "1"


@pytest.mark.skipif(not _RUN_BERT_TESTS, reason="Set NURSEASSIST_RUN_BERT_TESTS=1")
class TestBertIntegration:
    """Integration tests that require the actual BioClinicalBERT model."""

    @pytest.fixture(autouse=True)
    def setup_embedder(self, tmp_path):
        self.embedder = BioClinicalBertEmbedder(
            cache_dir=tmp_path / "bert_cache",
            batch_size=4,
        )

    def test_encode_produces_correct_shape(self):
        texts = [
            "Patient reports chest pain radiating to left arm.",
            "Blood pressure is 140/90 mmHg.",
            "Administered 500mg acetaminophen PO.",
        ]
        embeddings = self.embedder.encode(texts)
        assert embeddings.shape == (3, 768)

    def test_embeddings_are_l2_normalized(self):
        texts = ["SpO2 is 92% on room air."]
        embeddings = self.embedder.encode(texts)
        norm = np.linalg.norm(embeddings[0])
        assert abs(norm - 1.0) < 1e-5

    def test_encode_single(self):
        embedding = self.embedder.encode_single("Heart rate is 88 bpm.")
        assert embedding.shape == (768,)
        assert abs(np.linalg.norm(embedding) - 1.0) < 1e-5

    def test_deterministic_output(self):
        text = "Patient denies shortness of breath."
        emb1 = self.embedder.encode_single(text)
        emb2 = self.embedder.encode_single(text)
        np.testing.assert_array_almost_equal(emb1, emb2, decimal=5)

    def test_mean_pooling(self):
        texts = ["Temperature is 38.2 degrees Celsius."]
        cls_emb = self.embedder.encode(texts, pooling="cls")
        mean_emb = self.embedder.encode(texts, pooling="mean")
        # CLS and mean pooling should produce different results
        assert not np.allclose(cls_emb, mean_emb, atol=1e-3)

    def test_clinical_texts_differ_from_general(self):
        """Clinical text embeddings should differ from unrelated text."""
        clinical = self.embedder.encode_single("Administered heparin 5000 units SC.")
        general = self.embedder.encode_single("The weather is sunny today.")
        similarity = np.dot(clinical, general)
        # They should be somewhat dissimilar (cosine similarity < 0.9)
        assert similarity < 0.9

    def test_caching_works_end_to_end(self):
        texts = ["Patient has bilateral crackles on auscultation."]
        # First call computes and caches
        emb1 = self.embedder.encode(texts)
        # Second call should load from cache
        emb2 = self.embedder.encode(texts)
        np.testing.assert_array_equal(emb1, emb2)

    def test_batch_consistency(self):
        """Single encoding should match its position in a batch."""
        texts = [
            "Oxygen saturation is 95%.",
            "Patient is alert and oriented.",
            "Wound is clean, dry, and intact.",
        ]
        batch_emb = self.embedder.encode(texts)
        for i, text in enumerate(texts):
            single_emb = self.embedder.encode_single(text)
            np.testing.assert_array_almost_equal(
                batch_emb[i], single_emb, decimal=4,
            )
