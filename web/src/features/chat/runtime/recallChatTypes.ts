/**
 * Recall · 聊天 run 状态公共类型
 *
 * 被 recallStreamAdapter / useRecallAssistantRuntime / 业务组件共用。
 *
 * @author lvdaxianerplus
 */
import type { StreamEvent } from "../../../hooks/useRetrievalStream";

/**
 * 聊天抽屉 run 状态枚举。
 *
 * @author lvdaxianerplus
 */
export type RecallRunStatus = "idle" | "streaming" | "success" | "error";

/**
 * 引用条目（来自 `answer.completed.payload.results`）。
 *
 * @author lvdaxianerplus
 */
export type RecallCitation = {
  chunk_id?: string;
  document_name?: string;
  title?: string;
  content?: string;
  score?: number;
};

/**
 * 聊天抽屉 run 状态模型。
 *
 * @author lvdaxianerplus
 */
export type RecallRunState = {
  /** 用户原始问题 */
  question: string;
  /** 后端分配的 request id（用于反馈 / 重跑） */
  requestId: string | null;
  /** 累积的回答文本 */
  content: string;
  /** 当前状态 */
  status: RecallRunStatus;
  /** 累积的 stream 事件 */
  trace: StreamEvent[];
  /** 引用条目 */
  citations: RecallCitation[];
  /** 错误消息 */
  error?: string;
};
