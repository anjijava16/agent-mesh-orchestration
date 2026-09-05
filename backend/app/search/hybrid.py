"""Hybrid retrieval over OpenSearch.

We run BM25 and kNN as two independent queries and fuse them with Reciprocal
Rank Fusion. RRF was chosen over score normalisation on purpose: BM25 scores are
unbounded and corpus-dependent, cosine scores are not, and normalising the two
into a single scale produces a weighting that quietly drifts as the corpus grows.
RRF only looks at ranks, so it is stable.

An optional cross-encoder rerank pass runs on the fused head. It is off by
default because it doubles p95 latency; turn it on per-request.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from app.config import settings
from app.core.errors import UpstreamError
from app.core.logging import get_logger
from app.core.resilience import OPENSEARCH_BREAKER, with_resilience
from app.search.client import get_opensearch

log = get_logger(__name__)


@dataclass
class SearchHit:
    chunk_id: str
    document_id: str
    filename: str
    content: str
    page: int | None = None
    score: float = 0.0
    bm25_rank: int | None = None
    knn_rank: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "document_id": self.document_id,
            "filename": self.filename,
            "content": self.content,
            "page": self.page,
            "score": round(self.score, 6),
            "bm25_rank": self.bm25_rank,
            "knn_rank": self.knn_rank,
            "metadata": self.metadata,
        }

    def citation(self) -> str:
        loc = f" p.{self.page}" if self.page else ""
        return f"{self.filename}{loc}"


def _filters(user_id: str | None, document_ids: Sequence[str] | None, tags: Sequence[str] | None) -> list[dict]:
    clauses: list[dict] = []
    if user_id:
        clauses.append({"term": {"user_id": user_id}})
    if document_ids:
        clauses.append({"terms": {"document_id": list(document_ids)}})
    if tags:
        clauses.append({"terms": {"tags": list(tags)}})
    return clauses


@with_resilience(breaker=OPENSEARCH_BREAKER, timeout=settings.resilience.search_timeout_seconds, label="os.bm25")
async def _bm25(index: str, query: str, size: int, filters: list[dict]) -> list[dict]:
    body = {
        "size": size,
        "_source": {"excludes": ["embedding"]},
        "query": {
            "bool": {
                "must": [
                    {
                        "multi_match": {
                            "query": query,
                            "fields": ["content^1.0", "title^2.0", "filename.text^1.5"],
                            "type": "best_fields",
                            "operator": "or",
                            "minimum_should_match": "30%",
                        }
                    }
                ],
                "filter": filters,
            }
        },
    }
    res = await get_opensearch().search(index=index, body=body)
    return res["hits"]["hits"]


@with_resilience(breaker=OPENSEARCH_BREAKER, timeout=settings.resilience.search_timeout_seconds, label="os.knn")
async def _knn(index: str, vector: list[float], size: int, filters: list[dict]) -> list[dict]:
    # Lucene HNSW supports a filter clause inside the knn query, which is what
    # keeps tenant isolation from degenerating into post-filtering.
    knn_clause: dict[str, Any] = {"embedding": {"vector": vector, "k": size}}
    if filters:
        knn_clause["embedding"]["filter"] = {"bool": {"filter": filters}}
    body = {"size": size, "_source": {"excludes": ["embedding"]}, "query": {"knn": knn_clause}}
    res = await get_opensearch().search(index=index, body=body)
    return res["hits"]["hits"]


def reciprocal_rank_fusion(
    bm25_hits: list[dict], knn_hits: list[dict], *, k: int = 60, top_k: int = 8
) -> list[SearchHit]:
    scores: dict[str, float] = {}
    payloads: dict[str, dict] = {}
    ranks: dict[str, dict[str, int]] = {}

    for label, hits in (("bm25", bm25_hits), ("knn", knn_hits)):
        for rank, hit in enumerate(hits, start=1):
            doc_id = hit["_id"]
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank)
            payloads.setdefault(doc_id, hit["_source"])
            ranks.setdefault(doc_id, {})[label] = rank

    ordered = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:top_k]
    out: list[SearchHit] = []
    for doc_id, score in ordered:
        src = payloads[doc_id]
        out.append(
            SearchHit(
                chunk_id=src.get("chunk_id", doc_id),
                document_id=src.get("document_id", ""),
                filename=src.get("filename", "unknown"),
                content=src.get("content", ""),
                page=src.get("page"),
                score=score,
                bm25_rank=ranks[doc_id].get("bm25"),
                knn_rank=ranks[doc_id].get("knn"),
                metadata=src.get("metadata", {}),
            )
        )
    return out


async def hybrid_search(
    query: str,
    *,
    embedder: Any,
    user_id: str | None = None,
    document_ids: Sequence[str] | None = None,
    tags: Sequence[str] | None = None,
    top_k: int | None = None,
    index: str | None = None,
    rerank: bool = False,
) -> list[SearchHit]:
    cfg = settings.opensearch
    index = index or cfg.documents_index
    top_k = top_k or cfg.final_top_k
    filters = _filters(user_id, document_ids, tags)

    try:
        vector = await embedder.embed_query(query)
    except Exception as exc:
        # Degrade to lexical-only rather than failing the whole retrieval.
        log.warning("embedding_failed_lexical_fallback", error=str(exc)[:300])
        vector = None

    import asyncio

    tasks = [_bm25(index, query, cfg.bm25_top_k, filters)]
    if vector is not None:
        tasks.append(_knn(index, vector, cfg.knn_top_k, filters))

    results = await asyncio.gather(*tasks, return_exceptions=True)
    lexical = results[0] if not isinstance(results[0], BaseException) else []
    semantic = results[1] if len(results) > 1 and not isinstance(results[1], BaseException) else []

    if isinstance(results[0], BaseException) and not semantic:
        raise UpstreamError("Both retrieval legs failed", details={"error": str(results[0])[:300]})

    fused = reciprocal_rank_fusion(list(lexical), list(semantic), k=cfg.rrf_k, top_k=top_k * (3 if rerank else 1))

    if rerank and fused:
        fused = await _rerank(query, fused, top_k)

    log.info(
        "hybrid_search",
        query_len=len(query),
        bm25_hits=len(lexical),
        knn_hits=len(semantic),
        returned=len(fused[:top_k]),
        reranked=rerank,
    )
    return fused[:top_k]


async def _rerank(query: str, hits: list[SearchHit], top_k: int) -> list[SearchHit]:
    """Cross-encoder rerank. Falls back to the fused order if the model is absent."""
    try:
        from sentence_transformers import CrossEncoder  # type: ignore

        global _cross_encoder
        try:
            model = _cross_encoder  # type: ignore[name-defined]
        except NameError:
            model = _cross_encoder = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")  # type: ignore

        import asyncio

        pairs = [(query, h.content[:2000]) for h in hits]
        scores = await asyncio.to_thread(model.predict, pairs)
        for hit, score in zip(hits, scores, strict=False):
            hit.score = float(score)
        hits.sort(key=lambda h: h.score, reverse=True)
    except Exception as exc:
        log.warning("rerank_unavailable", error=str(exc)[:200])
    return hits[:top_k]
