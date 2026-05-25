"""
ES Service 集成测试

使用真实 ES 进行测试

@author lvdaxianerplus
@date 2026-04-16
"""

import pytest
import asyncio
from app.services.es_service import ESService
from app.config import Config


def get_es_service():
    """获取 ES Service 实例，失败时返回 None"""
    try:
        return ESService()
    except Exception:
        return None


def is_es_available():
    """检查 ES 是否可用"""
    service = get_es_service()
    if service is None:
        return False
    try:
        return service.is_connected()
    except Exception:
        return False


# 标记为集成测试
pytestmark = pytest.mark.integration


class TestESServiceLanguageDetection:
    """ES 语言检测测试（不需要真实 ES 连接）"""

    def test_detect_chinese(self):
        """测试中文检测"""
        service = ESService()
        assert service._contains_chinese("Pinia 是 Vue 的状态管理库")
        assert service._contains_chinese("你好世界")
        assert service._contains_chinese("状态管理")

    def test_detect_english_only(self):
        """测试纯英文检测"""
        service = ESService()
        assert not service._contains_chinese("Pinia is Vue's state management")
        assert not service._contains_chinese("Hello World")

    def test_detect_mixed(self):
        """测试中英混合"""
        service = ESService()
        assert service._contains_chinese("Pinia 状态管理")
        assert service._contains_chinese("Vue3状态管理")

    def test_detect_language(self):
        """测试语言检测"""
        service = ESService()
        assert service._detect_language("Pinia 是 Vue 的状态管理库") == "zh"
        assert service._detect_language("Pinia is Vue's state management") == "en"


class TestESServiceIntegration:
    """ES 集成测试（需要真实 ES）"""

    @pytest.fixture
    def service(self):
        """获取 ES Service 实例"""
        svc = get_es_service()
        if svc is None or not svc.is_connected():
            pytest.skip("ES 服务不可用，跳过集成测试")
        return svc

    @pytest.fixture
    def index_name(self):
        """测试索引名称"""
        return "test_rag_hybrid_search"

    @pytest.fixture(autouse=True)
    def setup_and_teardown(self, service, index_name):
        """每个测试前创建索引，测试后删除"""
        # 清理可能存在的旧索引
        try:
            service.client.indices.delete(index=index_name, ignore=[404])
        except Exception:
            pass
        yield
        # 清理测试索引
        try:
            service.client.indices.delete(index=index_name, ignore=[404])
        except Exception:
            pass

    def test_create_index(self, service, index_name):
        """测试创建索引"""
        async def run_test():
            await service.create_index_if_not_exists(index_name)
            assert service.client.indices.exists(index=index_name)

        asyncio.get_event_loop().run_until_complete(run_test())

    def test_index_and_search_chinese_doc(self, service, index_name):
        """测试索引中文文档并搜索"""

        async def run_test():
            # 1. 创建索引
            await service.create_index_if_not_exists(index_name)

            # 2. 索引文档
            await service.index_document(
                index_name=index_name,
                doc_id="doc_001",
                description="Pinia 是 Vue 的状态管理库",
                metadata={"type": "skill"},
                lang="zh"
            )
            service.client.indices.refresh(index=index_name)

            # 3. 搜索
            results = await service.search(
                index_name=index_name,
                query="Pinia",
                top_k=5,
                query_lang="auto"
            )

            # 4. 验证
            assert len(results) > 0
            assert results[0]["id"] == "doc_001"

            # 5. 验证描述字段存在
            assert "description" in results[0]

        asyncio.get_event_loop().run_until_complete(run_test())

    def test_index_and_search_multiple_docs(self, service, index_name):
        """测试索引多个文档并搜索"""

        async def run_test():
            # 1. 创建索引
            await service.create_index_if_not_exists(index_name)

            # 2. 索引多个文档
            docs = [
                ("doc_001", "Pinia 是 Vue3 推荐的状态管理库", "zh"),
                ("doc_002", "Vuex 是 Vue2 使用的状态管理库", "zh"),
                ("doc_003", "API 接口文档管理系统", "zh"),
                ("doc_004", "React Hooks 状态管理", "zh"),
            ]

            for doc_id, desc, lang in docs:
                await service.index_document(
                    index_name=index_name,
                    doc_id=doc_id,
                    description=desc,
                    metadata={"type": "skill"},
                    lang=lang
                )

            service.client.indices.refresh(index=index_name)

            # 3. 搜索状态管理
            results = await service.search(
                index_name=index_name,
                query="状态管理",
                top_k=5,
                query_lang="auto"
            )

            # 4. 验证
            assert len(results) >= 2  # 应该返回多个结果

        asyncio.get_event_loop().run_until_complete(run_test())

    def test_delete_document(self, service, index_name):
        """测试删除文档"""

        async def run_test():
            # 1. 创建索引并插入文档
            await service.create_index_if_not_exists(index_name)
            await service.index_document(
                index_name=index_name,
                doc_id="doc_to_delete",
                description="将被删除的文档",
                metadata={"type": "test"},
                lang="zh"
            )
            service.client.indices.refresh(index=index_name)

            # 2. 验证文档存在
            assert service.client.exists(index=index_name, id="doc_to_delete")

            # 3. 删除文档
            success = await service.delete_document(index_name, "doc_to_delete")
            assert success is True

            # 4. 刷新并验证文档不存在
            service.client.indices.refresh(index=index_name)
            assert not service.client.exists(index=index_name, id="doc_to_delete")

        asyncio.get_event_loop().run_until_complete(run_test())

    def test_search_with_top_k(self, service, index_name):
        """测试 top_k 参数"""

        async def run_test():
            # 1. 创建索引并插入文档
            await service.create_index_if_not_exists(index_name)
            for i in range(10):
                await service.index_document(
                    index_name=index_name,
                    doc_id=f"doc_{i}",
                    description=f"测试文档 {i}",
                    metadata={"type": "test"},
                    lang="zh"
                )
            service.client.indices.refresh(index=index_name)

            # 2. 限制返回数量
            results = await service.search(
                index_name=index_name,
                query="测试",
                top_k=3,
                query_lang="auto"
            )

            # 3. 验证
            assert len(results) <= 3

        asyncio.get_event_loop().run_until_complete(run_test())


class TestESServiceEndToEnd:
    """端到端测试"""

    @pytest.fixture
    def service(self):
        svc = get_es_service()
        if svc is None or not svc.is_connected():
            pytest.skip("ES 服务不可用，跳过集成测试")
        return svc

    @pytest.fixture
    def index_name(self):
        return "test_e2e"

    def test_full_workflow(self, service, index_name):
        """完整工作流：创建索引 -> 插入 -> 搜索 -> 删除"""

        async def run_test():
            # 清理
            try:
                service.client.indices.delete(index=index_name, ignore=[404])
            except Exception:
                pass

            # 1. 创建索引
            await service.create_index_if_not_exists(index_name)
            assert service.client.indices.exists(index=index_name)

            # 2. 插入数据
            test_data = [
                ("skill_001", "Pinia 是 Vue3 的状态管理库", "skill", "zh"),
                ("skill_002", "Vuex 是 Vue2 的状态管理库", "skill", "zh"),
                ("skill_003", "React Hooks 用于状态管理", "skill", "zh"),
            ]

            for doc_id, desc, doc_type, lang in test_data:
                await service.index_document(
                    index_name=index_name,
                    doc_id=doc_id,
                    description=desc,
                    metadata={"type": doc_type},
                    lang=lang
                )

            service.client.indices.refresh(index=index_name)

            # 3. 搜索 Pinia
            results = await service.search(
                index_name=index_name,
                query="Pinia",
                top_k=5,
                query_lang="auto"
            )
            assert len(results) > 0
            assert any("Pinia" in r.get("description", "") for r in results)

            # 4. 清理
            service.client.indices.delete(index=index_name)

        asyncio.get_event_loop().run_until_complete(run_test())


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
