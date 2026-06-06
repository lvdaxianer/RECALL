import type { AgentEvent } from "../../../api/sessions";
import type { AgentSession } from "../../../api/sessions";
import type { KnowledgeBase } from "../../../api/types";
import { DEFAULT_SESSION_ID } from "./chatConstants";

/**
 * 单条聊天消息的视图模型。
 *
 * @author lvdaxianerplus
 */
export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  status?: "streaming" | "success" | "error";
  trace?: AgentEvent[];
  durationMs?: number;
  requestId?: string | null;
  feedbackStatus?: "liked" | "disliked" | "queued" | "error";
  sourceQuestion?: string;
  knowledgeBaseIds?: string[];
  showThinking?: boolean;
}

/**
 * 单个会话的视图模型。
 *
 * @author lvdaxianerplus
 */
export interface ChatSession {
  id: string;
  title: string;
  kbIds: string[];
  messages: ChatMessage[];
  createdAt?: string;
}

/**
 * 创建默认空会话。
 *
 * @author lvdaxianerplus
 */
export function createDefaultSession(): ChatSession {
  return {
    id: DEFAULT_SESSION_ID,
    title: "新的检索会话",
    kbIds: [],
    messages: [],
  };
}

/**
 * 把后端 AgentSession 转为前端 ChatSession。
 *
 * @param session 后端会话
 * @author lvdaxianerplus
 */
export function fromAgentSession(session: AgentSession): ChatSession {
  return {
    id: session.session_id,
    title: session.title || "新的检索会话",
    kbIds: Array.isArray(session.metadata.knowledge_base_ids)
      ? session.metadata.knowledge_base_ids.map(String)
      : [],
    messages: [],
  };
}

/**
 * 取 assistant 消息对应的上一条 user 消息（用于点踩重跑）。
 *
 * @param messages 会话消息
 * @param assistantMessageId 当前 assistant 消息 id
 * @author lvdaxianerplus
 */
export function findPreviousUserQuestion(messages: ChatMessage[], assistantMessageId: string): string {
  const index = messages.findIndex((message) => message.id === assistantMessageId);
  if (index <= 0) {
    return "";
  }
  for (let cursor = index - 1; cursor >= 0; cursor -= 1) {
    if (messages[cursor].role === "user") {
      return messages[cursor].content;
    }
  }
  return "";
}

/**
 * 知识库是否对聊天可见。
 *
 * @param item 知识库
 * @author lvdaxianerplus
 */
export function isPublishedKnowledgeBase(item: KnowledgeBase): boolean {
  return item.status === "published";
}

/**
 * 把任意 error 转成可展示字符串。
 *
 * @param error 异常对象
 * @param fallback 兜底文案
 * @author lvdaxianerplus
 */
export function getErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message) {
    return error.message;
  }
  return fallback;
}
