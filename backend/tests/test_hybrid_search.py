from __future__ import annotations

from app.search.hybrid import reciprocal_rank_fusion


def _hit(doc_id: str, filename: str = "a.pdf") -> dict:
    return {"_id": doc_id, "_source": {"chunk_id": doc_id, "document_id": "d1", "filename": filename,
                                       "content": f"content {doc_id}", "page": 1}}


def test_rrf_rewards_documents_found_by_both_legs():
    bm25 = [_hit("a"), _hit("b"), _hit("c")]
    knn = [_hit("c"), _hit("d"), _hit("a")]

    fused = reciprocal_rank_fusion(bm25, knn, k=60, top_k=4)
    ids = [h.chunk_id for h in fused]

    # 'a' is rank 1 lexically and rank 3 semantically; 'c' is 3 and 1.
    # Both beat anything that appeared in only one list.
    assert set(ids[:2]) == {"a", "c"}
    assert fused[0].bm25_rank is not None and fused[0].knn_rank is not None


def test_rrf_handles_one_empty_leg():
    fused = reciprocal_rank_fusion([_hit("a"), _hit("b")], [], k=60, top_k=5)
    assert [h.chunk_id for h in fused] == ["a", "b"]
    assert fused[0].knn_rank is None


def test_rrf_respects_top_k():
    hits = [_hit(str(i)) for i in range(20)]
    assert len(reciprocal_rank_fusion(hits, hits, top_k=5)) == 5
