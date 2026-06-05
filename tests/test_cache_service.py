"""
缓存服务测试用例

覆盖查询归一化对 Embedding / Rerank 缓存命中的影响。
"""

from app.services.cache_service import CacheService


def test_embedding_cache_normalizes_punctuation_width_and_spacing():
    """
    场景：同一查询存在标点、全角字符和空格差异

    预期：
    - 写入一次缓存后，变体查询能命中同一 Embedding 缓存
    """
    cache = CacheService()
    embedding = [0.1, 0.2, 0.3]

    cache.set_embedding("人脸识别门禁，访客预约！", embedding)

    assert cache.get_embedding("  人脸门禁  访客预约  ") == embedding


def test_cache_stats_track_hits_misses_sets_and_reset():
    """
    场景：缓存有写入、命中、未命中和清理操作

    预期：
    - stats 返回命中率和计数
    - clear_all 同时重置统计
    """
    cache = CacheService()

    cache.set_embedding("登录", [0.1])
    assert cache.get_embedding("登录") == [0.1]
    assert cache.get_embedding("不存在") is None

    stats = cache.get_stats()["embedding_cache"]
    assert stats["sets"] == 1
    assert stats["hits"] == 1
    assert stats["misses"] == 1
    assert stats["hit_rate"] == 0.5

    cache.clear_all()

    reset_stats = cache.get_stats()["embedding_cache"]
    assert reset_stats["sets"] == 0
    assert reset_stats["hits"] == 0
    assert reset_stats["misses"] == 0
    assert reset_stats["hit_rate"] == 0.0


def test_rerank_cache_normalizes_synonyms_for_query_key():
    """
    场景：Rerank 查询使用业务同义词表达

    预期：
    - 车辆道闸 / 车闸 等价查询命中同一缓存
    """
    cache = CacheService()
    doc_ids = ["doc-1", "doc-2"]
    rerank_results = [{"index": 0, "relevance_score": 0.92}]

    cache.set_rerank("车辆道闸异常怎么处理？", doc_ids, rerank_results)

    assert cache.get_rerank("车闸异常怎么处理", doc_ids) == rerank_results


def test_rerank_cache_is_order_sensitive_because_result_indexes_reference_candidates():
    """
    场景：同一批候选文档顺序发生变化

    预期：
    - Rerank 缓存不命中，避免 cached index 指向错误文档
    """
    cache = CacheService()
    doc_ids = ["doc-1", "doc-2"]

    cache.set_rerank("登录功能", doc_ids, [{"index": 0, "relevance_score": 0.92}])

    assert cache.get_rerank("登录功能", list(reversed(doc_ids))) is None


def test_rerank_cache_is_content_sensitive_when_doc_ids_stay_the_same():
    """
    场景：候选文档 id 不变，但文档内容发生变化

    预期：
    - Rerank 缓存不命中，避免复用旧内容的相关性分数
    """
    cache = CacheService()
    doc_ids = ["doc-1", "doc-2"]
    original_fingerprints = ["登录功能", "注册功能"]
    changed_fingerprints = ["登录异常排查", "注册功能"]

    cache.set_rerank(
        "登录功能",
        doc_ids,
        [{"index": 0, "relevance_score": 0.92}],
        doc_fingerprints=original_fingerprints,
    )

    assert cache.get_rerank(
        "登录功能",
        doc_ids,
        doc_fingerprints=changed_fingerprints,
    ) is None


def test_rerank_cache_can_be_bypassed_after_bad_feedback():
    """
    场景：用户反馈某个查询排序不满意

    预期：
    - Rerank 缓存对该查询短期绕过，不再命中旧排序
    - Embedding 缓存不受影响
    """
    cache = CacheService()
    doc_ids = ["doc-1", "doc-2"]
    rerank_results = [{"index": 0, "relevance_score": 0.92}]
    embedding = [0.1, 0.2]

    cache.set_embedding("小程序上线后白屏", embedding)
    cache.set_rerank("小程序上线后白屏", doc_ids, rerank_results)
    cache.bypass_rerank_cache("小程序上线后白屏", reason="bad_feedback")

    assert cache.get_rerank("小程序上线后白屏", doc_ids) is None
    assert cache.get_embedding("小程序上线后白屏") == embedding
    stats = cache.get_stats()["rerank_cache"]
    assert stats["bypassed_queries"] == 1
    assert stats["bypasses"] == 1


def test_rerank_cache_can_be_invalidated_by_request_id():
    """
    场景：一次请求写入了 Rerank 缓存，用户随后按 request_id 撤销

    预期：
    - 只删除该 request 关联的 Rerank 缓存
    - 同时对 query 建立短期绕过
    """
    cache = CacheService()
    doc_ids = ["doc-1"]
    doc_fingerprints = ["小程序上线后白屏排查"]

    cache.set_rerank(
        "小程序上线后白屏",
        doc_ids,
        [{"index": 0, "score": 0.9}],
        doc_fingerprints=doc_fingerprints,
        request_id="req-001",
    )
    assert cache.get_rerank("小程序上线后白屏", doc_ids, doc_fingerprints) == [{"index": 0, "score": 0.9}]

    result = cache.invalidate_rerank_by_request_id("req-001")

    assert result == {
        "request_id": "req-001",
        "invalidated": 1,
        "bypassed_queries": 1,
    }
    assert cache.get_rerank("小程序上线后白屏", doc_ids, doc_fingerprints) is None
    assert cache.get_stats()["rerank_cache"]["lineage_size"] == 0


def test_invalidate_unknown_request_id_is_noop():
    """未知 request_id 撤销不影响缓存。"""
    cache = CacheService()

    result = cache.invalidate_rerank_by_request_id("missing")

    assert result == {
        "request_id": "missing",
        "invalidated": 0,
        "bypassed_queries": 0,
    }
