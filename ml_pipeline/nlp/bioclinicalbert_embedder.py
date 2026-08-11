"""BioClinicalBERT embedding extractor for training-time feature generation.

This module loads the ``emilyalsentzer/Bio_ClinicalBERT`` model from Hugging
Face and produces dense 768-dimensional embeddings for clinical text. These
embeddings are used *only* during training to improve the observation model's
quality. They are NOT shipped to mobile devices.

BioClinicalBERT is a BERT model pre-trained on clinical notes from MIMIC-III,
giving it strong understanding of clinical language, abbreviations, and medical
terminology that TF-IDF alone cannot capture.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


def _try_import_torch():
    """Lazy import torch so the module can be imported without it installed."""
    try:
        import torch
        return torch
    except ImportError:
        return None


def _try_import_transformers():
    """Lazy import transformers for the same reason."""
    try:
        from transformers import AutoModel, AutoTokenizer
        return AutoModel, AutoTokenizer
    except ImportError:
        return None, None


class BioClinicalBertEmbedder:
    """Extract dense clinical-text embeddings using BioClinicalBERT.

    The embedder is designed for batch training use:
    - Loads the model once and reuses it across all calls.
    - Caches computed embeddings to disk keyed by a content hash, so
      repeated training runs on the same data skip the forward pass.
    - Falls back gracefully when ``torch`` or ``transformers`` are missing.

    Parameters
    ----------
    model_name : str
        Hugging Face model identifier.
    max_length : int
        Maximum token length for the tokenizer.
    batch_size : int
        Number of texts to process in a single forward pass.
    cache_dir : Path or None
        Directory for caching computed embeddings. ``None`` disables caching.
    """

    EMBEDDING_DIM = 768

    def __init__(
        self,
        model_name: str = "emilyalsentzer/Bio_ClinicalBERT",
        max_length: int = 512,
        batch_size: int = 32,
        cache_dir: Optional[Path] = None,
    ):
        self.model_name = model_name
        self.max_length = max_length
        self.batch_size = batch_size
        self.cache_dir = cache_dir
        self._model = None
        self._tokenizer = None
        self._device = None
        self._available: Optional[bool] = None

    @property
    def is_available(self) -> bool:
        """Check if torch and transformers are installed."""
        if self._available is None:
            torch = _try_import_torch()
            AutoModel, AutoTokenizer = _try_import_transformers()
            self._available = torch is not None and AutoModel is not None
        return self._available

    def _ensure_loaded(self) -> None:
        """Load the model and tokenizer on first use."""
        if self._model is not None:
            return

        torch = _try_import_torch()
        AutoModel, AutoTokenizer = _try_import_transformers()
        if torch is None or AutoModel is None:
            raise RuntimeError(
                "BioClinicalBERT requires 'torch' and 'transformers' packages. "
                "Install them with: pip install torch transformers"
            )

        logger.info("Loading BioClinicalBERT model: %s", self.model_name)
        self._tokenizer = AutoTokenizer.from_pretrained(self.model_name)
        self._model = AutoModel.from_pretrained(self.model_name)
        self._device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self._model = self._model.to(self._device)
        self._model.eval()
        logger.info(
            "BioClinicalBERT loaded on %s (%d parameters)",
            self._device,
            sum(p.numel() for p in self._model.parameters()),
        )

    def _content_hash(self, texts: list[str]) -> str:
        """Compute a stable hash for a list of texts to key the cache."""
        hasher = hashlib.sha256()
        hasher.update(self.model_name.encode())
        hasher.update(str(self.max_length).encode())
        for text in texts:
            hasher.update(text.encode("utf-8"))
        return hasher.hexdigest()[:16]

    def _load_cached(self, cache_key: str) -> Optional[np.ndarray]:
        """Load cached embeddings if they exist."""
        if self.cache_dir is None:
            return None
        cache_path = self.cache_dir / f"embeddings_{cache_key}.npy"
        if cache_path.exists():
            try:
                embeddings = np.load(str(cache_path))
                logger.info("Loaded cached embeddings from %s", cache_path.name)
                return embeddings
            except Exception as error:
                logger.warning("Cache load failed (%s), recomputing", error)
        return None

    def _save_cached(self, cache_key: str, embeddings: np.ndarray) -> None:
        """Save computed embeddings to disk cache."""
        if self.cache_dir is None:
            return
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        cache_path = self.cache_dir / f"embeddings_{cache_key}.npy"
        try:
            np.save(str(cache_path), embeddings)
            logger.info("Cached embeddings to %s", cache_path.name)
        except Exception as error:
            logger.warning("Could not cache embeddings: %s", error)

    def encode(
        self,
        texts: list[str],
        *,
        pooling: str = "cls",
        show_progress: bool = True,
    ) -> np.ndarray:
        """Encode a list of clinical texts into dense embeddings.

        Parameters
        ----------
        texts : list[str]
            The clinical texts to embed.
        pooling : str
            Pooling strategy: ``"cls"`` for [CLS] token embedding, or
            ``"mean"`` for mean pooling over non-padding tokens.
        show_progress : bool
            Whether to print progress to stdout.

        Returns
        -------
        np.ndarray
            Array of shape ``(len(texts), 768)`` with L2-normalized embeddings.
        """
        if not texts:
            return np.zeros((0, self.EMBEDDING_DIM), dtype=np.float32)

        cache_key = self._content_hash(texts)
        cached = self._load_cached(cache_key)
        if cached is not None and cached.shape[0] == len(texts):
            return cached

        self._ensure_loaded()
        torch = _try_import_torch()

        all_embeddings: list[np.ndarray] = []
        total_batches = (len(texts) + self.batch_size - 1) // self.batch_size

        for batch_index in range(total_batches):
            start = batch_index * self.batch_size
            end = min(start + self.batch_size, len(texts))
            batch_texts = texts[start:end]

            if show_progress:
                print(
                    f"  BioClinicalBERT: encoding batch "
                    f"{batch_index + 1}/{total_batches} "
                    f"({start}–{end} of {len(texts)} texts)",
                    flush=True,
                )

            encoded = self._tokenizer(
                batch_texts,
                padding=True,
                truncation=True,
                max_length=self.max_length,
                return_tensors="pt",
            )
            encoded = {key: val.to(self._device) for key, val in encoded.items()}

            with torch.no_grad():
                outputs = self._model(**encoded)

            if pooling == "cls":
                # Use the [CLS] token representation (first token)
                batch_embeddings = outputs.last_hidden_state[:, 0, :].cpu().numpy()
            elif pooling == "mean":
                # Mean pooling: average over non-padding tokens
                attention_mask = encoded["attention_mask"]
                token_embeddings = outputs.last_hidden_state
                mask_expanded = (
                    attention_mask.unsqueeze(-1)
                    .expand(token_embeddings.size())
                    .float()
                )
                sum_embeddings = torch.sum(token_embeddings * mask_expanded, dim=1)
                sum_mask = torch.clamp(mask_expanded.sum(dim=1), min=1e-9)
                batch_embeddings = (sum_embeddings / sum_mask).cpu().numpy()
            else:
                raise ValueError(f"Unknown pooling strategy: {pooling!r}")

            all_embeddings.append(batch_embeddings)

        embeddings = np.vstack(all_embeddings).astype(np.float32)

        # L2 normalize each embedding vector
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        norms = np.maximum(norms, 1e-12)
        embeddings = embeddings / norms

        self._save_cached(cache_key, embeddings)
        return embeddings

    def encode_single(self, text: str, *, pooling: str = "cls") -> np.ndarray:
        """Convenience method for encoding a single text.

        Returns a 1-D array of shape ``(768,)``.
        """
        return self.encode([text], pooling=pooling, show_progress=False)[0]
