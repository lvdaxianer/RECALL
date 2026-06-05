import { requestJson } from "./client";
import type { ApiResponse } from "./types";

export interface RetrievalResult {
  chunk_id: string;
  knowledge_base_id: string;
  document_name: string;
  title: string;
  content: string;
  score: number;
  score_trace: Record<string, unknown>;
}

export interface RetrievalResponse {
  request_id: string;
  query_scope: "local" | "global" | "hybrid";
  route_plan: { strategy?: string; steps?: string[] };
  filters: { knowledge_base_ids: string[] };
  results: RetrievalResult[];
  trace: Array<Record<string, unknown>>;
}

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
      body: JSON.stringify({ vote: payload.vote, user_id: payload.user_id ?? "default" }),
    },
  );
  return response.data;
}

export async function listAnswerCache(): Promise<{ items: AnswerCacheRecord[]; total: number }> {
  const response = await requestJson<ApiResponse<{ items: AnswerCacheRecord[]; total: number }>>(
    "/api/v1/retrieval/answers/cache",
  );
  return response.data;
}

export async function deleteAnswerCache(cacheKey: string): Promise<Record<string, unknown>> {
  const response = await requestJson<ApiResponse<Record<string, unknown>>>(
    `/api/v1/retrieval/answers/cache/${encodeURIComponent(cacheKey)}`,
    { method: "DELETE" },
  );
  return response.data;
}
