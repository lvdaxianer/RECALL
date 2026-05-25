"""
导入 skills 数据到 Milvus 和 ES

从 /Users/lvdaxianer/.claude/skills 目录导入所有 skill 数据

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

from app.services.milvus_service import MilvusService
from app.services.es_service import get_es_service
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


async def clear_and_import():
    """
    清空并重新导入所有 skills 数据
    """
    print("=" * 60)
    print("开始导入 skills 数据")
    print("=" * 60)

    # 1. 清空 Milvus skill collection
    print("\n[1/4] 清空 Milvus skill collection...")
    milvus = MilvusService()
    try:
        full_name = milvus._get_full_collection_name("skill")
        if milvus.conn.has_collection(full_name):
            milvus.conn.drop_collection(full_name)
            rag_insert_logger.info("[Milvus] skill collection 已清空")
            print(f"  - Milvus skill collection '{full_name}' 已清空")
    except Exception as e:
        print(f"  - 清空 Milvus 失败: {e}")

    # 2. 清空 ES skill index
    print("\n[2/4] 清空 ES skill index...")
    es = get_es_service()
    try:
        if es.is_connected():
            if es.client.indices.exists(index=Config.ES_SKILL_INDEX):
                es.client.indices.delete(index=Config.ES_SKILL_INDEX)
                print(f"  - ES index '{Config.ES_SKILL_INDEX}' 已删除")
            # 重新创建索引
            await es.create_index_if_not_exists(Config.ES_SKILL_INDEX)
            print(f"  - ES index '{Config.ES_SKILL_INDEX}' 已重建")
        else:
            print("  - ES 未连接，跳过")
    except Exception as e:
        print(f"  - 清空 ES 失败: {e}")

    # 3. 扫描所有 skills 目录
    print("\n[3/4] 扫描 skills 目录...")
    skill_files = []
    for item in SKILLS_DIR.iterdir():
        if item.is_dir():
            skill_md = item / "SKILL.md"
            if skill_md.exists():
                skill_files.append(skill_md)

    print(f"  - 找到 {len(skill_files)} 个 skill 文件")
    for sf in skill_files[:5]:
        print(f"    - {sf.parent.name}")
    if len(skill_files) > 5:
        print(f"    ... 还有 {len(skill_files) - 5} 个")

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
                    index_name=Config.ES_SKILL_INDEX,
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
    asyncio.get_event_loop().run_until_complete(clear_and_import())
