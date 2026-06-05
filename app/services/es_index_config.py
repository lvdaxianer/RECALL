"""
Elasticsearch 索引配置构造模块

集中维护 IK 与 standard 降级索引配置。

@author lvdaxianerplus
@date 2026-06-01
"""


def build_index_body_with_ik() -> dict:
    """
    构建使用 IK 分词器的索引配置

    @returns ES 索引配置
    """
    ragflow_fields = _ragflow_compatible_fields(
        analyzer="ik_max_word",
        search_analyzer="ik_smart_synonym"
    )
    return {
        "settings": {
            "number_of_shards": 1,
            "number_of_replicas": 0,
            "analysis": {
                "filter": {
                    "synonym_filter": {
                        "type": "synonym",
                        "synonyms_path": "synonyms.txt",
                        "updateable": True
                    }
                },
                "analyzer": {
                    "ik_max_word": {
                        "type": "custom",
                        "tokenizer": "ik_max_word",
                        "filter": ["lowercase"]
                    },
                    "ik_smart_synonym": {
                        "type": "custom",
                        "tokenizer": "ik_smart",
                        "filter": ["lowercase", "synonym_filter"]
                    },
                    "ik_max_word_synonym": {
                        "type": "custom",
                        "tokenizer": "ik_max_word",
                        "filter": ["lowercase", "synonym_filter"]
                    }
                }
            }
        },
        "mappings": {
            "properties": {
                "id": {"type": "keyword"},
                "description": {
                    "type": "text",
                    "analyzer": "ik_max_word",
                    "search_analyzer": "ik_smart_synonym"
                },
                "description_en": {
                    "type": "text",
                    "analyzer": "ik_max_word",
                    "search_analyzer": "ik_max_word_synonym"
                },
                "collection": {"type": "keyword"},
                "features": {"type": "object", "enabled": True},
                "vector_id": {"type": "keyword"},
                "metadata": {"type": "object", "enabled": True},
                **ragflow_fields
            }
        }
    }


def build_index_body_without_ik() -> dict:
    """
    构建不使用 IK 分词器的索引配置

    @returns ES 索引配置
    """
    ragflow_fields = _ragflow_compatible_fields(analyzer="default")
    return {
        "settings": {
            "index": {
                "max_ngram_diff": 2
            },
            "number_of_shards": 1,
            "number_of_replicas": 0,
            "analysis": {
                "analyzer": {
                    "default": {
                        "type": "standard",
                        "stopwords": "_english_"
                    },
                    "ngram_analyzer": {
                        "type": "custom",
                        "tokenizer": "ngram_tokenizer",
                        "filter": ["lowercase"]
                    }
                },
                "tokenizer": {
                    "ngram_tokenizer": {
                        "type": "ngram",
                        "min_gram": 2,
                        "max_gram": 4,
                        "token_chars": ["letter", "digit"]
                    }
                }
            }
        },
        "mappings": {
            "properties": {
                "id": {"type": "keyword"},
                "description": {
                    "type": "text",
                    "analyzer": "default"
                },
                "description_en": {
                    "type": "text",
                    "analyzer": "default"
                },
                "lang": {"type": "keyword"},
                "metadata": {
                    "type": "object",
                    "enabled": True
                },
                "features": {
                    "type": "object",
                    "enabled": True
                },
                **ragflow_fields
            }
        }
    }


def _ragflow_compatible_fields(analyzer: str, search_analyzer: str | None = None) -> dict:
    """共享的 RAGFlow-compatible 富字段 mapping。"""
    text_field = {"type": "text", "analyzer": analyzer}
    if search_analyzer:
        text_field["search_analyzer"] = search_analyzer
    return {
        "title_tks": dict(text_field),
        "title_sm_tks": dict(text_field),
        "important_kwd": {"type": "keyword"},
        "important_tks": dict(text_field),
        "question_tks": dict(text_field),
        "content_ltks": dict(text_field),
        "content_sm_ltks": dict(text_field),
        "content_with_weight": dict(text_field),
    }
