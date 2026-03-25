import os
import chromadb
from chromadb.utils import embedding_functions
from langchain_core.tools import Tool
from dotenv import load_dotenv

load_dotenv()

CHROMA_PATH      = "./chroma_store"
COLLECTION_NAME  = "financial_regulatory_kb"
EMBEDDING_MODEL  = "all-MiniLM-L6-v2"
TOP_K_RESULTS    = 3


def _get_collection():
    """Returns the ChromaDB collection with the SentenceTransformer embedding function."""
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    ef = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name=EMBEDDING_MODEL
    )
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=ef,
        metadata={"hnsw:space": "cosine"},
    )


def get_vector_tool() -> Tool:
    """
    Builds and returns a LangChain Tool that performs semantic similarity
    search over the ChromaDB financial & regulatory knowledge base.
    Returns the top 3 relevant document snippets concatenated as a string.
    """
    collection = _get_collection()

    def search_knowledge_base(query: str) -> str:
        """
        Performs cosine-similarity search and returns the top-K document
        snippets along with their source metadata.
        """
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

            # Format each result with its source metadata
            formatted_snippets = []
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
                formatted_snippets.append(f"{header}\n\n{doc.strip()}")

            return "\n\n" + ("\n\n" + "─" * 60 + "\n\n").join(formatted_snippets)

        except Exception as e:
            return f"Vector tool error: {str(e)}"

    return Tool(
        name="regulatory_knowledge_search",
        func=search_knowledge_base,
        description=(
            "Use this tool for qualitative analysis, regulatory compliance, SEBI guidelines, "
            "and understanding risks or strategy mentioned in earnings transcripts. "
            "Examples: 'What are the SEBI D/E ratio limits for tech companies?', "
            "'What did Aether Technologies say about their AI strategy?', "
            "'What ESG disclosures are required for large-cap companies?', "
            "'Is GreenHorizon eligible for institutional investment?'"
        ),
    )