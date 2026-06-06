/**
 * Recall · 共享 API 类型
 *
 * 集中维护：知识库状态枚举 + 知识库视图模型 + 分块设置 + 通用 ApiResponse 信封。
 *
 * @author lvdaxianerplus
 */

/**
 * 知识库状态枚举（与后端枚举严格一致）。
 *
 * @author lvdaxianerplus
 */
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

/**
 * 知识库状态联合类型。
 *
 * @author lvdaxianerplus
 */
export type KnowledgeBaseStatusValue = (typeof KnowledgeBaseStatus)[keyof typeof KnowledgeBaseStatus];

/**
 * 知识库视图模型。
 *
 * @author lvdaxianerplus
 */
export interface KnowledgeBase {
  id: string;
  name: string;
  description: string;
  owner_id: string;
  status: KnowledgeBaseStatusValue;
  deleted_document_count?: number;
  deleted_chunk_count?: number;
}

/**
 * 知识库分块设置视图模型。
 *
 * @author lvdaxianerplus
 */
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

/**
 * 知识库分块设置的 PATCH payload 类型（所有字段可选）。
 *
 * @author lvdaxianerplus
 */
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

/**
 * 通用 API 响应信封 `{ code, message, data }`。
 *
 * @author lvdaxianerplus
 */
export interface ApiResponse<T> {
  code: number;
  message: string;
  data: T;
}
