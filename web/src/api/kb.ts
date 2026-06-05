import { requestJson } from "./client";
import type { ApiResponse, KnowledgeBase, KnowledgeBaseSettings, KnowledgeBaseSettingsUpdate } from "./types";

export async function listKnowledgeBases(ownerId?: string): Promise<KnowledgeBase[]> {
  const query = ownerId ? `?owner_id=${encodeURIComponent(ownerId)}` : "";
  const response = await requestJson<ApiResponse<KnowledgeBase[]>>(`/api/v1/kb${query}`);
  return response.data;
}

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

export async function publishKnowledgeBase(kbId: string, ownerId: string): Promise<KnowledgeBase> {
  const response = await requestJson<ApiResponse<KnowledgeBase>>(`/api/v1/kb/${kbId}/publish`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ owner_id: ownerId }),
  });
  return response.data;
}

export async function deleteKnowledgeBase(kbId: string, ownerId: string): Promise<KnowledgeBase> {
  const response = await requestJson<ApiResponse<KnowledgeBase>>(
    `/api/v1/kb/${kbId}?owner_id=${encodeURIComponent(ownerId)}`,
    { method: "DELETE" },
  );
  return response.data;
}

export async function getKnowledgeBaseSettings(kbId: string): Promise<KnowledgeBaseSettings> {
  const response = await requestJson<ApiResponse<KnowledgeBaseSettings>>(`/api/v1/kb/${kbId}/settings`);
  return response.data;
}

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
