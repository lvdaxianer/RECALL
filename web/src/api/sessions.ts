/**
 * Recall · Agent 会话 / Run / Event API 客户端
 *
 * 封装 `/api/v1/agent/{userId}/sessions[/{sessionId}/runs[/{runId}/events]]` 系列接口。
 * 用于聊天抽屉的历史回放。
 *
 * @author lvdaxianerplus
 */
import { requestJson } from "./client";
import type { ApiResponse } from "./types";

/**
 * Agent 会话视图模型。
 *
 * @author lvdaxianerplus
 */
export interface AgentSession {
  session_id: string;
  user_id: string;
  runtime_id: string;
  title: string | null;
  status: "active" | "closed";
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

/**
 * 单次 run 视图模型：含 input / answer / 状态 / 元数据。
 *
 * @author lvdaxianerplus
 */
export interface AgentRun {
  run_id: string;
  user_id: string;
  session_id: string;
  request_id: string | null;
  input: string;
  status: "queued" | "running" | "completed" | "failed" | "cancelled";
  tools: string[];
  answer: string | null;
  error: Record<string, unknown> | null;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

/**
 * 流式事件视图模型（后端持久化的回放事件）。
 *
 * @author lvdaxianerplus
 */
export interface AgentEvent {
  event_id: string;
  event: string;
  user_id: string;
  session_id: string | null;
  run_id: string | null;
  request_id: string | null;
  sequence: number;
  payload: Record<string, unknown>;
  created_at: string;
}

/**
 * 列出某用户全部会话。
 *
 * @param userId 用户 id
 * @returns 会话列表
 * @author lvdaxianerplus
 */
export async function listAgentSessions(userId: string): Promise<AgentSession[]> {
  const response = await requestJson<ApiResponse<AgentSession[]>>(`/api/v1/agent/${userId}/sessions`);
  return response.data;
}

/**
 * 列出指定会话下的全部 run。
 *
 * @param userId 用户 id
 * @param sessionId 会话 id
 * @returns run 列表
 * @author lvdaxianerplus
 */
export async function listAgentRuns(userId: string, sessionId: string): Promise<AgentRun[]> {
  const response = await requestJson<ApiResponse<AgentRun[]>>(
    `/api/v1/agent/${userId}/sessions/${sessionId}/runs`,
  );
  return response.data;
}

/**
 * 列出指定 run 下的全部事件（用于历史回放 + trace 展示）。
 *
 * @param userId 用户 id
 * @param sessionId 会话 id
 * @param runId run id
 * @returns 事件列表（按 sequence 升序）
 * @author lvdaxianerplus
 */
export async function listAgentEvents(userId: string, sessionId: string, runId: string): Promise<AgentEvent[]> {
  // run_id 通过 query string 传，避免某些代理对路径段含 / 的解析
  const response = await requestJson<ApiResponse<AgentEvent[]>>(
    `/api/v1/agent/${userId}/sessions/${sessionId}/events?run_id=${encodeURIComponent(runId)}`,
  );
  return response.data;
}

/**
 * 创建新会话。
 *
 * @param userId 用户 id
 * @param payload 会话元数据
 * @returns 新建的会话
 * @author lvdaxianerplus
 */
export async function createAgentSession(
  userId: string,
  payload: { title: string; runtime?: string; metadata?: Record<string, unknown> },
): Promise<AgentSession> {
  const response = await requestJson<ApiResponse<AgentSession>>(`/api/v1/agent/${userId}/sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    // 强制 runtime=local（前端聊天抽屉的本地 runtime），允许上层覆盖 metadata
    body: JSON.stringify({
      runtime: "local",
      metadata: {},
      ...payload,
    }),
  });
  return response.data;
}
