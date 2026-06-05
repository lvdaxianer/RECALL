import { requestJson } from "./client";
import type { ApiResponse } from "./types";

export type DocumentParseStatus = "queued" | "processing" | "parsed" | "indexed" | "failed";

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

export interface KnowledgeChunk {
  id: string;
  document_id?: string;
  chunk_index: number;
  title: string;
  content: string;
  token_count?: number;
  created_at?: string;
}

export async function listDocuments(kbId: string): Promise<KnowledgeDocument[]> {
  const response = await requestJson<ApiResponse<KnowledgeDocument[]>>(`/api/v1/kb/${kbId}/documents`);
  return response.data;
}

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

export async function listDocumentChunks(kbId: string, documentId: string): Promise<KnowledgeChunk[]> {
  const response = await requestJson<ApiResponse<KnowledgeChunk[]>>(
    `/api/v1/kb/${kbId}/documents/${documentId}/chunks`,
  );
  return response.data;
}
