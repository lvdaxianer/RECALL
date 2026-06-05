import { requestJson } from "./client";
import type { ApiResponse } from "./types";

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

export async function listAgentSessions(userId: string): Promise<AgentSession[]> {
  const response = await requestJson<ApiResponse<AgentSession[]>>(`/api/v1/agent/${userId}/sessions`);
  return response.data;
}

export async function listAgentRuns(userId: string, sessionId: string): Promise<AgentRun[]> {
  const response = await requestJson<ApiResponse<AgentRun[]>>(
    `/api/v1/agent/${userId}/sessions/${sessionId}/runs`,
  );
  return response.data;
}

export async function listAgentEvents(userId: string, sessionId: string, runId: string): Promise<AgentEvent[]> {
  const response = await requestJson<ApiResponse<AgentEvent[]>>(
    `/api/v1/agent/${userId}/sessions/${sessionId}/events?run_id=${encodeURIComponent(runId)}`,
  );
  return response.data;
}

export async function createAgentSession(
  userId: string,
  payload: { title: string; runtime?: string; metadata?: Record<string, unknown> },
): Promise<AgentSession> {
  const response = await requestJson<ApiResponse<AgentSession>>(`/api/v1/agent/${userId}/sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      runtime: "local",
      metadata: {},
      ...payload,
    }),
  });
  return response.data;
}
