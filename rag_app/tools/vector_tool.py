import logging
import chromadb
from chromadb.utils import embedding_functions
from pydantic import BaseModel, Field
from langchain_core.tools import StructuredTool
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

CHROMA_PATH     = "./chroma_store"
COLLECTION_NAME = "financial_regulatory_kb"
EMBEDDING_MODEL = "all-MiniLM-L6-v2"
TOP_K_RESULTS   = 3


class VectorQueryInput(BaseModel):
    """
    Explicit input schema — locks parameter name to 'query' so Gemini
    never invents arbitrary names.
    """
    query: str = Field(description="Natural language question about regulations or strategy.")


def _get_collection():
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    ef = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name=EMBEDDING_MODEL
    )
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=ef,
        metadata={"hnsw:space": "cosine"},
    )


def get_vector_tool() -> StructuredTool:
    """
    Returns a StructuredTool that performs cosine-similarity search over
    the ChromaDB financial & regulatory knowledge base.
    Returns the top 3 relevant document snippets as a formatted string.
    """
    collection = _get_collection()

    def search_knowledge_base(query: str) -> str:
        try:
            results = collection.query(
                query_texts=[query],
                n_results=TOP_K_RESULTS,
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
                source   = meta.get("source", "Unknown Source")
                category = meta.get("category", "Unknown Category")
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
            logger.exception("[Vector Tool] Error during similarity search")
            return f"Vector tool error: {str(e)}"

    return StructuredTool.from_function(
        func=search_knowledge_base,
        name="regulatory_knowledge_search",
        description=(
            "Use this tool for qualitative analysis: SEBI regulatory guidelines, "
            "disclosure requirements, ESG mandates, and insights from earnings transcripts "
            "(strategic pivots, management commentary, forward guidance). "
            "Examples: 'What are SEBI D/E limits for tech companies?', "
            "'What did Aether Technologies say about their AI strategy?', "
            "'What ESG disclosures are required for large-cap companies?'"
        ),
        args_schema=VectorQueryInput,
    )