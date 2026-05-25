"""
重建 ES 索引（支持同义词）

使用 IK 分词器 + 同义词过滤器创建索引

@author lvdaxianerplus
@date 2026-04-16
"""

import os
import sys
import asyncio
from pathlib import Path

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(override=True)

from app.services.es_service import get_es_service
from app.services.milvus_service import MilvusService
from app.services.embedding_service import EmbeddingService
from app.config import Config
from app.utils.logger import rag_insert_logger


SKILLS_DIR = Path("/Users/lvdaxianer/.claude/skills")


def parse_skill_md(file_path: Path) -> dict:
    """
    解析 SKILL.md 文件

    @param file_path - SKILL.md 文件路径
    @returns 包含 name, description 的字典
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # 解析 frontmatter
    name = None
    description = None
    in_frontmatter = False
    frontmatter_lines = []

    lines = content.split('\n')
    for i, line in enumerate(lines):
        if i == 0 and line.strip() == '---':
            in_frontmatter = True
            continue
        if in_frontmatter and line.strip() == '---':
            in_frontmatter = False
            continue
        if in_frontmatter:
            frontmatter_lines.append(line)

    # 解析 frontmatter 中的 name 和 description
    for line in frontmatter_lines:
        if line.startswith('name:'):
            name = line.split('name:')[1].strip().strip('"')
        elif line.startswith('description:'):
            description = line.split('description:')[1].strip().strip('"')

    return {
        'name': name or file_path.parent.name,
        'description': description or ''
    }


async def recreate_index_with_synonyms():
    """
    使用同义词分析器重建 ES 索引
    """
    print("=" * 60)
    print("开始重建 ES 索引（支持同义词）")
    print("=" * 60)

    es = get_es_service()

    if not es.is_connected():
        print("ES 未连接，请检查配置")
        return

    index_name = Config.ES_SKILL_INDEX

    # 1. 删除旧索引
    print(f"\n[1/4] 删除旧索引 '{index_name}'...")
    try:
        if es.client.indices.exists(index=index_name):
            es.client.indices.delete(index=index_name)
            print(f"  - 索引 '{index_name}' 已删除")
        else:
            print(f"  - 索引不存在，跳过删除")
    except Exception as e:
        print(f"  - 删除失败: {e}")
        return

    # 2. 创建带同义词的新索引
    print(f"\n[2/4] 创建带同义词的新索引...")
    try:
        index_body = {
            "settings": {
                "number_of_shards": 1,
                "number_of_replicas": 0,
                "analysis": {
                    "filter": {
                        "synonym_filter": {
                            "type": "synonym",
                            "synonyms": [
                                # 添加你的同义词
                                "pinia,store,vuex,状态管理",
                                "api,接口,rest",
                                "vue,vuejs,vue3",
                                "react,reactjs",
                                "typescript,ts",
                                "javascript,js",
                            ]
                        }
                    },
                    "analyzer": {
                        "ik_max_word_synonym": {
                            "type": "custom",
                            "tokenizer": "ik_max_word",
                            "filter": ["lowercase", "synonym_filter"]
                        },
                        "ik_smart_synonym": {
                            "type": "custom",
                            "tokenizer": "ik_smart",
                            "filter": ["lowercase", "synonym_filter"]
                        },
                        "english_synonym": {
                            "type": "custom",
                            "tokenizer": "standard",
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
                        "analyzer": "ik_max_word_synonym",
                        "search_analyzer": "ik_smart_synonym"
                    },
                    "description_en": {
                        "type": "text",
                        "analyzer": "english_synonym",
                        "search_analyzer": "english_synonym"
                    },
                    "lang": {"type": "keyword"},
                    "metadata": {
                        "type": "object",
                        "enabled": True
                    }
                }
            }
        }

        es.client.indices.create(index=index_name, body=index_body)
        print(f"  - 索引 '{index_name}' 创建成功（带同义词分析器）")
    except Exception as e:
        print(f"  - 创建索引失败: {e}")
        return

    # 3. 扫描 skills 目录
    print("\n[3/4] 扫描 skills 目录...")
    skill_files = []
    for item in SKILLS_DIR.iterdir():
        if item.is_dir():
            skill_md = item / "SKILL.md"
            if skill_md.exists():
                skill_files.append(skill_md)

    print(f"  - 找到 {len(skill_files)} 个 skill 文件")

    # 4. 导入数据
    print("\n[4/4] 开始导入数据...")
    embedding = EmbeddingService()
    success_count = 0
    fail_count = 0

    for i, skill_file in enumerate(skill_files):
        try:
            # 解析 skill 文件
            skill_data = parse_skill_md(skill_file)
            skill_name = skill_data['name']
            description = skill_data['description']

            if not description:
                continue  # 跳过没有描述的 skill

            # 直接使用 description 作为描述
            full_description = description

            # 生成 doc_id
            doc_id = f"skill_{skill_name}"

            # 获取向量
            vector = await embedding.encode(full_description)

            # 插入 Milvus
            milvus = MilvusService()
            milvus_result = await milvus.insert(
                collection="skill",
                doc_id=doc_id,
                description=full_description,
                vector=vector,
                metadata={
                    "type": "skill",
                    "id": doc_id,
                    "name": skill_name,
                    "description": description
                }
            )

            # 插入 ES
            try:
                await es.index_document(
                    index_name=index_name,
                    doc_id=doc_id,
                    description=full_description,
                    metadata={
                        "type": "skill",
                        "id": doc_id,
                        "name": skill_name,
                        "description": description
                    },
                    lang="zh" if any('\u4e00' <= c <= '\u9fff' for c in description) else "en"
                )
            except Exception as es_err:
                rag_insert_logger.warning(f"[ES] 索引失败: {doc_id}, error={es_err}")

            success_count += 1
            if (i + 1) % 10 == 0:
                print(f"  - 已导入 {i + 1}/{len(skill_files)}")

        except Exception as e:
            fail_count += 1
            print(f"  - 导入失败: {skill_file.parent.name}, error={e}")

    print("\n" + "=" * 60)
    print(f"导入完成: 成功 {success_count}, 失败 {fail_count}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(recreate_index_with_synonyms())