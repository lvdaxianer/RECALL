import { requestJson } from "./client";
import type { ApiResponse } from "./types";

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

export interface SynonymGroupPayload {
  knowledge_base_id?: string | null;
  canonical?: string;
  terms?: string[];
  owner_id?: string;
  enabled?: boolean;
}

export async function listSynonymGroups(params?: { knowledge_base_id?: string }): Promise<SynonymGroup[]> {
  const query = params?.knowledge_base_id ? `?knowledge_base_id=${encodeURIComponent(params.knowledge_base_id)}` : "";
  const response = await requestJson<ApiResponse<SynonymGroup[]>>(`/api/v1/synonyms${query}`);
  return response.data;
}

export async function createSynonymGroup(payload: SynonymGroupPayload): Promise<SynonymGroup> {
  const response = await requestJson<ApiResponse<SynonymGroup>>("/api/v1/synonyms", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return response.data;
}

export async function updateSynonymGroup(id: string, payload: SynonymGroupPayload): Promise<SynonymGroup> {
  const response = await requestJson<ApiResponse<SynonymGroup>>(`/api/v1/synonyms/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return response.data;
}

export async function deleteSynonymGroup(id: string): Promise<{ id: string }> {
  const response = await requestJson<ApiResponse<{ id: string }>>(`/api/v1/synonyms/${id}`, {
    method: "DELETE",
  });
  return response.data;
}
