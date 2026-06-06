/**
 * Recall · 检索 / 答案缓存 API 客户端
 *
 * 封装 `/api/v1/retrieval/*` 系列接口：非流式搜索、反馈、答案缓存管理。
 * 流式接口见 `hooks/useRetrievalStream.ts`。
 *
 * @author lvdaxianerplus
 */
import { requestJson } from "./client";
import type { ApiResponse } from "./types";

/**
 * 检索结果单条：包含 chunk 元信息 + 评分 trace。
 *
 * @author lvdaxianerplus
 */
export interface RetrievalResult {
  chunk_id: string;
  knowledge_base_id: string;
  document_name: string;
  title: string;
  content: string;
  score: number;
  score_trace: Record<string, unknown>;
}

/**
 * 检索响应：route_plan + score trace + 命中结果。
 *
 * @author lvdaxianerplus
 */
export interface RetrievalResponse {
  request_id: string;
  query_scope: "local" | "global" | "hybrid";
  route_plan: { strategy?: string; steps?: string[] };
  filters: { knowledge_base_ids: string[] };
  results: RetrievalResult[];
  trace: Array<Record<string, unknown>>;
}

/**
 * 答案缓存单条记录。
 *
 * @author lvdaxianerplus
 */
export interface AnswerCacheRecord {
  cache_key: string;
  normalized_query: string;
  knowledge_base_ids: string[];
  answer_preview: string;
  citation_count: number;
  request_id: string;
  trust_score: number;
  hit_count: number;
  expires_at: string;
  updated_at: string;
}

/**
 * 非流式检索接口。
 *
 * @param payload 问题 + KB + topK
 * @returns 检索响应（含 route_plan / score trace / 命中）
 * @author lvdaxianerplus
 */
export async function searchRetrieval(payload: {
  input: string;
  knowledge_base_ids: string[];
  top_k: number;
}): Promise<RetrievalResponse> {
  const response = await requestJson<ApiResponse<RetrievalResponse>>("/api/v1/retrieval/search", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return response.data;
}

/**
 * 提交点赞/点踩反馈。
 *
 * @param payload.request_id 关联的请求 id
 * @param payload.vote like / dislike
 * @param payload.user_id 可选用户 id
 * @returns 服务端响应（包含 trust_score / deleted 等）
 * @author lvdaxianerplus
 */
export async function sendAnswerFeedback(payload: {
  request_id: string;
  vote: "like" | "dislike";
  user_id?: string;
}): Promise<Record<string, unknown>> {
  const response = await requestJson<ApiResponse<Record<string, unknown>>>(
    `/api/v1/retrieval/answers/${encodeURIComponent(payload.request_id)}/feedback`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      // user_id 缺省时回退到占位用户 "default"
      body: JSON.stringify({ vote: payload.vote, user_id: payload.user_id ?? "default" }),
    },
  );
  return response.data;
}

/**
 * 列出答案缓存。
 *
 * @returns 缓存条目数组 + 总数
 * @author lvdaxianerplus
 */
export async function listAnswerCache(): Promise<{ items: AnswerCacheRecord[]; total: number }> {
  const response = await requestJson<ApiResponse<{ items: AnswerCacheRecord[]; total: number }>>(
    "/api/v1/retrieval/answers/cache",
  );
  return response.data;
}

/**
 * 删除指定 cache_key 的答案缓存。
 *
 * @param cacheKey 缓存 key（归一化 query 哈希）
 * @returns 服务端响应
 * @author lvdaxianerplus
 */
export async function deleteAnswerCache(cacheKey: string): Promise<Record<string, unknown>> {
  // 路径段需要 URL 编码以防 cache_key 包含特殊字符
  const response = await requestJson<ApiResponse<Record<string, unknown>>>(
    `/api/v1/retrieval/answers/cache/${encodeURIComponent(cacheKey)}`,
    { method: "DELETE" },
  );
  return response.data;
}
