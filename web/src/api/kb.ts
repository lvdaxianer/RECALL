/**
 * Recall · 知识库 API 客户端
 *
 * 集中封装 `/api/v1/kb` 系列 REST 接口的请求；调用方拿到的就是干净的 `KnowledgeBase` 视图模型。
 *
 * @author lvdaxianerplus
 */
import { requestJson } from "./client";
import type {
  ApiResponse,
  KnowledgeBase,
  KnowledgeBaseSettings,
  KnowledgeBaseSettingsUpdate,
} from "./types";

/**
 * 列出全部知识库（可选按 owner 过滤）。
 *
 * @param ownerId 可选的所有者 id
 * @returns 知识库列表
 * @author lvdaxianerplus
 */
export async function listKnowledgeBases(ownerId?: string): Promise<KnowledgeBase[]> {
  // ownerId 非空时拼到 query string 上做后端过滤
  const query = ownerId ? `?owner_id=${encodeURIComponent(ownerId)}` : "";
  const response = await requestJson<ApiResponse<KnowledgeBase[]>>(`/api/v1/kb${query}`);
  return response.data;
}

/**
 * 创建新知识库（draft 状态）。
 *
 * @param payload 名称 / 描述 / 所有者
 * @returns 新建的知识库
 * @author lvdaxianerplus
 */
export async function createKnowledgeBase(payload: {
  name: string;
  description: string;
  owner_id: string;
}): Promise<KnowledgeBase> {
  const response = await requestJson<ApiResponse<KnowledgeBase>>("/api/v1/kb", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return response.data;
}

/**
 * 发布知识库（draft → published，触发 embedding + 索引写入）。
 *
 * @param kbId 知识库 id
 * @param ownerId 所有者 id
 * @returns 发布后的知识库
 * @author lvdaxianerplus
 */
export async function publishKnowledgeBase(kbId: string, ownerId: string): Promise<KnowledgeBase> {
  const response = await requestJson<ApiResponse<KnowledgeBase>>(`/api/v1/kb/${kbId}/publish`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ owner_id: ownerId }),
  });
  return response.data;
}

/**
 * 删除知识库（同时清理 chunk + 文档）。
 *
 * @param kbId 知识库 id
 * @param ownerId 所有者 id
 * @returns 删除结果（包含 deleted_document_count / deleted_chunk_count）
 * @author lvdaxianerplus
 */
export async function deleteKnowledgeBase(kbId: string, ownerId: string): Promise<KnowledgeBase> {
  // 走 query string 传 owner_id 是因为部分代理对 DELETE body 解析不佳
  const response = await requestJson<ApiResponse<KnowledgeBase>>(
    `/api/v1/kb/${kbId}?owner_id=${encodeURIComponent(ownerId)}`,
    { method: "DELETE" },
  );
  return response.data;
}

/**
 * 获取知识库的分块设置。
 *
 * @param kbId 知识库 id
 * @returns 知识库分块设置
 * @author lvdaxianerplus
 */
export async function getKnowledgeBaseSettings(kbId: string): Promise<KnowledgeBaseSettings> {
  const response = await requestJson<ApiResponse<KnowledgeBaseSettings>>(`/api/v1/kb/${kbId}/settings`);
  return response.data;
}

/**
 * 更新知识库的分块设置（PATCH，部分字段更新）。
 *
 * @param kbId 知识库 id
 * @param payload 设置 patch
 * @returns 更新后的设置
 * @author lvdaxianerplus
 */
export async function updateKnowledgeBaseSettings(
  kbId: string,
  payload: KnowledgeBaseSettingsUpdate,
): Promise<KnowledgeBaseSettings> {
  const response = await requestJson<ApiResponse<KnowledgeBaseSettings>>(`/api/v1/kb/${kbId}/settings`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return response.data;
}
