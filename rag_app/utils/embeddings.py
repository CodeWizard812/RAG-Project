import os
import logging
from typing import List
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)


class GeminiEmbeddingFunction:
    """
    ChromaDB-compatible embedding function using GoogleGenerativeAIEmbeddings
    from langchain-google-genai.

    Does NOT import google.generativeai directly — that package conflicts
    with langchain-google-genai>=2.0 and is not needed. langchain-google-genai
    provides everything required.
    """

    def __init__(self):
        from langchain_google_genai import GoogleGenerativeAIEmbeddings
        api_key = self._get_api_key()
        self._model = GoogleGenerativeAIEmbeddings(
            model="models/gemini-embedding-001",
            google_api_key=api_key,
            task_type="retrieval_document",
        )
        logger.info("[Embeddings] GeminiEmbeddingFunction initialised via langchain-google-genai.")

    def _get_api_key(self) -> str:
        for i in range(1, 21):
            key = os.getenv(f"GEMINI_API_KEY_{i}", "").strip()
            if key and len(key) > 10:
                return key
        fallback = os.getenv("GEMINI_API_KEY", "").strip()
        if fallback and len(fallback) > 10:
            return fallback
        raise EnvironmentError(
            "No Gemini API key found. Set GEMINI_API_KEY_1 in your .env file."
        )

    def __call__(self, input: List[str]) -> List[List[float]]:
        """ChromaDB calls this with a list of strings."""
        return self._model.embed_documents(input)

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return self._model.embed_documents(texts)

    def embed_query(self, text: str) -> List[float]:
        from langchain_google_genai import GoogleGenerativeAIEmbeddings
        query_model = GoogleGenerativeAIEmbeddings(
            model="models/gemini-embedding-001",
            google_api_key=self._get_api_key(),
            task_type="retrieval_query",
        )
        return query_model.embed_query(text)