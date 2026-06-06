/**
 * Recall · 同义词组 API 客户端
 *
 * 封装 `/api/v1/synonyms` 系列接口。SynonymGroup 用于 query 归一化与缓存 key 归一化。
 *
 * @author lvdaxianerplus
 */
import { requestJson } from "./client";
import type { ApiResponse } from "./types";

/**
 * 同义词组视图模型。
 *
 * @author lvdaxianerplus
 */
export interface SynonymGroup {
  id: string;
  knowledge_base_id: string | null;
  canonical: string;
  terms: string[];
  owner_id: string;
  enabled: boolean;
  created_at?: string;
  updated_at?: string;
}

/**
 * 同义词组写入 payload（创建 / 更新共用）。
 *
 * @author lvdaxianerplus
 */
export interface SynonymGroupPayload {
  knowledge_base_id?: string | null;
  canonical?: string;
  terms?: string[];
  owner_id?: string;
  enabled?: boolean;
}

/**
 * 列出同义词组。
 *
 * @param params.knowledge_base_id 可选按 KB 过滤
 * @returns 同义词组列表
 * @author lvdaxianerplus
 */
export async function listSynonymGroups(params?: { knowledge_base_id?: string }): Promise<SynonymGroup[]> {
  // 按 KB 过滤时把 id 编码后拼到 query string
  const query = params?.knowledge_base_id ? `?knowledge_base_id=${encodeURIComponent(params.knowledge_base_id)}` : "";
  const response = await requestJson<ApiResponse<SynonymGroup[]>>(`/api/v1/synonyms${query}`);
  return response.data;
}

/**
 * 创建同义词组。
 *
 * @param payload 同义词组配置
 * @returns 新建的同义词组
 * @author lvdaxianerplus
 */
export async function createSynonymGroup(payload: SynonymGroupPayload): Promise<SynonymGroup> {
  const response = await requestJson<ApiResponse<SynonymGroup>>("/api/v1/synonyms", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return response.data;
}

/**
 * 更新同义词组（PATCH）。
 *
 * @param id 同义词组 id
 * @param payload 字段 patch
 * @returns 更新后的同义词组
 * @author lvdaxianerplus
 */
export async function updateSynonymGroup(id: string, payload: SynonymGroupPayload): Promise<SynonymGroup> {
  const response = await requestJson<ApiResponse<SynonymGroup>>(`/api/v1/synonyms/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return response.data;
}

/**
 * 删除同义词组。
 *
 * @param id 同义词组 id
 * @returns 包含被删 id 的确认
 * @author lvdaxianerplus
 */
export async function deleteSynonymGroup(id: string): Promise<{ id: string }> {
  const response = await requestJson<ApiResponse<{ id: string }>>(`/api/v1/synonyms/${id}`, {
    method: "DELETE",
  });
  return response.data;
}
