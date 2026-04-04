import os
import re
import uuid
import logging
import pdfplumber
import chromadb
#from chromadb.utils import embedding_functions
from typing import List, Dict
from rag_app.utils.embeddings import GeminiEmbeddingFunction 

logger = logging.getLogger(__name__)

CHROMA_PATH     = "./chroma_store"
CHROMA_PATH     = os.getenv("CHROMA_PATH", "./chroma_store")
COLLECTION_NAME = "financial_regulatory_kb"

# Chunking config — tuned for regulatory and financial documents
CHUNK_SIZE        = 800   # characters per chunk
CHUNK_OVERLAP     = 150   # overlap so context isn't lost at boundaries
MIN_CHUNK_LENGTH  = 100   # discard chunks shorter than this (headers, page numbers)


def _get_collection():
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    ef     = GeminiEmbeddingFunction() 
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=ef,
        metadata={"hnsw:space": "cosine"},
    )


def _extract_text_from_pdf(file_path: str) -> str:
    """
    Extracts all text from a PDF using pdfplumber.
    Handles multi-column layouts better than PyPDF2.
    """
    full_text = []
    with pdfplumber.open(file_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text()
            if text and text.strip():
                full_text.append(f"[Page {page_num}]\n{text.strip()}")
    return "\n\n".join(full_text)


def _clean_text(text: str) -> str:
    """
    Normalises whitespace and removes common PDF artefacts
    (ligatures, hyphenation, repeated headers/footers).
    """
    # Collapse multiple newlines to double newline (paragraph boundary)
    text = re.sub(r'\n{3,}', '\n\n', text)
    # Remove hyphenated line breaks (common in PDFs)
    text = re.sub(r'-\n([a-z])', r'\1', text)
    # Normalise whitespace within lines
    text = re.sub(r'[ \t]+', ' ', text)
    return text.strip()


def _chunk_text(text: str) -> List[str]:
    """
    Splits text into overlapping chunks of approximately CHUNK_SIZE characters.
    Prefers splitting at paragraph boundaries (\n\n) over mid-sentence splits.
    """
    chunks   = []
    start    = 0
    text_len = len(text)

    while start < text_len:
        end = start + CHUNK_SIZE

        if end >= text_len:
            # Last chunk — take everything remaining
            chunk = text[start:]
        else:
            # Try to split at a paragraph boundary within the last 200 chars
            paragraph_break = text.rfind('\n\n', start, end)
            if paragraph_break != -1 and paragraph_break > start + CHUNK_SIZE // 2:
                end = paragraph_break
            else:
                # Fall back to sentence boundary
                sentence_break = text.rfind('. ', start, end)
                if sentence_break != -1 and sentence_break > start + CHUNK_SIZE // 2:
                    end = sentence_break + 1  # include the period

            chunk = text[start:end]

        chunk = chunk.strip()
        if len(chunk) >= MIN_CHUNK_LENGTH:
            chunks.append(chunk)

        # Advance with overlap so context carries across chunk boundaries
        start = max(start + 1, end - CHUNK_OVERLAP)

    return chunks


def ingest_pdf(
    file_path: str,
    source_name: str,
    category: str,
    document_type: str,
    extra_metadata: Dict = None,
) -> Dict:
    """
    Full pipeline: PDF → text extraction → cleaning → chunking → embedding → ChromaDB.

    Args:
        file_path:      Absolute path to the uploaded PDF file.
        source_name:    Human-readable source label (e.g. "SEBI Circular 2025-001").
        category:       "Regulatory", "Transcript", "ESG", "Research", etc.
        document_type:  Specific type (e.g. "Investment Eligibility", "Earnings Transcript").
        extra_metadata: Any additional key-value pairs to store alongside each chunk.

    Returns:
        A dict summarising the ingestion result.
    """
    logger.info(f"[PDF Processor] Starting ingestion: {file_path}")

    # 1. Extract
    raw_text = _extract_text_from_pdf(file_path)
    if not raw_text.strip():
        raise ValueError("PDF appears to be empty or contains only scanned images (no extractable text).")

    # 2. Clean
    clean_text = _clean_text(raw_text)

    # 3. Chunk
    chunks = _chunk_text(clean_text)
    if not chunks:
        raise ValueError("No valid text chunks produced after processing.")

    logger.info(f"[PDF Processor] Extracted {len(chunks)} chunks from {len(raw_text)} chars.")

    # 4. Build metadata for each chunk
    base_metadata = {
        "source":        source_name,
        "category":      category,
        "document_type": document_type,
        "file_name":     os.path.basename(file_path),
        "total_chunks":  len(chunks),
    }
    if extra_metadata:
        base_metadata.update(extra_metadata)

    # 5. Build chunk records with unique IDs
    # ID format: doc_{uuid}_{chunk_index} — queryable and collision-free
    doc_uuid = str(uuid.uuid4())[:8]
    ids, documents, metadatas = [], [], []

    for i, chunk in enumerate(chunks):
        chunk_id = f"doc_{doc_uuid}_chunk_{i:04d}"
        chunk_metadata = {**base_metadata, "chunk_index": i, "doc_uuid": doc_uuid}
        ids.append(chunk_id)
        documents.append(chunk)
        metadatas.append(chunk_metadata)

    # 6. Upsert into ChromaDB
    collection = _get_collection()
    collection.upsert(ids=ids, documents=documents, metadatas=metadatas)

    logger.info(f"[PDF Processor] Upserted {len(chunks)} chunks. doc_uuid={doc_uuid}")

    return {
        "doc_uuid":       doc_uuid,
        "source_name":    source_name,
        "category":       category,
        "document_type":  document_type,
        "file_name":      os.path.basename(file_path),
        "char_count":     len(clean_text),
        "chunk_count":    len(chunks),
        "chunk_ids":      ids,
    }


def list_documents() -> List[Dict]:
    """
    Returns one record per unique document (grouped by doc_uuid),
    not one record per chunk. Useful for the /api/documents/ endpoint.
    """
    collection = _get_collection()
    total = collection.count()
    if total == 0:
        return []

    # Fetch all metadata — ChromaDB has no native GROUP BY,
    # so we deduplicate in Python by doc_uuid
    results = collection.get(include=["metadatas"])
    metadatas = results.get("metadatas", [])

    seen_uuids = {}
    for meta in metadatas:
        doc_uuid = meta.get("doc_uuid")

        # Handle seeded documents that predate doc_uuid (no uuid field)
        if not doc_uuid:
            key = meta.get("source", "unknown")
            if key not in seen_uuids:
                seen_uuids[key] = {
                    "doc_uuid":      None,
                    "source_name":   meta.get("source", "Unknown"),
                    "category":      meta.get("category", "Unknown"),
                    "document_type": meta.get("document_type", ""),
                    "file_name":     meta.get("file_name", "seeded"),
                    "chunk_count":   1,
                }
            else:
                seen_uuids[key]["chunk_count"] += 1
        else:
            if doc_uuid not in seen_uuids:
                seen_uuids[doc_uuid] = {
                    "doc_uuid":      doc_uuid,
                    "source_name":   meta.get("source", "Unknown"),
                    "category":      meta.get("category", "Unknown"),
                    "document_type": meta.get("document_type", ""),
                    "file_name":     meta.get("file_name", ""),
                    "chunk_count":   meta.get("total_chunks", 1),
                }

    return list(seen_uuids.values())


def delete_document(doc_uuid: str) -> int:
    """
    Deletes all chunks belonging to a document by doc_uuid.
    Returns the number of chunks deleted.
    """
    collection = _get_collection()
    results = collection.get(
        where={"doc_uuid": doc_uuid},
        include=["metadatas"],
    )
    ids_to_delete = results.get("ids", [])
    if ids_to_delete:
        collection.delete(ids=ids_to_delete)
    return len(ids_to_delete)