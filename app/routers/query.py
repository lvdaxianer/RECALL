"""
高精度 RAG 问答路由

串联查询理解层 → 混合检索层 → 重排序层 → 生成层 → 验证层

@author lvdaxianerplus
@date 2026-05-25
"""

import time
import asyncio
from typing import List, Dict, Any
from fastapi import APIRouter
from app.models.schemas import QueryRequest, QueryResponse, CitationItem, QueryOptions
from app.query.rewriter import get_query_rewriter
from app.query.hyde import get_hyde
from app.query.decomposer import get_query_decomposer
from app.generation.context_compressor import get_context_compressor
from app.generation.generator import get_generator
from app.generation.citation_builder import build_citation_list
from app.validation.hallucination_filter import get_hallucination_filter
from app.services.embedding_service import EmbeddingService
from app.services.milvus_service import MilvusService
from app.services.es_service import get_es_service
from app.services.rerank_service import RerankService
from app.services.hybrid_search import rrf_fusion
from app.config import Config
from app.utils.logger import get_logger

query_logger = get_logger("QueryRouter")

router = APIRouter(prefix="/api/v1/query", tags=["Query"])

# 服务懒加载单例
_embedding_service = None
_milvus_service = None
_rerank_service = None


def _get_embedding() -> EmbeddingService:
    """获取 Embedding 服务单例"""
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService()
    return _embedding_service


def _get_milvus() -> MilvusService:
    """获取 Milvus 服务单例"""
    global _milvus_service
    if _milvus_service is None:
        _milvus_service = MilvusService()
    return _milvus_service


def _get_rerank() -> RerankService:
    """获取 Rerank 服务单例"""
    global _rerank_service
    if _rerank_service is None:
        _rerank_service = RerankService()
    return _rerank_service


@router.post("", response_model=QueryResponse)
async def query(request: QueryRequest):
    """
    高精度 RAG 问答接口

    完整流程：查询理解 → 混合检索 → 重排序 → 上下文压缩 → 生成 → 验证

    @param request - 问答请求
    @returns 带引用溯源的答案
    @author lvdaxianerplus
    @date 2026-05-25
    """
    start_time = time.time()
    opts = request.options or QueryOptions()
    query_text = request.query

    query_logger.info("[Query] 开始处理, query='{}', opts={}", query_text[:80], opts.model_dump())

    try:
        # Step 1: 查询理解层
        effective_queries = await _run_query_understanding(query_text, opts)

        # Step 2: 混合检索（对所有有效查询并行检索，合并结果）
        all_chunks = await _run_hybrid_retrieval(effective_queries, opts)

        # Step 3: Rerank 重排序
        reranked_chunks = await _run_rerank(query_text, all_chunks, opts)

        # Step 4: 上下文压缩
        compressed_chunks = get_context_compressor().compress(reranked_chunks, query_text)

        # Step 5: 生成答案
        gen_result = await get_generator().generate(query_text, compressed_chunks)
        answer = gen_result["answer"]
        citations_raw = gen_result["citations"]

        # Step 6: 验证层（Faithfulness 检测 + 幻觉过滤）
        faithfulness_score = None
        if opts.use_validation and compressed_chunks:
            contexts = [c.get("description", "") for c in compressed_chunks]
            filter_result = await _run_validation(answer, contexts, query_text, compressed_chunks)
            answer = filter_result["answer"]
            faithfulness_score = filter_result.get("faithfulness_score")
            # 如果答案被替换（幻觉过滤兜底），重新构建引用
            if not filter_result.get("passed", True):
                citations_raw = []

        latency_ms = int((time.time() - start_time) * 1000)
        query_logger.info(
            "[Query] 完成, latency={}ms, faithfulness={}, citations={}",
            latency_ms, faithfulness_score, len(citations_raw)
        )

        return QueryResponse(
            code=200,
            message="success",
            answer=answer,
            citations=[CitationItem(**c) for c in citations_raw],
            faithfulness_score=faithfulness_score,
            latency_ms=latency_ms
        )

    except Exception as e:
        latency_ms = int((time.time() - start_time) * 1000)
        query_logger.error("[Query] 处理失败, error={}, latency={}ms", str(e), latency_ms)
        return QueryResponse(
            code=500,
            message=f"处理失败: {str(e)}",
            answer="系统处理失败，请稍后重试。",
            citations=[],
            latency_ms=latency_ms
        )


async def _run_query_understanding(query_text: str, opts: QueryOptions) -> List[str]:
    """
    执行查询理解层

    根据选项执行改写、分解，返回有效查询列表

    @param query_text - 原始查询
    @param opts - 查询选项
    @returns 有效查询列表
    @author lvdaxianerplus
    @date 2026-05-25
    """
    queries = [query_text]

    # 查询改写：生成语义等价变体
    if opts.use_rewrite:
        try:
            rewrite_result = await get_query_rewriter().rewrite(query_text)
            rewritten = rewrite_result.get("rewritten", "")
            variants = rewrite_result.get("variants", [])
            # 将改写结果和变体加入查询列表（去重）
            for q in [rewritten] + variants:
                if q and q not in queries:
                    queries.append(q)
            query_logger.info("[Query] 查询改写完成, 变体数={}", len(queries) - 1)
        except Exception as e:
            query_logger.warning("[Query] 查询改写失败, error={}", str(e))

    # 问题分解：复杂问题拆分为子问题
    if opts.use_decompose:
        try:
            sub_questions = await get_query_decomposer().decompose(query_text)
            for q in sub_questions:
                if q and q not in queries:
                    queries.append(q)
            query_logger.info("[Query] 问题分解完成, 子问题数={}", len(sub_questions))
        except Exception as e:
            query_logger.warning("[Query] 问题分解失败, error={}", str(e))

    return queries


async def _run_hybrid_retrieval(
    queries: List[str],
    opts: QueryOptions
) -> List[Dict[str, Any]]:
    """
    对多个查询并行执行混合检索，合并去重

    @param queries - 查询列表
    @param opts - 查询选项
    @returns 合并后的 chunk 列表
    @author lvdaxianerplus
    @date 2026-05-25
    """
    search_type = opts.search_type or "all"
    collections = ["skill", "asset"] if search_type == "all" else [search_type]
    es_index = Config.ES_SKILL_INDEX if search_type != "asset" else Config.ES_ASSET_INDEX
    retrieve_top_k = max((opts.top_k or 5) * 4, 20)

    # 对每个查询并行检索
    async def retrieve_single(q: str) -> List[Dict[str, Any]]:
        """单个查询的混合检索"""
        try:
            # 生成查询向量（HyDE 或普通 Embedding）
            if opts.use_hyde:
                vector = await get_hyde().generate_vector(q)
            else:
                vector = await _get_embedding().encode(q)

            # 并行执行向量检索和 BM25 检索
            vector_results, es_results = await asyncio.gather(
                _get_milvus().search(
                    collection=collections,
                    query_vector=vector,
                    top_k=retrieve_top_k
                ),
                _run_es_search(es_index, q, retrieve_top_k)
            )

            # RRF 融合
            if es_results:
                return rrf_fusion([vector_results, es_results], k=60)
            return vector_results
        except Exception as e:
            query_logger.warning("[Query] 单次检索失败, query='{}', error={}", q[:50], str(e))
            return []

    # 并行执行所有查询的检索（最多取前 3 个查询避免过多 LLM 调用）
    tasks = [retrieve_single(q) for q in queries[:3]]
    results_per_query = await asyncio.gather(*tasks)

    # 合并所有查询的结果，按 id 去重，保留最高 rrf_score
    merged: Dict[str, Dict[str, Any]] = {}
    for results in results_per_query:
        for item in results:
            doc_id = item.get("id", "")
            if not doc_id:
                continue
            existing = merged.get(doc_id)
            # 保留 rrf_score 更高的版本
            if existing is None or item.get("rrf_score", 0) > existing.get("rrf_score", 0):
                merged[doc_id] = item

    # 按 rrf_score 降序排列
    all_chunks = sorted(merged.values(), key=lambda x: x.get("rrf_score", 0), reverse=True)
    query_logger.info("[Query] 混合检索完成, 合并后 chunk 数={}", len(all_chunks))
    return all_chunks


async def _run_es_search(
    es_index: str,
    query_text: str,
    top_k: int
) -> List[Dict[str, Any]]:
    """
    执行 ES BM25 搜索，失败时降级返回空列表

    @param es_index - ES 索引名
    @param query_text - 查询文本
    @param top_k - 返回数量
    @returns 搜索结果列表
    @author lvdaxianerplus
    @date 2026-05-25
    """
    try:
        es_service = get_es_service()
        return await es_service.search(
            index_name=es_index,
            query=query_text,
            top_k=top_k,
            query_lang="auto"
        )
    except Exception as e:
        query_logger.warning("[Query] ES 搜索失败（降级）, error={}", str(e))
        return []


async def _run_rerank(
    query_text: str,
    chunks: List[Dict[str, Any]],
    opts: QueryOptions
) -> List[Dict[str, Any]]:
    """
    执行 Rerank 重排序，按阈值过滤并截取 top_k

    @param query_text - 查询文本
    @param chunks - 待重排的 chunk 列表
    @param opts - 查询选项
    @returns 重排后的 chunk 列表
    @author lvdaxianerplus
    @date 2026-05-25
    """
    if not chunks:
        return []

    threshold = opts.rerank_threshold if opts.rerank_threshold is not None else 0.3
    top_k = opts.top_k or 5

    try:
        rerank_results = await _get_rerank().rerank(query_text, chunks)
        # 将 rerank 分数写回 chunks
        for r in rerank_results:
            idx = r.get("index")
            if idx is not None and idx < len(chunks):
                chunks[idx]["score"] = r.get("relevance_score", chunks[idx].get("score", 0))

        # 按 score 降序排列，过滤低分，截取 top_k
        sorted_chunks = sorted(chunks, key=lambda x: x.get("score", 0), reverse=True)
        filtered = [c for c in sorted_chunks if c.get("score", 0) >= threshold]
        result = filtered[:top_k]
        query_logger.info(
            "[Query] Rerank 完成: {} -> {} chunks (threshold={}, top_k={})",
            len(chunks), len(result), threshold, top_k
        )
        return result
    except Exception as e:
        query_logger.warning("[Query] Rerank 失败（降级）, error={}", str(e))
        return chunks[:top_k]


async def _run_validation(
    answer: str,
    contexts: List[str],
    query_text: str,
    chunks: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    执行验证层：Faithfulness 检测 + 幻觉过滤

    @param answer - 生成的答案
    @param contexts - 参考上下文列表
    @param query_text - 原始查询
    @param chunks - 检索到的 chunks（用于重新生成时构建上下文）
    @returns 包含 answer、faithfulness_score、passed 的字典
    @author lvdaxianerplus
    @date 2026-05-25
    """
    from app.generation.citation_builder import build_context_with_citations
    from app.generation.generator import GENERATION_PROMPT

    async def regenerate(system_prompt: str) -> str:
        """使用严格 Prompt 重新生成答案"""
        context_with_citations = build_context_with_citations(chunks)
        prompt = GENERATION_PROMPT.format(
            context_with_citations=context_with_citations,
            query=query_text
        )
        from app.services.llm_service import get_llm_service
        return await get_llm_service().chat_simple(prompt, system=system_prompt)

    return await get_hallucination_filter().filter(
        answer=answer,
        contexts=contexts,
        regenerate_fn=regenerate
    )
