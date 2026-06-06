import { useCallback, useEffect, useState } from "react";

import {
  createAgentSession,
  listAgentEvents,
  listAgentRuns,
  listAgentSessions,
  type AgentEvent,
  type AgentRun,
} from "../../api/sessions";
import { DEFAULT_SESSION_ID, DEFAULT_USER_ID } from "./runtime/chatConstants";
import {
  createDefaultSession,
  fromAgentSession,
  getErrorMessage,
  type ChatMessage,
  type ChatSession,
} from "./runtime/chatModels";


/**
 * 把 runs + events 展开为前端消息列表（user 配 assistant）。
 *
 * @param runs 会话中的运行记录
 * @param eventsByRun 按 run_id 分组的事件
 * @author lvdaxianerplus
 */
function messagesFromRuns(runs: AgentRun[], eventsByRun: Record<string, AgentEvent[]>): ChatMessage[] {
  return [...runs]
    .reverse()
    .flatMap((run) => [
      {
        id: `${run.run_id}-user`,
        role: "user" as const,
        content: run.input,
        status: "success" as const,
      },
      {
        id: `${run.run_id}-assistant`,
        role: "assistant" as const,
        content: run.answer || (run.status === "failed" ? "生成失败，请重试。" : "正在生成..."),
        status: run.status === "failed" ? "error" as const : "success" as const,
        trace: eventsByRun[run.run_id] ?? [],
        requestId: run.request_id,
        showThinking: false,
      },
    ]);
}

/**
 * 批量并发加载每个 run 的事件列表。失败时使用空数组。
 *
 * @param sessionId 会话 id
 * @param runs 运行列表
 * @author lvdaxianerplus
 */
async function loadRunEvents(
  sessionId: string,
  runs: AgentRun[],
): Promise<Record<string, AgentEvent[]>> {
  const entries = await Promise.all(
    runs.map(async (run) => {
      try {
        return [run.run_id, await listAgentEvents(DEFAULT_USER_ID, sessionId, run.run_id)] as const;
      } catch {
        return [run.run_id, []] as const;
      }
    }),
  );
  return Object.fromEntries(entries);
}

/**
 * useChatSessions 返回值。
 *
 * @author lvdaxianerplus
 */
export interface UseChatSessionsResult {
  sessions: ChatSession[];
  activeSessionId: string;
  activeSession: ChatSession;
  setActiveSessionId: (id: string) => void;
  updateActiveSession: (patch: Partial<ChatSession>) => void;
  appendMessage: (message: ChatMessage) => void;
  updateMessage: (messageId: string, patch: Partial<ChatMessage>) => void;
  loadSessions: () => Promise<void>;
  loadSessionRuns: (sessionId: string) => Promise<void>;
  handleNewSession: (publishedKbIds: string[]) => Promise<void>;
  sessionError: string | null;
}

/**
 * 聊天会话管理 hook：封装会话列表、当前会话、消息增删改、加载/新建等副作用。
 *
 * @author lvdaxianerplus
 */
export function useChatSessions(isOpen: boolean): UseChatSessionsResult {
  const [sessions, setSessions] = useState<ChatSession[]>([createDefaultSession()]);
  const [activeSessionId, setActiveSessionId] = useState(DEFAULT_SESSION_ID);
  const [sessionError, setSessionError] = useState<string | null>(null);
  const activeSession = sessions.find((session) => session.id === activeSessionId) ?? sessions[0];

  /**
   * 打开抽屉时同步拉一次会话列表。
   *
   * @author lvdaxianerplus
   */
  useEffect(() => {
    if (!isOpen) {
      return;
    }
    void loadSessions();
  }, [isOpen]);

  /**
   * 切换到非默认会话时拉取历史 runs。
   *
   * @author lvdaxianerplus
   */
  useEffect(() => {
    if (!isOpen || !activeSessionId || activeSessionId === DEFAULT_SESSION_ID) {
      return;
    }
    void loadSessionRuns(activeSessionId);
  }, [isOpen, activeSessionId]);

  /**
   * 加载后端会话列表。失败时把错误暴露给 UI。
   *
   * @author lvdaxianerplus
   */
  const loadSessions = useCallback(async () => {
    setSessionError(null);
    try {
      const remoteSessions = await listAgentSessions(DEFAULT_USER_ID);
      if (remoteSessions.length === 0) {
        return;
      }
      const nextSessions = remoteSessions.map(fromAgentSession);
      setSessions(nextSessions);
      setActiveSessionId(nextSessions[0].id);
    } catch (error) {
      setSessionError(getErrorMessage(error, "加载会话失败"));
    }
  }, []);

  /**
   * 加载指定会话的所有 run + events。
   *
   * @param sessionId 会话 id
   * @author lvdaxianerplus
   */
  const loadSessionRuns = useCallback(async (sessionId: string) => {
    try {
      const runs = await listAgentRuns(DEFAULT_USER_ID, sessionId);
      const eventsByRun = await loadRunEvents(sessionId, runs);
      setSessions((current) =>
        current.map((session) =>
          session.id === sessionId ? { ...session, messages: messagesFromRuns(runs, eventsByRun) } : session,
        ),
      );
    } catch {
      // 静默：列表已有本地默认数据，无需打断用户
    }
  }, []);

  /**
   * 更新当前会话的部分字段。
   *
   * @param patch 字段 patch
   * @author lvdaxianerplus
   */
  const updateActiveSession = useCallback(
    (patch: Partial<ChatSession>) => {
      setSessions((current) =>
        current.map((session) => (session.id === activeSessionId ? { ...session, ...patch } : session)),
      );
    },
    [activeSessionId],
  );

  /**
   * 在当前会话末尾追加一条消息。
   *
   * @param message 新消息
   * @author lvdaxianerplus
   */
  const appendMessage = useCallback(
    (message: ChatMessage) => {
      setSessions((current) =>
        current.map((session) =>
          session.id === activeSessionId ? { ...session, messages: [...session.messages, message] } : session,
        ),
      );
    },
    [activeSessionId],
  );

  /**
   * 更新当前会话中指定消息的字段。
   *
   * @param messageId 消息 id
   * @param patch 字段 patch
   * @author lvdaxianerplus
   */
  const updateMessage = useCallback(
    (messageId: string, patch: Partial<ChatMessage>) => {
      setSessions((current) =>
        current.map((session) =>
          session.id === activeSessionId
            ? {
                ...session,
                messages: session.messages.map((message) =>
                  message.id === messageId ? { ...message, ...patch } : message,
                ),
              }
            : session,
        ),
      );
    },
    [activeSessionId],
  );

  /**
   * 创建新会话（先尝试后端，失败时本地占位）。
   *
   * @param publishedKbIds 已发布 KB id 列表（用于默认选中）
   * @author lvdaxianerplus
   */
  const handleNewSession = useCallback(async (publishedKbIds: string[]) => {
    const kbIds = publishedKbIds.length > 0 ? [publishedKbIds[0]] : [];
    try {
      const remoteSession = await createAgentSession(DEFAULT_USER_ID, {
        title: "新的检索会话",
        metadata: { knowledge_base_ids: kbIds },
      });
      const next = fromAgentSession(remoteSession);
      setSessions((current) => [{ ...next, kbIds }, ...current]);
      setActiveSessionId(next.id);
    } catch (error) {
      const fallbackId = `session-${Date.now()}`;
      setSessions((current) => [
        { id: fallbackId, title: "新的检索会话", kbIds, messages: [] },
        ...current,
      ]);
      setActiveSessionId(fallbackId);
      setSessionError(getErrorMessage(error, "新建会话失败，已使用本地占位"));
    }
  }, []);

  return {
    sessions,
    activeSessionId,
    activeSession,
    setActiveSessionId,
    updateActiveSession,
    appendMessage,
    updateMessage,
    loadSessions,
    loadSessionRuns,
    handleNewSession,
    sessionError,
  };
}
