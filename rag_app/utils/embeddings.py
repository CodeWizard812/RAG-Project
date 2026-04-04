
# Single place that provides the embedding function for ChromaDB.
# Uses Google's text-embedding-004 model instead of sentence-transformers,
# which removes the entire torch/transformers stack from requirements.

import os
import logging
from typing import List
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)


class GeminiEmbeddingFunction:
    """
    ChromaDB-compatible embedding function using Google's
    text-embedding-004 model via the google-generativeai SDK.

    Replaces SentenceTransformerEmbeddingFunction entirely.
    Produces 768-dimensional embeddings — same dimensionality as
    all-MiniLM-L6-v2, so existing ChromaDB collections are compatible
    after a reseed.

    Usage (identical interface to ChromaDB's built-in functions):
        ef = GeminiEmbeddingFunction()
        collection = client.get_or_create_collection("kb", embedding_function=ef)
    """

    def __init__(self):
        import google.generativeai as genai
        api_key = self._get_api_key()
        genai.configure(api_key=api_key)
        self._genai = genai
        logger.info("[Embeddings] Gemini embedding function initialised.")

    def _get_api_key(self) -> str:
        """
        Uses the first available Gemini key from the pool.
        Embedding calls are cheap and rarely hit rate limits separately.
        """
        for i in range(1, 21):
            key = os.getenv(f"GEMINI_API_KEY_{i}", "").strip()
            if key and len(key) > 10:
                return key
        fallback = os.getenv("GEMINI_API_KEY", "").strip()
        if fallback and len(fallback) > 10:
            return fallback
        raise EnvironmentError(
            "No Gemini API key found for embeddings. "
            "Set GEMINI_API_KEY_1 in your .env file."
        )

    def __call__(self, input: List[str]) -> List[List[float]]:
        """
        ChromaDB calls this with a list of strings.
        Returns a list of embedding vectors.
        """
        result = self._genai.embed_content(
            model="models/text-embedding-004",
            content=input,
            task_type="retrieval_document",
        )
        return result["embedding"] if isinstance(input, str) else [
            e for e in result["embedding"]
        ]

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """LangChain-compatible interface."""
        return self(texts)

    def embed_query(self, text: str) -> List[float]:
        """LangChain-compatible interface for single query embedding."""
        result = self._genai.embed_content(
            model="models/text-embedding-004",
            content=text,
            task_type="retrieval_query",
        )
        return result["embedding"]