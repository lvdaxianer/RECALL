"""
Answer cache service tests.

Author: lvdaxianerplus
Date: 2026-06-04
"""

from app.services.answer_cache_service import AnswerCacheService
from app.services.knowledge_base_repository import KnowledgeBaseRepository


def test_answer_cache_reuses_normalized_question_with_kb_revision(tmp_path):
    """归一化后的相同问题在同一知识库发版版本下复用答案。"""
    repository = KnowledgeBaseRepository(str(tmp_path / "kb.sqlite"))
    kb = repository.create_knowledge_base("Java", "notes", "u1")
    repository.update_knowledge_base_status(kb["id"], "published")
    service = AnswerCacheService(repository, ttl_seconds=3600)

    service.set(
        input_text="JMM 的访问策略是啥？",
        knowledge_base_ids=[kb["id"]],
        top_k=5,
        answer="JMM 通过主内存和工作内存定义访问规则。",
        citations=[{"chunk_id": "chunk-1", "title": "JMM"}],
        trace=[{"stage": "candidate_scoring"}],
        request_id="req-001",
    )

    cached = service.get(
        input_text="jmm 访问策略是啥呢",
        knowledge_base_ids=[kb["id"]],
        top_k=5,
    )

    assert cached is not None
    assert cached["answer"] == "JMM 通过主内存和工作内存定义访问规则。"
    assert cached["normalized_query"] == "jmm 访问策略是啥"
    assert cached["hit_count"] == 1


def test_answer_cache_invalidates_when_kb_revision_changes(tmp_path):
    """知识库重新发版后不复用旧答案缓存。"""
    repository = KnowledgeBaseRepository(str(tmp_path / "kb.sqlite"))
    kb = repository.create_knowledge_base("Java", "notes", "u1")
    repository.update_knowledge_base_status(kb["id"], "published")
    service = AnswerCacheService(repository, ttl_seconds=3600)

    service.set(
        input_text="JMM 的访问策略是啥？",
        knowledge_base_ids=[kb["id"]],
        top_k=5,
        answer="旧答案",
        citations=[],
        trace=[],
        request_id="req-001",
    )
    repository.update_knowledge_base_status(kb["id"], "changed")
    repository.update_knowledge_base_status(kb["id"], "published")

    assert service.get("JMM 的访问策略是啥", [kb["id"]], 5) is None


def test_answer_feedback_updates_trust_or_deletes_cache(tmp_path):
    """点赞提升信任权重，点踩删除缓存并登记短期绕过。"""
    repository = KnowledgeBaseRepository(str(tmp_path / "kb.sqlite"))
    kb = repository.create_knowledge_base("Java", "notes", "u1")
    repository.update_knowledge_base_status(kb["id"], "published")
    service = AnswerCacheService(repository, ttl_seconds=3600)
    service.set(
        input_text="JMM 的访问策略是啥？",
        knowledge_base_ids=[kb["id"]],
        top_k=5,
        answer="JMM 答案",
        citations=[],
        trace=[],
        request_id="req-001",
    )

    liked = service.record_feedback("req-001", "like", user_id="default")
    assert liked["trust_score"] == 1
    assert service.get("JMM 访问策略是啥", [kb["id"]], 5)["trust_score"] == 1

    disliked = service.record_feedback("req-001", "dislike", user_id="default")
    assert disliked["deleted"] is True
    assert service.get("JMM 访问策略是啥", [kb["id"]], 5) is None
    assert service.is_bypassed("JMM 的访问策略是啥？", [kb["id"]], 5) is True


def test_answer_feedback_deletes_cache_after_cache_hit_request_id_changes(tmp_path):
    """缓存命中会产生新的 request_id，点踩该回答仍应删除原缓存。"""
    repository = KnowledgeBaseRepository(str(tmp_path / "kb.sqlite"))
    kb = repository.create_knowledge_base("Java", "notes", "u1")
    repository.update_knowledge_base_status(kb["id"], "published")
    service = AnswerCacheService(repository, ttl_seconds=3600)
    cached = service.set(
        input_text="JMM 的访问策略是啥？",
        knowledge_base_ids=[kb["id"]],
        top_k=5,
        answer="JMM 答案",
        citations=[],
        trace=[],
        request_id="req-original",
    )

    service.bind_request_id(cached["cache_key"], "req-cache-hit")
    disliked = service.record_feedback("req-cache-hit", "dislike", user_id="default")

    assert disliked["deleted"] is True
    assert service.get("JMM 访问策略是啥", [kb["id"]], 5) is None
    assert service.is_bypassed("JMM 访问策略是啥", [kb["id"]], 5) is True


def test_answer_cache_lists_and_deletes_records(tmp_path):
    """答案缓存支持管理台列表和手动删除。"""
    repository = KnowledgeBaseRepository(str(tmp_path / "kb.sqlite"))
    kb = repository.create_knowledge_base("Java", "notes", "u1")
    repository.update_knowledge_base_status(kb["id"], "published")
    service = AnswerCacheService(repository, ttl_seconds=3600)
    cached = service.set(
        input_text="JMM 的访问策略是啥？",
        knowledge_base_ids=[kb["id"]],
        top_k=5,
        answer="JMM 答案",
        citations=[{"chunk_id": "chunk-1", "title": "JMM"}],
        trace=[],
        request_id="req-001",
    )

    records = service.list_records()
    deleted = service.delete(cached["cache_key"])

    assert records[0]["cache_key"] == cached["cache_key"]
    assert records[0]["answer_preview"] == "JMM 答案"
    assert records[0]["citation_count"] == 1
    assert deleted["deleted"] is True
    assert service.list_records() == []


def test_answer_cache_key_uses_synonym_normalization(tmp_path):
    """同义问法应生成同一答案缓存 key，提升缓存命中率。"""
    repository = KnowledgeBaseRepository(str(tmp_path / "kb.sqlite"))
    kb = repository.create_knowledge_base("Python", "notes", "u1")
    repository.create_synonym_group(kb["id"], "职责", ["能负责啥", "承担什么职责"], "u1")
    service = AnswerCacheService(repository, ttl_seconds=3600)

    key_a, normalized_a, _ = service.build_cache_key("装饰器能负责啥", [kb["id"]], 5)
    key_b, normalized_b, _ = service.build_cache_key("装饰器承担什么职责", [kb["id"]], 5)

    assert normalized_a == "装饰器职责"
    assert normalized_b == "装饰器职责"
    assert key_a == key_b


def test_answer_cache_get_checks_base_builtin_and_synonym_variants(tmp_path):
    """答案缓存读取时一次覆盖基础、硬编码和 DB 同义词归一化 key。"""
    repo = KnowledgeBaseRepository(str(tmp_path / "kb.sqlite"))
    kb = repo.create_knowledge_base("KB", "desc", "u1")
    repo.create_synonym_group(kb["id"], "Java 内存模型", ["JMM"], "u1")
    cache = AnswerCacheService(repo)

    stored = cache.set(
        input_text="Java 内存模型 访问策略",
        knowledge_base_ids=[kb["id"]],
        top_k=5,
        answer="cached answer",
        citations=[],
        trace=[],
        request_id="req-store",
        temperature=0.2,
    )

    hit = cache.get("JMM 访问策略", [kb["id"]], 5, temperature=0.2)

    assert hit is not None
    assert hit["cache_key"] == stored["cache_key"]


def test_answer_cache_key_includes_temperature(tmp_path):
    """不同 temperature 不能复用同一个答案缓存。"""
    repo = KnowledgeBaseRepository(str(tmp_path / "kb.sqlite"))
    kb = repo.create_knowledge_base("KB", "desc", "u1")
    cache = AnswerCacheService(repo)

    low = cache.build_cache_key("同一个问题", [kb["id"]], 5, temperature=0.2)[0]
    high = cache.build_cache_key("同一个问题", [kb["id"]], 5, temperature=0.7)[0]

    assert low != high
