"""
轻量图谱检索服务测试

@author lvdaxianerplus
@date 2026-05-31
"""

from app.services.graph_retrieval_service import GraphRetrievalService


def test_graph_search_matches_entity_name():
    """查询命中实体名称时返回对应文档"""
    service = GraphRetrievalService()
    service.index_document(
        doc_id="skill-jwt",
        description="JWT 登录认证能力",
        metadata={"type": "skill", "id": "skill-jwt"},
        features={
            "category": "认证",
            "tags": ["登录"],
            "entities": [{"name": "JWT", "type": "技术组件"}],
            "relations": []
        }
    )

    results = service.search("JWT 怎么登录", search_type="skill", top_k=5)

    assert results[0]["id"] == "skill-jwt"
    assert results[0]["score"] > 0
    assert results[0]["_graph_match_type"] == "entity"


def test_graph_search_expands_one_hop_relation():
    """查询关系目标时可通过一跳关系召回源实体文档"""
    service = GraphRetrievalService()
    service.index_document(
        doc_id="skill-jwt",
        description="JWT 登录认证能力",
        metadata={"type": "skill", "id": "skill-jwt"},
        features={
            "category": "认证",
            "tags": ["登录"],
            "entities": [{"name": "JWT", "type": "技术组件"}],
            "relations": [{"source": "JWT", "target": "登录认证", "relation": "用于"}]
        }
    )

    results = service.search("登录认证", search_type="skill", top_k=5)

    assert results[0]["id"] == "skill-jwt"
    assert results[0]["_graph_match_type"] == "relation"


def test_graph_search_dedupes_documents_and_filters_type():
    """图检索按文档去重，并按资源类型过滤"""
    service = GraphRetrievalService()
    features = {
        "category": "认证",
        "tags": ["登录"],
        "entities": [{"name": "JWT", "type": "技术组件"}],
        "relations": [{"source": "JWT", "target": "JWT", "relation": "相关"}]
    }
    service.index_document("skill-jwt", "JWT 登录认证能力", {"type": "skill", "id": "skill-jwt"}, features)
    service.index_document("asset-jwt", "JWT 图标素材", {"type": "asset", "id": "asset-jwt"}, features)

    results = service.search("JWT", search_type="skill", top_k=5)

    assert [item["id"] for item in results] == ["skill-jwt"]


def test_delete_document_removes_document_from_graph_indexes():
    """删除文档时同步清理实体和关系倒排索引"""
    service = GraphRetrievalService()
    service.index_document(
        doc_id="skill-jwt",
        description="JWT 登录认证能力",
        metadata={"type": "skill", "id": "skill-jwt"},
        features={
            "category": "认证",
            "tags": ["登录"],
            "entities": [{"name": "JWT", "type": "技术组件"}],
            "relations": [{"source": "JWT", "target": "登录认证", "relation": "用于"}]
        }
    )

    deleted = service.delete_document("skill-jwt")

    assert deleted is True
    assert service.search("JWT 登录认证", search_type="skill", top_k=5) == []
    assert service.stats() == {
        "document_count": 0,
        "entity_count": 0,
        "relation_term_count": 0
    }


def test_reindex_document_replaces_old_graph_terms():
    """重复索引同一文档时清理旧实体和关系词项"""
    service = GraphRetrievalService()
    service.index_document(
        doc_id="skill-auth",
        description="JWT 登录认证能力",
        metadata={"type": "skill", "id": "skill-auth"},
        features={
            "entities": [{"name": "JWT", "type": "技术组件"}],
            "relations": [{"source": "JWT", "target": "登录认证", "relation": "用于"}]
        }
    )
    service.index_document(
        doc_id="skill-auth",
        description="OAuth2 授权能力",
        metadata={"type": "skill", "id": "skill-auth"},
        features={
            "entities": [{"name": "OAuth2", "type": "技术组件"}],
            "relations": [{"source": "OAuth2", "target": "授权", "relation": "用于"}]
        }
    )

    assert service.search("JWT 登录认证", search_type="skill", top_k=5) == []
    assert service.search("OAuth2 授权", search_type="skill", top_k=5)[0]["id"] == "skill-auth"
    assert service.stats() == {
        "document_count": 1,
        "entity_count": 1,
        "relation_term_count": 3
    }


def test_rebuild_replaces_existing_graph_index():
    """重建图索引时清空旧数据并写入新数据"""
    service = GraphRetrievalService()
    service.index_document(
        doc_id="old-doc",
        description="旧登录能力",
        metadata={"type": "skill", "id": "old-doc"},
        features={
            "entities": [{"name": "旧系统"}],
            "relations": []
        }
    )

    stats = service.rebuild([
        {
            "id": "new-doc",
            "description": "JWT 登录认证能力",
            "metadata": {"type": "skill", "id": "new-doc"},
            "features": {
                "entities": [{"name": "JWT"}],
                "relations": [{"source": "JWT", "target": "登录认证", "relation": "用于"}]
            }
        }
    ])

    assert stats["document_count"] == 1
    assert service.search("旧系统", search_type="skill", top_k=5) == []
    assert service.search("JWT", search_type="skill", top_k=5)[0]["id"] == "new-doc"


def test_graph_stats_and_explain_show_matches():
    """图索引统计和解释可展示命中原因"""
    service = GraphRetrievalService()
    service.index_document(
        doc_id="skill-jwt",
        description="JWT 登录认证能力",
        metadata={"type": "skill", "id": "skill-jwt"},
        features={
            "category": "认证",
            "tags": ["登录"],
            "entities": [{"name": "JWT", "type": "技术组件"}],
            "relations": [{"source": "JWT", "target": "登录认证", "relation": "用于"}]
        }
    )

    stats = service.stats()
    explain = service.explain("JWT 登录认证", search_type="skill", top_k=5)

    assert stats["document_count"] == 1
    assert stats["entity_count"] == 1
    assert stats["relation_term_count"] == 3
    assert explain["query"] == "JWT 登录认证"
    assert explain["result_count"] == 1
    assert explain["matches"][0]["id"] == "skill-jwt"
    assert "jwt" in explain["matched_entities"]
    assert "登录认证" in explain["matched_relation_terms"]
