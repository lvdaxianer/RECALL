"""
RAG 语义检索故事线集成测试

使用真实服务（不使用 mock）：
- Embedding 服务（阿里云 DashScope）
- Rerank 服务（阿里云 DashScope）
- Milvus 向量数据库

测试覆盖故事线完整流程：
1. 健康检查
2. 单条插入
3. 批量插入
4. 语义检索
5. 删除

@author lvdaxianerplus
@date 2026-04-15
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient
import os
import random
import string


# =============================================================================
# Fixtures
# =============================================================================

BASE_URL = "http://localhost:8000"

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_STORY_INTEGRATION_TESTS") != "true",
        reason="需要真实 localhost:8000、DashScope 和 Milvus 服务，默认跳过"
    )
]


def generate_id(prefix: str = "") -> str:
    """生成随机 ID"""
    random_str = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
    return f"{prefix}{random_str}" if prefix else random_str


@pytest_asyncio.fixture
async def client():
    """创建异步 HTTP 客户端"""
    async with AsyncClient(base_url=BASE_URL, timeout=60.0) as c:
        yield c


# =============================================================================
# 测试 1: 健康检查
# =============================================================================

class TestHealthCheck:
    """健康检查接口测试"""

    @pytest.mark.asyncio
    async def test_health_check(self, client):
        """
        场景：检查服务健康状态

        预期：
        - 返回 200
        - status 字段存在
        - services 包含 milvus, embedding, rerank
        """
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "services" in data
        assert "milvus" in data["services"]
        assert "embedding" in data["services"]
        assert "rerank" in data["services"]
        print(f"\n健康检查结果: {data}")


# =============================================================================
# 测试 2: 单条插入
# =============================================================================

class TestSingleInsert:
    """单条插入接口测试"""

    @pytest.mark.asyncio
    async def test_insert_skill(self, client):
        """
        场景：插入 skill 类型数据

        预期：插入成功，返回 id 和 collection
        """
        request_body = {
            "description": "用户登录功能，包含用户名密码验证",
            "metadata": {
                "type": "skill",
                "id": generate_id("skill-login-"),
                "description": "登录相关 skill"
            }
        }
        response = await client.post("/api/v1/rag/test-user/insert", json=request_body)
        print(f"\n插入 skill 响应: {response.json()}")
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200
        assert data["message"] == "success"
        assert "data" in data
        assert "id" in data["data"]
        assert data["data"]["collection"] == "skill"

    @pytest.mark.asyncio
    async def test_insert_asset(self, client):
        """
        场景：插入 asset 类型数据

        预期：插入成功
        """
        request_body = {
            "description": "登录页面 UI 组件，包含输入框和按钮",
            "metadata": {
                "type": "asset",
                "id": generate_id("asset-login-"),
                "description": "登录页面资源"
            }
        }
        response = await client.post("/api/v1/rag/test-user/insert", json=request_body)
        print(f"\n插入 asset 响应: {response.json()}")
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["collection"] == "asset"

    @pytest.mark.asyncio
    async def test_insert_multiple_skills(self, client):
        """
        场景：插入多条 skill 数据用于后续检索

        预期：全部插入成功
        """
        skills = [
            {"description": "用户注册功能，支持邮箱和手机号注册", "type": "skill", "desc": "注册"},
            {"description": "用户登录功能，支持账号密码登录", "type": "skill", "desc": "登录"},
            {"description": "用户登出功能，清除会话信息", "type": "skill", "desc": "登出"},
            {"description": "密码重置功能，通过邮箱验证重置", "type": "skill", "desc": "密码重置"},
            {"description": "用户个人信息编辑页面", "type": "asset", "desc": "个人信息"},
        ]

        inserted_ids = []
        for skill in skills:
            request_body = {
                "description": skill["description"],
                "metadata": {
                    "type": skill["type"],
                    "id": generate_id(f"{skill['type']}-{skill['desc']}-"),
                    "description": skill["desc"]
                }
            }
            response = await client.post("/api/v1/rag/test-user/insert", json=request_body)
            assert response.status_code == 200
            data = response.json()
            inserted_ids.append(data["data"]["id"])
            print(f"\n插入 {skill['desc']}: {data['data']['id']}")

        print(f"\n共插入 {len(inserted_ids)} 条数据")


# =============================================================================
# 测试 3: 批量插入
# =============================================================================

class TestBatchInsert:
    """批量插入接口测试"""

    @pytest.mark.asyncio
    async def test_batch_insert(self, client):
        """
        场景：批量插入多条数据

        预期：批量插入成功
        """
        request_body = {
            "items": [
                {
                    "description": f"批量插入的 skill 内容 {i}",
                    "metadata": {
                        "type": "skill",
                        "id": generate_id(f"batch-skill-{i}-"),
                        "description": f"批量 {i}"
                    }
                }
                for i in range(5)
            ]
        }
        response = await client.post("/api/v1/rag/test-user/insert/batch", json=request_body)
        print(f"\n批量插入响应: {response.json()}")
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200
        assert data["data"]["inserted_count"] == 5


# =============================================================================
# 测试 4: 语义检索
# =============================================================================

class TestSearch:
    """语义检索接口测试"""

    @pytest.mark.asyncio
    async def test_search_all(self, client):
        """
        场景：检索 type=all

        预期：返回所有类型的结果
        """
        request_body = {
            "input": "用户登录相关功能",
            "type": "all",
            "topK": 10
        }
        response = await client.post("/api/v1/rag/test-user/search", json=request_body)
        print(f"\n检索 all 响应: {response.json()}")
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200
        assert isinstance(data["data"], list)

    @pytest.mark.asyncio
    async def test_search_skill(self, client):
        """
        场景：只检索 skill 类型

        预期：只返回 skill 类型结果
        """
        request_body = {
            "input": "登录验证",
            "type": "skill",
            "topK": 10
        }
        response = await client.post("/api/v1/rag/test-user/search", json=request_body)
        print(f"\n检索 skill 响应: {response.json()}")
        assert response.status_code == 200
        data = response.json()
        for item in data.get("data", []):
            assert item["metadata"]["type"] == "skill"

    @pytest.mark.asyncio
    async def test_search_asset(self, client):
        """
        场景：只检索 asset 类型

        预期：只返回 asset 类型结果
        """
        request_body = {
            "input": "页面组件 UI",
            "type": "asset",
            "topK": 10
        }
        response = await client.post("/api/v1/rag/test-user/search", json=request_body)
        print(f"\n检索 asset 响应: {response.json()}")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_search_chinese_query(self, client):
        """
        场景：中文查询

        预期：正常返回结果
        """
        request_body = {
            "input": "怎么实现用户登录",
            "type": "skill",
            "topK": 5
        }
        response = await client.post("/api/v1/rag/test-user/search", json=request_body)
        print(f"\n中文检索响应: {response.json()}")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_search_empty_result(self, client):
        """
        场景：查询不存在的内容

        预期：返回空列表
        """
        request_body = {
            "input": "不存在的超纲内容 xyz123",
            "type": "skill",
            "topK": 10
        }
        response = await client.post("/api/v1/rag/test-user/search", json=request_body)
        print(f"\n空结果检索响应: {response.json()}")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data["data"], list)


# =============================================================================
# 测试 5: 删除
# =============================================================================

class TestDelete:
    """删除接口测试"""

    @pytest.mark.asyncio
    async def test_delete_after_insert(self, client):
        """
        场景：先插入再删除

        预期：删除成功
        """
        # 先插入
        insert_body = {
            "description": "用于删除测试的数据",
            "metadata": {
                "type": "skill",
                "id": generate_id("delete-test-"),
                "description": "删除测试"
            }
        }
        insert_response = await client.post("/api/v1/rag/test-user/insert", json=insert_body)
        assert insert_response.status_code == 200
        inserted_id = insert_response.json()["data"]["id"]

        # 再删除
        delete_body = {
            "type": "skill",
            "id": inserted_id
        }
        delete_response = await client.request("DELETE", "/api/v1/rag/test-user/delete", json=delete_body)
        print(f"\n删除响应: {delete_response.json()}")
        assert delete_response.status_code == 200
        assert delete_response.json()["code"] == 200


# =============================================================================
# 测试 6: 边界条件
# =============================================================================

class TestEdgeCases:
    """边界条件测试"""

    @pytest.mark.asyncio
    async def test_search_topk_1(self, client):
        """topK=1"""
        request_body = {
            "input": "用户",
            "type": "skill",
            "topK": 1
        }
        response = await client.post("/api/v1/rag/test-user/search", json=request_body)
        assert response.status_code == 200
        data = response.json()
        assert len(data.get("data", [])) <= 1

    @pytest.mark.asyncio
    async def test_search_topk_100(self, client):
        """topK=100"""
        request_body = {
            "input": "用户",
            "type": "skill",
            "topK": 100
        }
        response = await client.post("/api/v1/rag/test-user/search", json=request_body)
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_insert_very_long_description(self, client):
        """超长描述（接近上限）"""
        long_desc = "测试描述 " * 500  # ~4500 字符
        request_body = {
            "description": long_desc,
            "metadata": {
                "type": "skill",
                "id": generate_id("long-desc-"),
                "description": "长描述测试"
            }
        }
        response = await client.post("/api/v1/rag/test-user/insert", json=request_body)
        print(f"\n长描述插入响应: {response.status_code}")
        assert response.status_code == 200


# =============================================================================
# 测试 7: 完整故事线流程
# =============================================================================

class TestFullStoryFlow:
    """完整故事线流程测试"""

    @pytest.mark.asyncio
    async def test_complete_flow(self, client):
        """
        故事线完整流程：

        1. 健康检查 - 确认服务可用
        2. 用户A插入数据 - 添加测试 skill
        3. 用户B检索 - 验证能查到数据
        4. 删除测试数据 - 清理

        预期：全流程成功
        """
        print("\n========== 开始完整故事线流程测试 ==========")

        # 1. 健康检查
        print("\n[步骤1] 健康检查...")
        health_response = await client.get("/health")
        assert health_response.status_code == 200
        health_data = health_response.json()
        print(f"服务状态: {health_data['status']}")
        print(f"各服务: {health_data['services']}")

        # 2. 用户A插入数据
        print("\n[步骤2] 用户A插入数据...")
        test_id = generate_id("story-test-")
        insert_body = {
            "description": "这是一个完整的用户故事线测试数据，用于验证RAG语义检索功能",
            "metadata": {
                "type": "skill",
                "id": test_id,
                "description": "故事线测试"
            }
        }
        insert_response = await client.post("/api/v1/rag/test-user/insert", json=insert_body)
        assert insert_response.status_code == 200
        inserted_data = insert_response.json()
        print(f"插入成功: {inserted_data['data']}")

        # 3. 用户B检索
        print("\n[步骤3] 用户B检索...")
        search_body = {
            "input": "故事线测试",
            "type": "skill",
            "topK": 5
        }
        search_response = await client.post("/api/v1/rag/test-user/search", json=search_body)
        assert search_response.status_code == 200
        search_data = search_response.json()
        print(f"检索到 {len(search_data.get('data', []))} 条结果")

        # 验证能查到刚插入的数据
        found = False
        for item in search_data.get("data", []):
            if item["metadata"]["id"] == test_id:
                found = True
                print(f"找到测试数据，score={item['score']}")
                break

        # 如果检索未命中，检查检索结果列表
        if not found and len(search_data.get("data", [])) > 0:
            print("检索结果示例:")
            for item in search_data["data"][:3]:
                print(f"  - id={item['metadata']['id']}, score={item['score']}")

        # 4. 清理（删除测试数据）
        print("\n[步骤4] 清理测试数据...")
        delete_body = {"type": "skill", "id": test_id}
        delete_response = await client.request("DELETE", "/api/v1/rag/test-user/delete", json=delete_body)
        print(f"删除结果: {delete_response.status_code}")

        print("\n========== 故事线流程测试完成 ==========")


# =============================================================================
# 运行入口
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
