/**
 * Recall · 聊天模块全局常量
 *
 * 集中管理：后端事件名、用户标识、检索参数选项、阶段标题映射。
 * 替代分散在各页面的魔法字符串与魔法数字。
 *
 * @author lvdaxianerplus
 */

/**
 * 后端流式事件名。集中维护以避免散落字符串不一致。
 *
 * @author lvdaxianerplus
 */
export const STREAM_EVENT = {
  REQUEST_CREATED: "request.created",
  RETRIEVAL_PROGRESS: "retrieval.progress",
  RETRIEVAL_TRACE: "retrieval.trace",
  ANSWER_DELTA: "answer.delta",
  ANSWER_COMPLETED: "answer.completed",
  REQUEST_FAILED: "request.failed",
  ERROR: "error",
} as const;
export type StreamEventName = (typeof STREAM_EVENT)[keyof typeof STREAM_EVENT];

/**
 * 默认用户标识。前端无登录态时使用占位用户，
 * TODO: 接入 auth 后改为 session.user_id。
 *
 * @author lvdaxianerplus
 */
export const DEFAULT_USER_ID = "default";

/**
 * 默认会话 ID：尚未创建后端会话时使用。
 *
 * @author lvdaxianerplus
 */
export const DEFAULT_SESSION_ID = "session-default";

/**
 * 检索条数（topK）可选值。
 *
 * @author lvdaxianerplus
 */
export const TOP_K_OPTIONS = [3, 5, 8, 10] as const;

/**
 * 生成温度可选值。
 *
 * @author lvdaxianerplus
 */
export const TEMPERATURE_OPTIONS = [0, 0.2, 0.5, 0.7, 1] as const;

/**
 * 知识库状态 → UI 状态枚举映射。
 * 集中维护以避免在 StatusBadge / StatusBadge(Recall) / KBListPage / DocumentIngestPage
 * 等多处重复硬编码相同映射。
 *
 * @author lvdaxianerplus
 */
export const KB_STATUS = {
  ACTIVE: "active",
  DELETED: "deleted",
  DRAFT: "draft",
  CHANGED: "changed",
  PUBLISHING: "publishing",
  PUBLISHED: "published",
  PUBLISH_FAILED: "publish_failed",
  ARCHIVED: "archived",
} as const;
export type KbStatus = (typeof KB_STATUS)[keyof typeof KB_STATUS];

/**
 * 知识库状态 → 中文标签。
 *
 * @author lvdaxianerplus
 */
export const KB_STATUS_LABELS: Record<string, string> = {
  [KB_STATUS.ACTIVE]: "兼容可用",
  [KB_STATUS.DELETED]: "已删除",
  [KB_STATUS.DRAFT]: "草稿",
  [KB_STATUS.CHANGED]: "有未发布变更",
  [KB_STATUS.PUBLISHING]: "发布中",
  [KB_STATUS.PUBLISHED]: "已发布",
  [KB_STATUS.PUBLISH_FAILED]: "发布失败",
  [KB_STATUS.ARCHIVED]: "已归档",
};

/**
 * KB 状态 → StatusBadgeVariant 策略映射（替代 if-else 链）。
 *
 * @author lvdaxianerplus
 */
export const KB_STATUS_TO_BADGE: Record<string, "ready" | "error" | "warning" | "info" | "paused" | "neutral"> = {
  [KB_STATUS.PUBLISHED]: "ready",
  [KB_STATUS.ACTIVE]: "ready",
  [KB_STATUS.PUBLISH_FAILED]: "error",
  [KB_STATUS.DELETED]: "error",
  [KB_STATUS.PUBLISHING]: "warning",
  [KB_STATUS.DRAFT]: "warning",
  [KB_STATUS.CHANGED]: "info",
  [KB_STATUS.ARCHIVED]: "paused",
};

/**
 * 文档解析状态。
 *
 * @author lvdaxianerplus
 */
export const PARSE_STATUS = {
  QUEUED: "queued",
  PROCESSING: "processing",
  PARSED: "parsed",
  INDEXED: "indexed",
  FAILED: "failed",
} as const;
export type ParseStatus = (typeof PARSE_STATUS)[keyof typeof PARSE_STATUS];

/**
 * 解析状态 → 中文标签。
 *
 * @author lvdaxianerplus
 */
export const PARSE_STATUS_LABELS: Record<string, string> = {
  [PARSE_STATUS.QUEUED]: "等待解析",
  [PARSE_STATUS.PROCESSING]: "解析中",
  [PARSE_STATUS.PARSED]: "解析成功",
  [PARSE_STATUS.INDEXED]: "解析成功",
  [PARSE_STATUS.FAILED]: "解析失败",
};

/**
 * 解析状态 → Badge variant 策略映射。
 *
 * @author lvdaxianerplus
 */
export const PARSE_STATUS_TO_BADGE: Record<string, "default" | "secondary" | "destructive" | "outline"> = {
  [PARSE_STATUS.FAILED]: "destructive",
  [PARSE_STATUS.QUEUED]: "secondary",
  [PARSE_STATUS.PROCESSING]: "secondary",
  [PARSE_STATUS.PARSED]: "default",
  [PARSE_STATUS.INDEXED]: "default",
};

/**
 * 不可用 KB 状态集合：用于聊天/聊天范围选择中过滤掉未发布 KB。
 *
 * @author lvdaxianerplus
 */
export const UNAVAILABLE_KB_STATUSES: ReadonlySet<string> = new Set([
  KB_STATUS.DELETED,
  KB_STATUS.ARCHIVED,
  KB_STATUS.PUBLISHING,
]);
