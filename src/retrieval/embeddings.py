"""
Embedding Provider Abstraction
==============================
Defines a clean EmbeddingProvider interface so the rest of the system
is fully decoupled from any specific embedding backend.

Active providers
----------------
LocalSentenceTransformerProvider  (default – runs entirely offline, no API key)
    Model: all-MiniLM-L6-v2
    Dimension: 384
    Uses ONNX Runtime + tokenizers for ultra-fast, offline CPU inference
    without heavy torch DLL dependencies.
    Produces unit-length 384-dimensional normalized vectors with strong semantic quality.

OpenAIEmbeddingProvider           (optional – requires OPENAI_API_KEY)
    Model: text-embedding-3-small (or overridden via EMBEDDING_MODEL env var)
    Dimension: 1536 (or 768 / 3072 depending on model)

The vector dimension is intentional and consistent:
  - EMBEDDING_DIM in config.py is set to match whichever provider is active.
  - PostgreSQL/pgvector schema and LocalHybridStore both read this value at schema
    creation time, so the dimension stays consistent across the stack.

Selecting a provider
--------------------
Set EMBEDDING_PROVIDER=local   → LocalSentenceTransformerProvider (default)
Set EMBEDDING_PROVIDER=openai  → OpenAIEmbeddingProvider
"""

from abc import ABC, abstractmethod
from typing import List, Optional
import os
import logging
import numpy as np

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Abstract interface
# ---------------------------------------------------------------------------

class EmbeddingProvider(ABC):
    """Common interface every embedding backend must implement."""

    @property
    @abstractmethod
    def dimension(self) -> int:
        """The number of dimensions produced by this provider."""

    @abstractmethod
    def embed_text(self, text: str) -> List[float]:
        """Return a unit-length embedding vector for a single text string."""

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Return embeddings for a list of texts.
        Providers may override with a true batch call for efficiency.
        Default: sequential single-text calls.
        """
        return [self.embed_text(t) for t in texts]


# ---------------------------------------------------------------------------
# Provider 1: Local sentence-transformers (default / offline)
# ---------------------------------------------------------------------------

class LocalSentenceTransformerProvider(EmbeddingProvider):
    """
    Local embedding provider implementing all-MiniLM-L6-v2.

    Engine:
    - Primary: ONNX Runtime + tokenizers (native, CPU-optimized, ~5ms per sentence,
      bypasses torch DLL restrictions on Windows).
    - Fallback: sentence_transformers library if ONNX is unavailable.

    Why this model:
    - 22 MB download, CPU-friendly, ~5-20 ms per sentence.
    - 384-dimensional normalized vectors with strong semantic retrieval quality.
    - No API key, no quota, no network dependency after first download.
    - Widely used benchmark baseline for retrieval tasks.
    """

    MODEL_NAME = "all-MiniLM-L6-v2"
    _DIMENSION = 384

    def __init__(self, model_name: str = MODEL_NAME):
        self._model_name = model_name
        self._ort_session = None
        self._tokenizer = None
        self._st_model = None
        self._engine = None
        logger.info(
            f"LocalSentenceTransformerProvider initialized for model '{model_name}' (dim={self._DIMENSION})."
        )

    def _init_model(self):
        if self._engine is not None:
            return

        # Attempt 1: ONNX Runtime + tokenizers (fast, no torch DLL dependency)
        try:
            import onnxruntime as ort
            from tokenizers import Tokenizer
            from huggingface_hub import hf_hub_download

            logger.info("Initializing local embedding model via ONNX Runtime engine...")
            repo_id = f"sentence-transformers/{self._model_name}"
            tok_path = hf_hub_download(repo_id=repo_id, filename="tokenizer.json")
            model_path = hf_hub_download(repo_id=repo_id, filename="onnx/model.onnx")

            tokenizer = Tokenizer.from_file(tok_path)
            tokenizer.enable_truncation(max_length=256)
            tokenizer.enable_padding(pad_id=0, pad_token="[PAD]")

            # Set up session with reasonable threading
            sess_options = ort.SessionOptions()
            sess_options.intra_op_num_threads = 2
            sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL

            session = ort.InferenceSession(
                model_path,
                sess_options=sess_options,
                providers=["CPUExecutionProvider"]
            )

            self._tokenizer = tokenizer
            self._ort_session = session
            self._engine = "onnx"
            logger.info(f"ONNX Runtime model loaded successfully for {self._model_name}.")
            return
        except Exception as e:
            logger.warning(f"Could not initialize ONNX engine ({e}). Falling back to sentence_transformers.")

        # Attempt 2: sentence_transformers library
        try:
            from sentence_transformers import SentenceTransformer
            logger.info(f"Loading sentence-transformers model: {self._model_name}")
            self._st_model = SentenceTransformer(self._model_name)
            self._engine = "sentence_transformers"
            logger.info("SentenceTransformer loaded successfully.")
            return
        except Exception as e:
            logger.error(f"Failed to load sentence_transformers: {e}")
            raise RuntimeError(
                f"Failed to load local embedding model '{self._model_name}' via both ONNX and sentence_transformers: {e}"
            )

    @property
    def dimension(self) -> int:
        return self._DIMENSION

    def embed_text(self, text: str) -> List[float]:
        self._init_model()
        if self._engine == "onnx":
            return self.embed_batch([text])[0]
        else:
            vec = self._st_model.encode(text, normalize_embeddings=True, show_progress_bar=False)
            return vec.tolist()

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []

        self._init_model()
        if self._engine == "onnx":
            # Batch encode with tokenizers
            encoded = self._tokenizer.encode_batch(texts)
            input_ids = np.array([e.ids for e in encoded], dtype=np.int64)
            attention_mask = np.array([e.attention_mask for e in encoded], dtype=np.int64)
            token_type_ids = np.array([e.type_ids for e in encoded], dtype=np.int64)

            inputs = {
                "input_ids": input_ids,
                "attention_mask": attention_mask,
                "token_type_ids": token_type_ids
            }
            outputs = self._ort_session.run(None, inputs)
            token_embeddings = outputs[0]  # shape: [batch, seq_len, 384]

            # Mean pooling with attention mask
            input_mask_expanded = np.expand_dims(attention_mask, -1).astype(np.float32)
            sum_embeddings = np.sum(token_embeddings * input_mask_expanded, axis=1)
            sum_mask = np.clip(input_mask_expanded.sum(axis=1), a_min=1e-9, a_max=None)
            embeddings = sum_embeddings / sum_mask

            # L2 normalize
            norm = np.linalg.norm(embeddings, axis=1, keepdims=True)
            embeddings = embeddings / np.clip(norm, a_min=1e-12, a_max=None)

            return [row.tolist() for row in embeddings]
        else:
            vecs = self._st_model.encode(texts, normalize_embeddings=True, show_progress_bar=False, batch_size=32)
            return [v.tolist() for v in vecs]


# ---------------------------------------------------------------------------
# Provider 2: OpenAI (optional, production)
# ---------------------------------------------------------------------------

class OpenAIEmbeddingProvider(EmbeddingProvider):
    """
    Uses the OpenAI embeddings API.
    Requires OPENAI_API_KEY set in environment.

    Default model  : text-embedding-3-small  → 1536 dimensions
    Override model : set EMBEDDING_MODEL env var (e.g. text-embedding-3-large → 3072 dims)

    This provider is kept optional. If the API key is absent or the API
    returns a quota error, the caller should fall back to the local provider.
    """

    def __init__(self, api_key: str, model: str = "text-embedding-3-small"):
        self._api_key = api_key
        self._model = model
        self._client = None
        self._dim_map = {
            "text-embedding-3-small": 1536,
            "text-embedding-3-large": 3072,
            "text-embedding-ada-002": 1536,
        }
        self._dim = self._dim_map.get(model, 1536)

    def _get_client(self):
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI(api_key=self._api_key)
        return self._client

    @property
    def dimension(self) -> int:
        return self._dim

    def embed_text(self, text: str) -> List[float]:
        client = self._get_client()
        response = client.embeddings.create(model=self._model, input=text[:8000])
        return response.data[0].embedding

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        client = self._get_client()
        clean = [t[:8000] for t in texts]
        response = client.embeddings.create(model=self._model, input=clean)
        return [item.embedding for item in response.data]


# ---------------------------------------------------------------------------
# Factory & Module Singleton
# ---------------------------------------------------------------------------

def get_embedding_provider() -> EmbeddingProvider:
    """
    Resolve the active embedding provider from environment variables.

    EMBEDDING_PROVIDER=local   (default) → LocalSentenceTransformerProvider
    EMBEDDING_PROVIDER=openai           → OpenAIEmbeddingProvider
    """
    provider_name = os.getenv("EMBEDDING_PROVIDER", "local").lower().strip()

    if provider_name == "openai":
        api_key = os.getenv("OPENAI_API_KEY", "")
        if not api_key:
            logger.warning(
                "EMBEDDING_PROVIDER=openai but OPENAI_API_KEY is not set. "
                "Falling back to local sentence-transformers provider."
            )
            return LocalSentenceTransformerProvider()
        model = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
        logger.info(f"Using OpenAI embedding provider: {model}")
        return OpenAIEmbeddingProvider(api_key=api_key, model=model)

    # Default: local offline provider
    local_model = os.getenv("LOCAL_EMBEDDING_MODEL", LocalSentenceTransformerProvider.MODEL_NAME)
    return LocalSentenceTransformerProvider(model_name=local_model)


# Singleton instance accessible across services
embedding_generator: EmbeddingProvider = get_embedding_provider()
