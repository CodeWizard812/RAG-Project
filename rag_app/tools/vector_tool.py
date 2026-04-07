import os
import logging
import chromadb
from pydantic import BaseModel, Field
from langchain_core.tools import StructuredTool
from dotenv import load_dotenv
from rag_app.utils.embeddings import GeminiEmbeddingFunction

load_dotenv()
logger          = logging.getLogger(__name__)
CHROMA_PATH     = os.getenv("CHROMA_PATH", "./chroma_store")
COLLECTION_NAME = "financial_regulatory_kb"
TOP_K_RESULTS   = 3

# Module-level singleton so the collection object is reused across
# requests — avoids re-opening the ChromaDB client on every query
_collection = None


def _get_collection():
    global _collection
    if _collection is None:
        client      = chromadb.PersistentClient(path=CHROMA_PATH)
        ef          = GeminiEmbeddingFunction()
        _collection = client.get_or_create_collection(
            name=COLLECTION_NAME,
            embedding_function=ef,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info(
            f"[VectorTool] Collection opened: {COLLECTION_NAME} "
            f"({_collection.count()} docs)"
        )
    return _collection


def refresh_collection():
    """
    Called after a PDF is ingested to force the singleton to re-read
    the collection from disk, picking up the newly added chunks.
    """
    global _collection
    _collection = None
    logger.info("[VectorTool] Collection cache cleared — will reload on next query.")


class VectorQueryInput(BaseModel):
    query: str = Field(
        description=(
            "Natural language question about regulations, strategy, earnings, "
            "or any document uploaded by the user."
        )
    )


def get_vector_tool() -> StructuredTool:
    """
    Returns a StructuredTool that performs cosine-similarity search over
    the ChromaDB knowledge base, which includes both seeded regulatory
    documents and any PDFs uploaded by the user.
    """
    def search_knowledge_base(query: str) -> str:
        try:
            col   = _get_collection()
            count = col.count()

            if count == 0:
                return "The knowledge base is empty. No documents have been seeded or uploaded."

            results = col.query(
                query_texts=[query],
                n_results=min(TOP_K_RESULTS, count),
                include=["documents", "metadatas", "distances"],
            )

            documents = results.get("documents", [[]])[0]
            metadatas = results.get("metadatas", [[]])[0]
            distances = results.get("distances", [[]])[0]

            if not documents:
                return "No relevant documents found in the knowledge base."

            snippets = []
            for i, (doc, meta, dist) in enumerate(
                zip(documents, metadatas, distances), start=1
            ):
                similarity_pct = round((1 - dist) * 100, 1)
                source   = meta.get("source",        "Unknown Source")
                category = meta.get("category",      "Unknown Category")
                doc_type = meta.get("document_type", "")

                header = (
                    f"[Source {i} | {category} | {doc_type} | "
                    f"Relevance: {similarity_pct}%]\n"
                    f"Source: {source}"
                )
                snippets.append(f"{header}\n\n{doc.strip()}")

            separator = "\n\n" + "─" * 60 + "\n\n"
            return "\n\n" + separator.join(snippets)

        except Exception as e:
            logger.exception("[VectorTool] Error during similarity search")
            return f"Vector tool error: {str(e)}"

    return StructuredTool.from_function(
        func=search_knowledge_base,
        name="regulatory_knowledge_search",
        description=(
            "Use this tool to search ALL qualitative content: SEBI regulatory guidelines, "
            "disclosure requirements, ESG mandates, earnings transcripts, and any PDF "
            "documents uploaded by the user. This is the correct tool whenever the user "
            "asks about an uploaded document, a filing, an annual report, or any "
            "non-numerical content. Input should be a natural language question."
        ),
        args_schema=VectorQueryInput,
    )