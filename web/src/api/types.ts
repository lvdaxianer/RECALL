export const KnowledgeBaseStatus = {
  Active: "active",
  Deleted: "deleted",
  Draft: "draft",
  Publishing: "publishing",
  Published: "published",
  PublishFailed: "publish_failed",
  Archived: "archived",
  Changed: "changed",
} as const;

export type KnowledgeBaseStatusValue = (typeof KnowledgeBaseStatus)[keyof typeof KnowledgeBaseStatus];

export interface KnowledgeBase {
  id: string;
  name: string;
  description: string;
  owner_id: string;
  status: KnowledgeBaseStatusValue;
  deleted_document_count?: number;
  deleted_chunk_count?: number;
}

export interface KnowledgeBaseSettings {
  knowledge_base_id: string;
  semantic_chunking_enabled: boolean;
  chunk_size: number;
  overlap: number;
  top_k_default: number;
  max_heading_depth: number;
  llm_planning_timeout_ms: number;
  updated_at: string;
}

export type KnowledgeBaseSettingsUpdate = Partial<
  Pick<
    KnowledgeBaseSettings,
    | "semantic_chunking_enabled"
    | "chunk_size"
    | "overlap"
    | "top_k_default"
    | "max_heading_depth"
    | "llm_planning_timeout_ms"
  >
>;

export interface ApiResponse<T> {
  code: number;
  message: string;
  data: T;
}
