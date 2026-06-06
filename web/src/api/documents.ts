/**
 * Recall · 文档 / Chunk API 客户端
 *
 * 封装 `/api/v1/kb/{kbId}/documents[/{docId}/chunks]` 系列接口。
 *
 * @author lvdaxianerplus
 */
import { requestJson } from "./client";
import type { ApiResponse } from "./types";

/**
 * 文档解析状态枚举（与后端枚举保持一致）。
 *
 * @author lvdaxianerplus
 */
export type DocumentParseStatus = "queued" | "processing" | "parsed" | "indexed" | "failed";

/**
 * 知识库文档视图模型。
 *
 * @author lvdaxianerplus
 */
export interface KnowledgeDocument {
  id: string;
  knowledge_base_id?: string;
  document_name: string;
  content_type?: string;
  status: string;
  chunk_count: number;
  parse_status?: DocumentParseStatus;
  parse_attempts?: number;
  parse_error?: string | null;
  queued_at?: string | null;
  processing_started_at?: string | null;
  parsed_at?: string | null;
  indexed_at?: string | null;
  created_at?: string;
  updated_at?: string;
}

/**
 * 文档分块视图模型。
 *
 * @author lvdaxianerplus
 */
export interface KnowledgeChunk {
  id: string;
  document_id?: string;
  chunk_index: number;
  title: string;
  content: string;
  token_count?: number;
  created_at?: string;
}

/**
 * 列出知识库下的所有文档。
 *
 * @param kbId 知识库 id
 * @returns 文档列表
 * @author lvdaxianerplus
 */
export async function listDocuments(kbId: string): Promise<KnowledgeDocument[]> {
  const response = await requestJson<ApiResponse<KnowledgeDocument[]>>(`/api/v1/kb/${kbId}/documents`);
  return response.data;
}

/**
 * 上传一份新文档到指定知识库。
 *
 * @param kbId 知识库 id
 * @param payload 文档内容 + 元信息
 * @returns 上传后的文档
 * @author lvdaxianerplus
 */
export async function uploadDocument(
  kbId: string,
  payload: { name: string; content: string; content_type: string; owner_id: string },
): Promise<KnowledgeDocument> {
  const response = await requestJson<ApiResponse<KnowledgeDocument>>(`/api/v1/kb/${kbId}/documents`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return response.data;
}

/**
 * 列出指定文档的所有分块。
 *
 * @param kbId 知识库 id
 * @param documentId 文档 id
 * @returns Chunk 列表
 * @author lvdaxianerplus
 */
export async function listDocumentChunks(kbId: string, documentId: string): Promise<KnowledgeChunk[]> {
  const response = await requestJson<ApiResponse<KnowledgeChunk[]>>(
    `/api/v1/kb/${kbId}/documents/${documentId}/chunks`,
  );
  return response.data;
}
