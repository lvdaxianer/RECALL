"""
语义优化服务测试

@author lvdaxianerplus
@date 2026-05-31
"""

import json
import pytest
from unittest.mock import AsyncMock

from app.models.schemas import SearchRequest
from app.services.query_optimize_service import QueryOptimizeService


def test_search_request_accepts_issue_type():
    """普通检索请求模型应承载问题类型字段。"""
    request = SearchRequest(input="白屏怎么排查", issue_type="fault")

    assert request.issue_type == "fault"


@pytest.mark.asyncio
async def test_optimize_includes_issue_type_for_fault_query():
    """查询优化结果应包含问题类型路由与 SEE trace。"""
    service = QueryOptimizeService(llm_service=None)

    result = await service.optimize("小程序上线后白屏，本地正常")

    assert result["issue_type"] == "fault"
    assert result["issue_route"]["issue_type"] == "fault"
    assert any(item["stage"] == "issue_type_detected" for item in result["see_trace"])
    assert result["query_scope"] == "local"


@pytest.mark.asyncio
async def test_optimize_query_success_json():
    """LLM 返回结构化 JSON 时生成优化查询和 SEE 追踪"""
    llm = AsyncMock()
    llm.chat_simple.return_value = (
        '{"intent":"排查登录失败原因",'
        '"cot_plan":["识别现象","检索认证错误"],'
        '"optimized_query":"登录失败的常见原因和排查步骤",'
        '"expanded_queries":["登录失败原因","认证失败排查"]}'
    )
    service = QueryOptimizeService(llm_service=llm)

    result = await service.optimize("登录失败")

    assert result["intent"] == "排查登录失败原因"
    assert result["optimized_query"] == "登录失败的常见原因和排查步骤"
    assert result["expanded_queries"] == ["登录失败", "登录失败原因", "认证失败排查"]
    assert result["cot_plan"] == ["识别现象", "检索认证错误"]
    assert result["see_trace"][0]["stage"] == "intent"
    assert result["fallback_used"] is False


@pytest.mark.asyncio
async def test_optimize_query_accepts_json_code_block():
    """LLM 返回 markdown JSON 代码块时也能解析"""
    llm = AsyncMock()
    llm.chat_simple.return_value = (
        '```json\n'
        '{"intent":"查找 JWT 登录",'
        '"cot_plan":["识别 JWT","检索登录认证"],'
        '"optimized_query":"JWT 登录认证",'
        '"expanded_queries":["JWT 登录","登录认证"]}'
        '\n```'
    )
    service = QueryOptimizeService(llm_service=llm)

    result = await service.optimize("JWT 登录")

    assert result["intent"] == "查找 JWT 登录"
    assert result["optimized_query"] == "JWT 登录认证"
    assert result["expanded_queries"] == ["JWT 登录", "登录认证"]
    assert result["fallback_used"] is False


@pytest.mark.asyncio
async def test_optimize_query_invalid_json_fallback():
    """LLM 返回非 JSON 时降级使用原始查询"""
    llm = AsyncMock()
    llm.chat_simple.return_value = "not-json"
    service = QueryOptimizeService(llm_service=llm)

    result = await service.optimize("登录失败")

    assert result["optimized_query"] == "登录失败"
    assert result["expanded_queries"] == ["登录失败"]
    assert result["see_trace"][0]["stage"] == "fallback"
    assert result["fallback_used"] is True


@pytest.mark.asyncio
async def test_optimize_query_llm_exception_fallback():
    """LLM 调用异常时降级使用原始查询并记录原因"""
    llm = AsyncMock()
    llm.chat_simple.side_effect = RuntimeError("llm unavailable")
    service = QueryOptimizeService(llm_service=llm)

    result = await service.optimize("登录失败")

    assert result["optimized_query"] == "登录失败"
    assert result["fallback_used"] is True
    assert "llm unavailable" in result["fallback_reason"]


@pytest.mark.asyncio
async def test_optimize_query_uses_memory_cache_for_same_query():
    """相同查询复用优化结果，避免重复调用 LLM 增加端到端延迟"""
    llm = AsyncMock()
    llm.chat_simple.return_value = (
        '{"intent":"排查登录失败原因",'
        '"cot_plan":["识别现象"],'
        '"optimized_query":"登录失败排查",'
        '"expanded_queries":["登录失败排查"]}'
    )
    service = QueryOptimizeService(llm_service=llm)

    first = await service.optimize("登录失败")
    second = await service.optimize("登录失败")

    assert first["optimized_query"] == "登录失败排查"
    assert second["optimized_query"] == "登录失败排查"
    assert llm.chat_simple.await_count == 1
    assert any(item["stage"] == "optimize_cache" for item in second["see_trace"])


@pytest.mark.asyncio
async def test_optimize_query_cache_uses_normalized_query_key(monkeypatch):
    """标点、空格和高置信同义词不同但语义相同的查询复用优化缓存"""
    monkeypatch.setattr("app.services.query_optimize_service.Config.QUERY_OPTIMIZE_FAST_RULES_ENABLED", False, raising=False)
    llm = AsyncMock()
    llm.chat_simple.return_value = (
        '{"intent":"查找智慧社区通行联动",'
        '"cot_plan":["识别通行场景"],'
        '"optimized_query":"智慧社区门禁访客梯控车辆道闸联动",'
        '"expanded_queries":["智慧社区门禁访客梯控车辆道闸联动"]}'
    )
    service = QueryOptimizeService(llm_service=llm)

    first = await service.optimize("智慧社区：人脸门禁、访客预约、电梯权限、车辆道闸联动")
    second = await service.optimize("智慧社区 人脸门禁 访客预约 梯控 车闸联动")

    assert first["optimized_query"] == "智慧社区门禁访客梯控车辆道闸联动"
    assert second["optimized_query"] == "智慧社区门禁访客梯控车辆道闸联动"
    assert llm.chat_simple.await_count == 1
    cache_trace = next(item for item in second["see_trace"] if item["stage"] == "optimize_cache")
    assert cache_trace["metrics"]["cache_hit_type"] == "normalized"
    assert cache_trace["metrics"]["normalized_query"]


@pytest.mark.asyncio
async def test_optimize_query_fast_rules_skip_llm_for_clear_business_query(monkeypatch):
    """明确业务查询命中快速规则时跳过 LLM，降低首次优化检索延迟"""
    monkeypatch.setattr("app.services.query_optimize_service.Config.QUERY_OPTIMIZE_FAST_RULES_ENABLED", True, raising=False)
    llm = AsyncMock()
    service = QueryOptimizeService(llm_service=llm)

    result = await service.optimize("社区要做人脸门禁、访客预约、电梯权限和车辆道闸联动，应该命中哪个文档？")

    assert result["optimized_query"] == "智慧社区门禁访客梯控车辆道闸联动"
    assert result["expanded_queries"] == [
        "智慧社区门禁访客梯控车辆道闸联动",
        "人脸门禁 访客预约 电梯权限 车辆道闸",
    ]
    assert result["fallback_used"] is False
    assert result["fallback_reason"] == ""
    assert result["see_trace"][0]["stage"] == "fast_rules"
    assert llm.chat_simple.await_count == 0


@pytest.mark.asyncio
async def test_optimize_query_fast_rules_do_not_initialize_default_llm(monkeypatch):
    """命中快速规则时不初始化默认 LLM 客户端，避免首次请求无效开销"""
    monkeypatch.setattr("app.services.query_optimize_service.Config.QUERY_OPTIMIZE_FAST_RULES_ENABLED", True, raising=False)

    def fail_if_llm_initialized():
        raise AssertionError("LLM should be initialized lazily")

    monkeypatch.setattr(
        "app.services.query_optimize_service.get_llm_service",
        fail_if_llm_initialized
    )
    service = QueryOptimizeService()

    result = await service.optimize("社区要做人脸门禁、访客预约、电梯权限和车辆道闸联动，应该命中哪个文档？")

    assert result["optimized_query"] == "智慧社区门禁访客梯控车辆道闸联动"
    assert result["see_trace"][0]["stage"] == "fast_rules"


@pytest.mark.asyncio
async def test_optimize_query_troubleshooting_rule_decomposes_mini_program_white_screen(monkeypatch):
    """小程序上线后白屏命中故障规则，并在 SEE 中展示结构化拆解"""
    monkeypatch.setattr("app.services.query_optimize_service.Config.QUERY_OPTIMIZE_FAST_RULES_ENABLED", True, raising=False)
    monkeypatch.setattr("app.services.query_optimize_service.Config.QUERY_OPTIMIZE_RULES_PATH", "", raising=False)
    llm = AsyncMock()
    service = QueryOptimizeService(llm_service=llm)

    result = await service.optimize("我的小程序上线后白屏了，之前本地开发都正常")

    assert result["intent"] == "排查小程序生产环境上线后白屏问题"
    assert result["optimized_query"] == "小程序上线后白屏 本地正常 生产环境异常 排查"
    assert result["expanded_queries"] == [
        "小程序上线后白屏 本地开发正常 生产环境异常",
        "微信小程序 发布后白屏 构建配置 接口域名 资源加载",
        "小程序线上白屏 app.js 报错 分包加载 权限配置",
    ]
    assert result["cot_plan"] == [
        "识别故障现象：小程序白屏",
        "区分环境差异：本地开发正常，生产环境异常",
        "优先检索发布、构建、配置、接口、资源加载、权限和运行时错误相关问题",
    ]
    assert result["see_trace"][0]["stage"] == "query_decomposition"
    assert result["see_trace"][0]["metrics"] == {
        "query_type": "troubleshooting",
        "rule": "mini_program_white_screen_after_release",
        "entities": ["小程序"],
        "symptoms": ["白屏"],
        "environment_gap": ["本地正常", "生产环境异常"],
        "time_context": ["上线后"],
    }
    assert result["see_trace"][1]["stage"] == "fast_rules"
    assert llm.chat_simple.await_count == 0


@pytest.mark.asyncio
async def test_optimize_query_exposes_query_scope_and_route_plan(monkeypatch):
    """查询优化结果暴露 query_scope 与 route_plan，且 cot_plan 仍只包含摘要"""
    monkeypatch.setattr("app.services.query_optimize_service.Config.QUERY_OPTIMIZE_FAST_RULES_ENABLED", True, raising=False)
    service = QueryOptimizeService(llm_service=AsyncMock())

    result = await service.optimize("请总结这批文档的整体架构和能力缺口")

    assert result["query_scope"] == "global"
    assert result["route_plan"]["strategy"] == "summary_first"
    assert any(item["stage"] == "query_scope" for item in result["see_trace"])
    joined_plan = " ".join(result["cot_plan"])
    assert "chain of thought" not in joined_plan.lower()
    assert "逐步推理" not in joined_plan


@pytest.mark.asyncio
async def test_optimize_query_uses_configured_troubleshooting_rules(monkeypatch, tmp_path):
    """QUERY_OPTIMIZE_RULES_PATH 可配置故障类拆解规则"""
    rules_path = tmp_path / "query-rules.json"
    rules_path.write_text(
        json.dumps({
            "rules": [
                {
                    "name": "h5_blank_after_deploy",
                    "query_type": "troubleshooting",
                    "triggers": ["h5", "部署", "空白"],
                    "intent": "排查 H5 部署后页面空白问题",
                    "cot_plan": ["识别 H5 空白现象", "对比本地与部署环境差异"],
                    "optimized_query": "H5 部署后页面空白 本地正常 排查",
                    "expanded_queries": ["H5 部署后页面空白", "前端部署后白屏 资源路径 接口配置"],
                    "decomposition": {
                        "entities": ["H5"],
                        "symptoms": ["页面空白"],
                        "environment_gap": ["本地正常", "部署环境异常"],
                        "time_context": ["部署后"]
                    }
                }
            ]
        }, ensure_ascii=False),
        encoding="utf-8"
    )
    monkeypatch.setattr("app.services.query_optimize_service.Config.QUERY_OPTIMIZE_FAST_RULES_ENABLED", True, raising=False)
    monkeypatch.setattr("app.services.query_optimize_service.Config.QUERY_OPTIMIZE_RULES_PATH", str(rules_path), raising=False)
    llm = AsyncMock()
    service = QueryOptimizeService(llm_service=llm)

    result = await service.optimize("H5部署后页面空白，本地正常")

    assert result["intent"] == "排查 H5 部署后页面空白问题"
    assert result["optimized_query"] == "H5 部署后页面空白 本地正常 排查"
    assert result["expanded_queries"] == ["H5 部署后页面空白", "前端部署后白屏 资源路径 接口配置"]
    assert result["see_trace"][0]["metrics"]["rule"] == "h5_blank_after_deploy"
    assert result["see_trace"][0]["metrics"]["entities"] == ["H5"]
    assert llm.chat_simple.await_count == 0


@pytest.mark.asyncio
async def test_optimize_query_cache_uses_structured_troubleshooting_key(monkeypatch):
    """故障类同义表达复用结构化缓存 key，提升优化缓存命中率"""
    monkeypatch.setattr("app.services.query_optimize_service.Config.QUERY_OPTIMIZE_FAST_RULES_ENABLED", True, raising=False)
    monkeypatch.setattr("app.services.query_optimize_service.Config.QUERY_OPTIMIZE_RULES_PATH", "", raising=False)
    llm = AsyncMock()
    service = QueryOptimizeService(llm_service=llm)

    first = await service.optimize("我的小程序上线后白屏了，之前本地开发都正常")
    second = await service.optimize("本地没问题，发布小程序后页面空白")

    assert first["optimized_query"] == second["optimized_query"]
    cache_trace = next(item for item in second["see_trace"] if item["stage"] == "optimize_cache")
    assert cache_trace["metrics"]["cache_hit_type"] == "normalized"
    assert cache_trace["metrics"]["normalized_query"] == (
        "type:troubleshooting entity:小程序 symptom:白屏 env:本地正常->生产环境异常 time:上线后"
    )
    assert llm.chat_simple.await_count == 0


@pytest.mark.asyncio
async def test_optimize_query_uses_configured_prompt_file(monkeypatch, tmp_path):
    """配置 QUERY_OPTIMIZE_PROMPT_PATH 后使用文件内 Prompt 模板调用 LLM"""
    monkeypatch.setattr("app.services.query_optimize_service.Config.QUERY_OPTIMIZE_FAST_RULES_ENABLED", False, raising=False)
    prompt_path = tmp_path / "query-optimize-prompt.txt"
    prompt_path.write_text("自定义检索计划模板::{query}::只输出 JSON", encoding="utf-8")
    monkeypatch.setattr(
        "app.services.query_optimize_service.Config.QUERY_OPTIMIZE_PROMPT_PATH",
        str(prompt_path),
        raising=False
    )
    llm = AsyncMock()
    llm.chat_simple.return_value = (
        '{"intent":"查找告警处置",'
        '"cot_plan":["识别告警对象"],'
        '"optimized_query":"设备告警处置流程",'
        '"expanded_queries":["设备告警处置"]}'
    )
    service = QueryOptimizeService(llm_service=llm)

    result = await service.optimize("告警怎么处理")

    sent_prompt = llm.chat_simple.await_args.args[0]
    assert "自定义检索计划模板::告警怎么处理::只输出 JSON" == sent_prompt
    assert result["optimized_query"] == "设备告警处置流程"


@pytest.mark.asyncio
async def test_optimize_query_missing_prompt_file_falls_back_to_default(monkeypatch, tmp_path):
    """配置的 Prompt 文件不存在时回退内置模板，保证查询优化可用"""
    monkeypatch.setattr("app.services.query_optimize_service.Config.QUERY_OPTIMIZE_FAST_RULES_ENABLED", False, raising=False)
    monkeypatch.setattr(
        "app.services.query_optimize_service.Config.QUERY_OPTIMIZE_PROMPT_PATH",
        str(tmp_path / "missing-prompt.txt"),
        raising=False
    )
    llm = AsyncMock()
    llm.chat_simple.return_value = (
        '{"intent":"查找告警处置",'
        '"cot_plan":["识别告警对象"],'
        '"optimized_query":"设备告警处置流程",'
        '"expanded_queries":["设备告警处置"]}'
    )
    service = QueryOptimizeService(llm_service=llm)

    result = await service.optimize("告警怎么处理")

    sent_prompt = llm.chat_simple.await_args.args[0]
    assert "请将用户查询优化为更适合 RAG 检索的结构化计划" in sent_prompt
    assert "用户查询：告警怎么处理" in sent_prompt
    assert "{{" not in sent_prompt
    assert "}}" not in sent_prompt
    assert result["optimized_query"] == "设备告警处置流程"


@pytest.mark.asyncio
async def test_optimize_query_configured_prompt_allows_json_braces(monkeypatch, tmp_path):
    """自定义 Prompt 可直接包含 JSON 示例，不要求手动转义花括号"""
    monkeypatch.setattr("app.services.query_optimize_service.Config.QUERY_OPTIMIZE_FAST_RULES_ENABLED", False, raising=False)
    prompt_path = tmp_path / "query-optimize-prompt.txt"
    prompt_path.write_text(
        '用户查询：{query}\n只输出 JSON：{"optimized_query":"...","expanded_queries":["..."]}',
        encoding="utf-8"
    )
    monkeypatch.setattr(
        "app.services.query_optimize_service.Config.QUERY_OPTIMIZE_PROMPT_PATH",
        str(prompt_path),
        raising=False
    )
    llm = AsyncMock()
    llm.chat_simple.return_value = (
        '{"intent":"查找告警处置",'
        '"cot_plan":["识别告警对象"],'
        '"optimized_query":"设备告警处置流程",'
        '"expanded_queries":["设备告警处置"]}'
    )
    service = QueryOptimizeService(llm_service=llm)

    await service.optimize("告警怎么处理")

    sent_prompt = llm.chat_simple.await_args.args[0]
    assert '用户查询：告警怎么处理' in sent_prompt
    assert '{"optimized_query":"...","expanded_queries":["..."]}' in sent_prompt
