"""
同义词归一化服务测试

Author: lvdaxianerplus
Date: 2026-06-05
"""

from app.services.knowledge_base_repository import KnowledgeBaseRepository
from app.services.synonym_service import SynonymService


def test_compiled_synonym_index_uses_longest_match():
    """同义词归一化使用最长匹配，避免短词先替换破坏长词。"""
    from app.services.synonym_index_service import CompiledSynonymIndex

    index = CompiledSynonymIndex.from_groups([
        {"canonical": "Java 内存模型", "terms": ["JMM", "Java Memory Model"]},
        {"canonical": "访问策略", "terms": ["访问规则", "访问"]},
    ])

    assert index.normalize("jmm 的访问规则是啥") == "Java 内存模型 的访问策略是啥"


def test_compiled_synonym_index_can_include_builtin_synonyms():
    """硬编码兜底同义词也应进入同一个快速索引。"""
    from app.services.synonym_index_service import CompiledSynonymIndex

    index = CompiledSynonymIndex.from_groups([], include_builtin=True)

    assert index.normalize("装饰器干啥用的") == "装饰器作用"


def test_synonym_service_normalizes_global_terms(tmp_path):
    """全局同义词组将口语查询归一到 canonical。"""
    repo = KnowledgeBaseRepository(str(tmp_path / "kb.sqlite"))
    repo.create_synonym_group(None, "作用", ["干啥用的", "有什么作用"], "u1")
    service = SynonymService(repo)

    assert service.normalize_query("装饰器干啥用的", []) == "装饰器作用"
    assert service.normalize_query("装饰器有什么作用", []) == "装饰器作用"


def test_synonym_service_applies_kb_groups_before_global_groups(tmp_path):
    """知识库 scoped 同义词优先于全局同义词。"""
    repo = KnowledgeBaseRepository(str(tmp_path / "kb.sqlite"))
    kb = repo.create_knowledge_base("KB", "desc", "u1")
    repo.create_synonym_group(None, "全局作用", ["干啥用的"], "u1")
    repo.create_synonym_group(kb["id"], "局部作用", ["干啥用的"], "u1")
    service = SynonymService(repo)

    assert service.normalize_query("模块干啥用的", [kb["id"]]) == "模块局部作用"


def test_synonym_service_trims_and_deduplicates_terms(tmp_path):
    """创建同义词组时会裁剪空白并去重。"""
    repo = KnowledgeBaseRepository(str(tmp_path / "kb.sqlite"))
    group = repo.create_synonym_group(None, "作用", [" 干啥用的 ", "干啥用的", " "], "u1")

    assert group["terms"] == ["干啥用的"]


def test_synonym_service_ignores_disabled_groups_but_keeps_builtin_fallback(tmp_path):
    """禁用同义词组不参与 DB 归一化，但硬编码兜底仍可生效。"""
    repo = KnowledgeBaseRepository(str(tmp_path / "kb.sqlite"))
    group = repo.create_synonym_group(None, "作用", ["干啥用的"], "u1")
    repo.update_synonym_group(group["id"], {"enabled": False})
    service = SynonymService(repo)

    assert service.normalize_query("装饰器干啥用的", []) == "装饰器作用"


def test_synonym_service_keeps_empty_query_empty(tmp_path):
    """空查询归一化后仍为空。"""
    repo = KnowledgeBaseRepository(str(tmp_path / "kb.sqlite"))
    service = SynonymService(repo)

    assert service.normalize_query("", []) == ""


def test_synonym_service_reuses_compiled_index_until_revision_changes(tmp_path):
    """同一知识库范围内同义词索引应复用，避免每次请求重新查库和编译。"""
    repo = KnowledgeBaseRepository(str(tmp_path / "kb.sqlite"))
    kb = repo.create_knowledge_base("KB", "desc", "u1")
    repo.create_synonym_group(kb["id"], "Java 内存模型", ["JMM"], "u1")
    service = SynonymService(repo)

    assert service.normalize_query("JMM 是什么", [kb["id"]]) == "Java 内存模型 是什么"
    first_cache_key = next(iter(service._index_cache.keys()))
    assert service.normalize_query("JMM 作用", [kb["id"]]) == "Java 内存模型 作用"
    assert next(iter(service._index_cache.keys())) == first_cache_key

    repo.create_synonym_group(kb["id"], "访问策略", ["访问规则"], "u1")
    assert service.normalize_query("访问规则", [kb["id"]]) == "访问策略"
    assert len(service._index_cache) >= 2


def test_synonym_service_replaces_longest_term_first(tmp_path):
    """同义词匹配优先替换最长词，避免短词抢先截断。"""
    repo = KnowledgeBaseRepository(str(tmp_path / "kb.sqlite"))
    repo.create_synonym_group(None, "作用", ["用", "有什么作用"], "u1")
    service = SynonymService(repo)

    assert service.normalize_query("装饰器有什么作用", []) == "装饰器作用"
