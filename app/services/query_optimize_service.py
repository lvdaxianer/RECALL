"""
语义优化服务

识别查询意图，生成检索计划摘要和扩展查询。

@author lvdaxianerplus
@date 2026-05-31
"""

import json
from pathlib import Path
import re
import time
from collections import OrderedDict
from copy import deepcopy
from typing import Optional, Dict, Any

from app.config import Config
from app.services.issue_routing_service import IssueRoutingService
from app.services.llm_service import get_llm_service
from app.services.query_scope_service import QueryScopeService
from app.services.query_normalization import normalize_query_text
from app.utils.logger import get_logger

optimize_logger = get_logger("SemanticOptimize")

OPTIMIZE_PROMPT = """
请将用户查询优化为更适合 RAG 检索的结构化计划。

要求：
1. 识别用户核心意图。
2. 输出可解释的检索计划摘要，不输出完整私有推理链。
3. 生成 1-3 个检索查询，覆盖同义词、故障现象、关键实体。
4. 不要编造事实，只改写检索表达。

用户查询：{query}

只输出 JSON：
{
  "intent": "...",
  "cot_plan": ["...", "..."],
  "optimized_query": "...",
  "expanded_queries": ["...", "..."]
}
"""

DEFAULT_OPTIMIZE_RULES = [
    {
        "name": "mini_program_white_screen_after_release",
        "query_type": "troubleshooting",
        "triggers": ["小程序"],
        "synonym_triggers": [
            ["上线后", "发布后", "发布", "正式环境", "生产环境", "线上"],
            ["本地正常", "本地开发正常", "本地开发都正常", "本地没问题"],
            ["白屏", "页面空白"],
        ],
        "intent": "排查小程序生产环境上线后白屏问题",
        "cot_plan": [
            "识别故障现象：小程序白屏",
            "区分环境差异：本地开发正常，生产环境异常",
            "优先检索发布、构建、配置、接口、资源加载、权限和运行时错误相关问题",
        ],
        "optimized_query": "小程序上线后白屏 本地正常 生产环境异常 排查",
        "expanded_queries": [
            "小程序上线后白屏 本地开发正常 生产环境异常",
            "微信小程序 发布后白屏 构建配置 接口域名 资源加载",
            "小程序线上白屏 app.js 报错 分包加载 权限配置",
        ],
        "decomposition": {
            "entities": ["小程序"],
            "symptoms": ["白屏"],
            "environment_gap": ["本地正常", "生产环境异常"],
            "time_context": ["上线后"],
        },
    },
]

class QueryOptimizeService:
    """语义优化服务"""

    def __init__(self, llm_service=None):
        """初始化语义优化服务"""
        self._llm = llm_service
        self._cache: OrderedDict[str, tuple[float, Dict[str, Any]]] = OrderedDict()
        self._scope_service = QueryScopeService()
        self._issue_routing_service = IssueRoutingService()

    @property
    def llm(self):
        """惰性初始化 LLM 客户端，避免缓存/快速规则路径产生无效开销。"""
        if self._llm is None:
            self._llm = get_llm_service()
        return self._llm

    async def optimize(self, query: str) -> Dict[str, Any]:
        """
        优化查询

        @param query - 原始查询
        @returns 优化结果
        @author lvdaxianerplus
        @date 2026-05-31
        """
        cached_result = self._get_cached(query)
        if cached_result is not None:
            optimize_logger.info("[语义优化] 缓存命中, query='{}'", query[:80])
            return self._with_query_scope(query, cached_result)

        fast_result = self._optimize_with_fast_rules(query)
        if fast_result is not None:
            optimize_logger.info(
                "[语义优化] 快速规则命中, original='{}', optimized='{}'",
                query[:80],
                fast_result["optimized_query"][:80]
            )
            fast_result = self._with_query_scope(query, fast_result)
            self._set_cached(query, fast_result)
            return fast_result

        try:
            prompt = self._build_prompt(query)
            response = await self.llm.chat_simple(
                prompt,
                system="你是一个专业的信息检索意图分析和查询优化助手。"
            )
            result = self._parse_response(response, query)
            optimize_logger.info(
                "[语义优化] 优化完成, original='{}', optimized='{}'",
                query[:80],
                result["optimized_query"][:80]
            )
            result = self._with_query_scope(query, result)
            self._set_cached(query, result)
            return result
        except Exception as e:
            optimize_logger.warning("[语义优化] 优化失败，使用原始查询, error={}", str(e))
            return self._with_query_scope(query, self._fallback(query, str(e)))

    def _with_query_scope(self, query: str, result: Dict[str, Any]) -> Dict[str, Any]:
        """补充 query_scope 与路由摘要，避免暴露私有推理链。"""
        scoped = deepcopy(result)
        scope = self._scope_service.detect(query)
        scoped["query_scope"] = scope["query_scope"]
        scoped["route_plan"] = scope["route_plan"]
        issue_route = self._issue_routing_service.detect(query)
        scoped["issue_type"] = issue_route["issue_type"]
        scoped["issue_route"] = issue_route
        trace = list(scoped.get("see_trace", []) or [])
        if not any(item.get("stage") == "query_scope" for item in trace):
            trace.append({
                "stage": "query_scope",
                "summary": scope["reason"],
                "metrics": {
                    "query_scope": scope["query_scope"],
                    "route_plan": scope["route_plan"],
                },
            })
        else:
            pass
        if not any(item.get("stage") == "issue_type_detected" for item in trace):
            trace.append({
                "stage": "issue_type_detected",
                "summary": issue_route["reason"],
                "metrics": {
                    "issue_type": issue_route["issue_type"],
                    "confidence": issue_route["confidence"],
                    "matched_terms": issue_route["matched_terms"],
                },
            })
        else:
            pass
        scoped["see_trace"] = trace
        return scoped

    def _get_cached(self, query: str) -> Optional[Dict[str, Any]]:
        """获取缓存的查询优化结果"""
        exact_key = self._build_cache_key(query)
        normalized_query = self._normalize_query_for_cache(query)
        normalized_key = self._build_cache_key(normalized_query, normalized=True)

        cached = self._cache.get(exact_key)
        cache_hit_type = "exact"
        if cached is None:
            cached = self._cache.get(normalized_key)
            cache_hit_type = "normalized"
        if cached is None:
            return None

        created_at, result = cached
        if (time.time() - created_at) > Config.QUERY_OPTIMIZE_CACHE_TTL:
            self._cache.pop(exact_key, None)
            self._cache.pop(normalized_key, None)
            return None

        self._cache.move_to_end(exact_key if cache_hit_type == "exact" else normalized_key)
        cached_result = deepcopy(result)
        cached_result.setdefault("see_trace", []).append({
            "stage": "optimize_cache",
            "summary": "命中查询优化缓存，跳过 LLM 调用",
            "metrics": {
                "cache_hit": True,
                "cache_hit_type": cache_hit_type,
                "normalized_query": normalized_query
            }
        })
        return cached_result

    def _set_cached(self, query: str, result: Dict[str, Any]) -> None:
        """写入查询优化缓存"""
        exact_key = self._build_cache_key(query)
        normalized_query = self._normalize_query_for_cache(query)
        normalized_key = self._build_cache_key(normalized_query, normalized=True)
        cached_value = (time.time(), deepcopy(result))

        self._cache[exact_key] = cached_value
        self._cache.move_to_end(exact_key)
        self._cache[normalized_key] = cached_value
        self._cache.move_to_end(normalized_key)
        while len(self._cache) > Config.QUERY_OPTIMIZE_CACHE_MAX_SIZE:
            self._cache.popitem(last=False)

    def _build_cache_key(self, query: str, normalized: bool = False) -> str:
        """构造查询优化缓存 key。"""
        prefix = "normalized" if normalized else "exact"
        return f"{prefix}:{query or ''}"

    def _normalize_query_for_cache(self, query: str) -> str:
        """轻量查询归一化，用于提升优化缓存命中率。"""
        matched_rule = self._match_configured_rule(query)
        if matched_rule and matched_rule.get("query_type") == "troubleshooting":
            return self._build_structured_cache_query(matched_rule)
        return normalize_query_text(query)

    def _optimize_with_fast_rules(self, query: str) -> Optional[Dict[str, Any]]:
        """用高置信本地规则优化明确业务查询，跳过 LLM 调用。"""
        if not Config.QUERY_OPTIMIZE_FAST_RULES_ENABLED:
            return None

        matched_rule = self._match_configured_rule(query)
        if matched_rule is not None:
            return self._build_rule_result(matched_rule)

        compact_query = re.sub(r"\s+", "", self._normalize_query_for_cache(query))
        community_terms = ["社区", "门禁", "访客", "梯控", "车辆道闸"]
        if all(term in compact_query for term in community_terms):
            expanded_queries = [
                "智慧社区门禁访客梯控车辆道闸联动",
                "人脸门禁 访客预约 电梯权限 车辆道闸",
            ]
            return {
                "intent": "查找智慧社区通行管理多系统联动能力",
                "cot_plan": [
                    "识别智慧社区通行场景",
                    "提取门禁、访客、梯控、车辆道闸关键实体",
                    "优先检索多系统联动或集成方案"
                ],
                "optimized_query": expanded_queries[0],
                "expanded_queries": expanded_queries,
                "see_trace": [
                    {
                        "stage": "fast_rules",
                        "summary": "命中本地快速规则，跳过 LLM 查询优化",
                        "metrics": {
                            "rule": "community_access_control",
                            "expanded_query_count": len(expanded_queries)
                        }
                    }
                ],
                "fallback_used": False,
                "fallback_reason": ""
            }

        return None

    def _match_configured_rule(self, query: str) -> Optional[Dict[str, Any]]:
        """匹配查询优化配置规则。"""
        normalized_query = self._normalize_plain_query(query)
        for rule in self._load_optimize_rules():
            if self._rule_matches(rule, normalized_query):
                return rule
        return None

    def _load_optimize_rules(self) -> list[Dict[str, Any]]:
        """读取可配置查询优化规则，读取失败时使用内置规则。"""
        rules_path = Config.QUERY_OPTIMIZE_RULES_PATH
        if not rules_path:
            return DEFAULT_OPTIMIZE_RULES

        try:
            raw_rules = json.loads(Path(rules_path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            optimize_logger.warning(
                "[语义优化] 自定义规则读取失败，使用内置规则, path='{}', error={}",
                rules_path,
                str(e)
            )
            return DEFAULT_OPTIMIZE_RULES

        if isinstance(raw_rules, dict):
            rules = raw_rules.get("rules", [])
        else:
            rules = raw_rules
        if not isinstance(rules, list):
            optimize_logger.warning(
                "[语义优化] 自定义规则格式无效，使用内置规则, path='{}'",
                rules_path
            )
            return DEFAULT_OPTIMIZE_RULES
        return [rule for rule in rules if isinstance(rule, dict)]

    def _rule_matches(self, rule: Dict[str, Any], normalized_query: str) -> bool:
        """判断规则是否命中。"""
        triggers = rule.get("triggers", [])
        if triggers and not all(self._contains_term(normalized_query, term) for term in triggers):
            return False

        synonym_triggers = rule.get("synonym_triggers", [])
        for group in synonym_triggers:
            if not isinstance(group, list):
                continue
            if not any(self._contains_term(normalized_query, term) for term in group):
                return False
        return bool(triggers or synonym_triggers)

    def _contains_term(self, normalized_query: str, term: str) -> bool:
        """判断归一化查询中是否包含目标词。"""
        normalized_term = self._normalize_plain_query(term)
        return bool(normalized_term and normalized_term in normalized_query)

    def _normalize_plain_query(self, query: str) -> str:
        """仅做文本归一化，避免结构化缓存递归调用规则匹配。"""
        return re.sub(r"\s+", "", normalize_query_text(query))

    def _build_rule_result(self, rule: Dict[str, Any]) -> Dict[str, Any]:
        """将配置规则转换为查询优化结果。"""
        expanded_queries = list(rule.get("expanded_queries") or [rule.get("optimized_query", "")])
        expanded_queries = [query for query in expanded_queries if query]
        optimized_query = rule.get("optimized_query") or (expanded_queries[0] if expanded_queries else "")
        decomposition = rule.get("decomposition") or {}
        return {
            "intent": rule.get("intent", ""),
            "cot_plan": list(rule.get("cot_plan", [])),
            "optimized_query": optimized_query,
            "expanded_queries": expanded_queries[:3],
            "see_trace": [
                {
                    "stage": "query_decomposition",
                    "summary": rule.get("intent", ""),
                    "metrics": {
                        "query_type": rule.get("query_type", ""),
                        "rule": rule.get("name", ""),
                        "entities": decomposition.get("entities", []),
                        "symptoms": decomposition.get("symptoms", []),
                        "environment_gap": decomposition.get("environment_gap", []),
                        "time_context": decomposition.get("time_context", []),
                    },
                },
                {
                    "stage": "fast_rules",
                    "summary": "命中本地可配置规则，跳过 LLM 查询优化",
                    "metrics": {
                        "rule": rule.get("name", ""),
                        "expanded_query_count": len(expanded_queries[:3]),
                    },
                },
            ],
            "fallback_used": False,
            "fallback_reason": "",
        }

    def _build_structured_cache_query(self, rule: Dict[str, Any]) -> str:
        """为故障类规则生成结构化缓存 key 查询串。"""
        decomposition = rule.get("decomposition") or {}
        entities = decomposition.get("entities", [])
        symptoms = decomposition.get("symptoms", [])
        environment_gap = decomposition.get("environment_gap", [])
        time_context = decomposition.get("time_context", [])
        env_value = "->".join(environment_gap)
        return (
            f"type:{rule.get('query_type', '')} "
            f"entity:{entities[0] if entities else ''} "
            f"symptom:{symptoms[0] if symptoms else ''} "
            f"env:{env_value} "
            f"time:{time_context[0] if time_context else ''}"
        ).strip()

    def _build_prompt(self, query: str) -> str:
        """构造 LLM 查询优化 Prompt。"""
        return self._get_prompt_template().replace("{query}", query)

    def _get_prompt_template(self) -> str:
        """读取可配置 Prompt 模板，读取失败时回退内置模板。"""
        prompt_path = Config.QUERY_OPTIMIZE_PROMPT_PATH
        if not prompt_path:
            return OPTIMIZE_PROMPT

        try:
            template = Path(prompt_path).read_text(encoding="utf-8")
        except OSError as e:
            optimize_logger.warning(
                "[语义优化] 自定义 Prompt 读取失败，使用内置模板, path='{}', error={}",
                prompt_path,
                str(e)
            )
            return OPTIMIZE_PROMPT

        if "{query}" not in template:
            optimize_logger.warning(
                "[语义优化] 自定义 Prompt 缺少 {query} 占位符，使用内置模板, path='{}'",
                prompt_path
            )
            return OPTIMIZE_PROMPT
        return template

    def _parse_response(self, response: str, original_query: str) -> Dict[str, Any]:
        """
        解析 LLM JSON 响应

        @param response - LLM 返回内容
        @param original_query - 原始查询
        @returns 解析后的优化结果
        """
        json_str = self._extract_json(response)
        if not json_str:
            optimize_logger.warning("[语义优化] JSON 解析失败, response='{}'", response[:120])
            return self._fallback(original_query, "invalid json")

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            optimize_logger.warning("[语义优化] JSON 解析失败, response='{}'", response[:120])
            return self._fallback(original_query, str(e))

        optimized_query = data.get("optimized_query") or original_query
        expanded_queries = data.get("expanded_queries") or [optimized_query]
        if original_query not in expanded_queries:
            expanded_queries.insert(0, original_query)
        limited_queries = expanded_queries[:3]

        return {
            "intent": data.get("intent", ""),
            "cot_plan": data.get("cot_plan", data.get("plan", [])),
            "optimized_query": optimized_query,
            "expanded_queries": limited_queries,
            "see_trace": [
                {
                    "stage": "intent",
                    "summary": data.get("intent", ""),
                    "metrics": {"expanded_query_count": len(limited_queries)}
                }
            ],
            "fallback_used": False,
            "fallback_reason": ""
        }

    def _extract_json(self, text: str) -> Optional[str]:
        """从 LLM 返回文本中提取 JSON 对象"""
        try:
            json.loads(text)
            return text
        except Exception:
            pass

        patterns = [
            r'```json\s*(\{.*?\})\s*```',
            r'```\s*(\{.*?\})\s*```',
            r'(\{.*\})'
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.DOTALL)
            if match:
                potential_json = match.group(1)
                try:
                    json.loads(potential_json)
                    return potential_json
                except Exception:
                    continue
        return None

    def _fallback(self, query: str, reason: str) -> Dict[str, Any]:
        """
        构造降级优化结果

        @param query - 原始查询
        @param reason - 降级原因
        @returns 降级结果
        """
        return {
            "intent": "",
            "cot_plan": [],
            "optimized_query": query,
            "expanded_queries": [query],
            "see_trace": [
                {
                    "stage": "fallback",
                    "summary": "LLM 优化失败，使用原始查询",
                    "metrics": {"expanded_query_count": 1}
                }
            ],
            "fallback_used": True,
            "fallback_reason": reason
        }


_query_optimize_service: Optional[QueryOptimizeService] = None


def get_query_optimize_service() -> QueryOptimizeService:
    """获取语义优化服务单例"""
    global _query_optimize_service
    if _query_optimize_service is None:
        _query_optimize_service = QueryOptimizeService()
    return _query_optimize_service
