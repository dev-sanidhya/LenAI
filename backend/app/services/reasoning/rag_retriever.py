from typing import Optional, Any
import chromadb
from chromadb.config import Settings as ChromaSettings
from app.core.config import get_settings
from app.core.logging import get_logger
from app.services.llm.ollama_client import get_ollama_client

logger = get_logger(__name__)
settings = get_settings()

# Cross-encoder loaded lazily on first retrieve() call.
# `sentence_transformers` + torch pull in ~1.5GB of memory at import time,
# which OOM-killed the ingestion worker (which only needs store_chunks /
# delete_chunks_for_document and never re-ranks). Lazy import keeps the
# heavy stack out of the worker process entirely.
_cross_encoder: Optional[Any] = None


def _get_cross_encoder():
    global _cross_encoder
    if _cross_encoder is None:
        from sentence_transformers import CrossEncoder  # lazy: 1.5GB+
        logger.info("loading_cross_encoder", model="cross-encoder/ms-marco-MiniLM-L-6-v2")
        _cross_encoder = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2", max_length=512)
    return _cross_encoder


def _get_chroma_client() -> chromadb.HttpClient:
    return chromadb.HttpClient(
        host=settings.chroma_host,
        port=settings.chroma_port,
        settings=ChromaSettings(anonymized_telemetry=False),
    )


def _build_where_filter(tenant_id: str, document_ids: Optional[list[str]] = None) -> dict:
    if not document_ids:
        return {"tenant_id": tenant_id}
    if len(document_ids) == 1:
        return {"$and": [{"tenant_id": tenant_id}, {"document_id": document_ids[0]}]}
    return {"$and": [{"tenant_id": tenant_id}, {"document_id": {"$in": document_ids}}]}


async def store_chunks(chunks: list[dict]) -> None:
    """Store embedded chunks in ChromaDB. Idempotent by chunk ID."""
    if not chunks:
        return

    ollama = get_ollama_client()
    client = _get_chroma_client()
    collection = client.get_or_create_collection(
        name=settings.chroma_collection_documents,
        metadata={"hnsw:space": "cosine"},
    )

    ids = [c["id"] for c in chunks]
    texts = [c["text"] for c in chunks]
    metadatas = [
        {
            "document_id": c["document_id"],
            "tenant_id": c["tenant_id"],
            "page": c.get("page", 0),
            "type": c.get("type", "text"),
            "chunk_index": c.get("chunk_index", 0),
            "table_index": c.get("table_index", -1),
            "embedding_model": settings.ollama_embed_model,
        }
        for c in chunks
    ]

    # Embed in batches of 10 to avoid timeouts
    embeddings = []
    batch_size = 10
    for i in range(0, len(texts), batch_size):
        batch = texts[i: i + batch_size]
        batch_embs = await ollama.embed_batch(batch)
        embeddings.extend(batch_embs)

    # Upsert (existing IDs are overwritten - idempotent)
    collection.upsert(ids=ids, embeddings=embeddings, documents=texts, metadatas=metadatas)
    logger.info("chunks_stored", count=len(chunks))


async def delete_chunks_for_document(document_id: str) -> None:
    """Remove all chunks for a document (used when re-uploading)."""
    client = _get_chroma_client()
    collection = client.get_or_create_collection(settings.chroma_collection_documents)
    collection.delete(where={"document_id": document_id})


async def retrieve(
    query: str,
    tenant_id: str,
    document_ids: Optional[list[str]] = None,
    top_k_retrieve: int = None,
    top_k_rerank: int = None,
) -> list[dict]:
    """
    Two-stage retrieval:
    1. Semantic search in ChromaDB (top_k_retrieve candidates)
    2. Cross-encoder re-ranking (top_k_rerank final results)
    """
    top_k_retrieve = top_k_retrieve or settings.rag_top_k_retrieve
    top_k_rerank = top_k_rerank or settings.rag_top_k_rerank

    ollama = get_ollama_client()
    query_embedding = await ollama.embed(query)

    client = _get_chroma_client()
    collection = client.get_or_create_collection(settings.chroma_collection_documents)

    # Build where filter - always scope to tenant
    where = _build_where_filter(tenant_id, document_ids)

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=min(top_k_retrieve, collection.count() or 1),
        where=where if collection.count() > 0 else None,
        include=["documents", "metadatas", "distances"],
    )

    if not results["documents"] or not results["documents"][0]:
        return []

    docs = results["documents"][0]
    metas = results["metadatas"][0]
    distances = results["distances"][0]

    candidates = [
        {
            "text": doc,
            "metadata": meta,
            "similarity_score": round(1 - dist, 4),
        }
        for doc, meta, dist in zip(docs, metas, distances)
    ]

    if len(candidates) <= 1:
        return candidates[:top_k_rerank]

    # Cross-encoder re-ranking
    cross_encoder = _get_cross_encoder()
    pairs = [[query, c["text"]] for c in candidates]
    scores = cross_encoder.predict(pairs)

    for i, candidate in enumerate(candidates):
        candidate["rerank_score"] = float(scores[i])

    candidates.sort(key=lambda x: x["rerank_score"], reverse=True)
    top = candidates[:top_k_rerank]

    logger.info("retrieval_done", query_len=len(query), candidates=len(candidates), returned=len(top))
    return top
