import { useEffect, useMemo, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import {
  createAgentSession,
  listAgentEvents,
  listAgentRuns,
  type AgentEvent,
  listAgentSessions,
  type AgentRun,
  type AgentSession,
} from "../../api/sessions";
import { sendAnswerFeedback } from "../../api/retrieval";
import type { KnowledgeBase } from "../../api/types";
import { ErrorState } from "../../components/common/ErrorState";
import { LoadingState } from "../../components/common/LoadingState";
import { useKnowledgeBases } from "../../hooks/useKnowledgeBases";
import { appendStreamEvent, readRetrievalStream, type StreamState } from "../../hooks/useRetrievalStream";

interface ChatMessage {
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

interface CitationItem {
  chunk_id?: string;
  document_name?: string;
  title?: string;
  content?: string;
  snippet?: string;
  score?: number;
}

interface ChatSession {
  id: string;
  title: string;
  kbIds: string[];
  messages: ChatMessage[];
}

const DEFAULT_SESSION_ID = "session-default";
const CHAT_USER_ID = "default";

function createDefaultSession(): ChatSession {
  return {
    id: DEFAULT_SESSION_ID,
    title: "新的检索会话",
    kbIds: [],
    messages: [],
  };
}

function fromAgentSession(session: AgentSession): ChatSession {
  return {
    id: session.session_id,
    title: session.title || "新的检索会话",
    kbIds: Array.isArray(session.metadata.knowledge_base_ids)
      ? session.metadata.knowledge_base_ids.map(String)
      : [],
    messages: [],
  };
}

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

function isPublishedKnowledgeBase(item: KnowledgeBase): boolean {
  return item.status === "published";
}

function getDisabledReason(item: KnowledgeBase): string | undefined {
  if (isPublishedKnowledgeBase(item)) {
    return undefined;
  }
  return `${item.name}不可用于聊天`;
}

function getTraceTitle(stage: string): string {
  const titles: Record<string, string> = {
    query_scope: "查询范围",
    candidate_scoring: "候选评分",
    engine_fallback: "降级检索",
  };
  return titles[stage] ?? stage;
}

function getCitationItems(events: AgentEvent[]): CitationItem[] {
  return events.flatMap((event) => {
    const results = event.payload.results;
    if (event.event === "answer.completed" && Array.isArray(results)) {
      return results.map((item) => item as CitationItem);
    }
    return [];
  });
}

function getCitationScore(score?: number): string {
  return typeof score === "number" ? score.toFixed(3) : "-";
}

function getCitationSnippet(item: CitationItem): string {
  return String(item.content ?? item.snippet ?? item.chunk_id ?? "-");
}

function formatDuration(durationMs: number): string {
  if (durationMs >= 1000) {
    return `${(durationMs / 1000).toFixed(2)}s`;
  }
  return `${Math.max(0, Math.round(durationMs))}ms`;
}

function getFeedbackText(status?: ChatMessage["feedbackStatus"]): string | null {
  if (status === "liked") {
    return "已增加信任权重";
  }
  if (status === "disliked") {
    return "这题不算，我让它重新想一遍";
  }
  if (status === "queued") {
    return "反馈会在回答完成后提交";
  }
  if (status === "error") {
    return "反馈提交失败";
  }
  return null;
}

function getLatestProgressSummary(events: AgentEvent[] | undefined): string {
  const progress = [...(events ?? [])]
    .reverse()
    .find((event) => event.event === "retrieval.progress" && typeof event.payload.summary === "string");
  return typeof progress?.payload.summary === "string" ? progress.payload.summary : "正在检索证据";
}

function getThinkingTitle(isStreaming: boolean): string {
  return isStreaming ? "思考中" : "已完成思考";
}

function getProgressSummary(summary: unknown, stage: unknown): string {
  const stageText = String(stage ?? "");
  const raw = String(summary ?? "");
  if (stageText === "query_scope" || raw.includes("检索范围")) {
    return "正在判断这个问题适合怎么查";
  }
  if (stageText === "retrieval" || raw.includes("召回")) {
    return "正在从选中的知识库里查找相关资料";
  }
  if (stageText === "answer_generation" || raw.includes("组织回答")) {
    return "已找到可用资料，正在整理回答";
  }
  return raw || "正在处理检索请求";
}

function getTraceSummary(trace: { stage?: string; summary?: string; metrics?: Record<string, unknown> }): string {
  const stage = String(trace.stage ?? "");
  const metrics = trace.metrics ?? {};
  if (stage === "query_scope") {
    const queryScope = String(metrics.query_scope ?? "");
    if (queryScope === "global") {
      return "这个问题需要先看知识库整体概览";
    }
    if (queryScope === "hybrid") {
      return "这个问题会同时查概览和具体片段";
    }
    return "已判断检索方式，准备查找相关资料";
  }
  if (stage === "candidate_scoring") {
    const engine = String(metrics.engine ?? "");
    if (engine.includes("rerank")) {
      return "正在把候选资料按相关性重新排序";
    }
    if (engine.includes("fallback") || engine.includes("sqlite")) {
      return "外部检索暂不可用，已改用本地资料匹配";
    }
    return "正在筛选最可能有帮助的资料";
  }
  if (stage === "engine_fallback") {
    return "外部检索暂不可用，已切换备用检索方式";
  }
  if (stage === "answer_cache") {
    return "命中以前验证过的回答，可以更快返回";
  }
  return String(trace.summary ?? "已完成一个检索步骤");
}

function getThinkingSteps(events: AgentEvent[] | undefined): Array<{ summary: string; meta?: string }> {
  const steps: Array<{ summary: string; meta?: string }> = [];
  let hasAnswerDelta = false;
  for (const event of events ?? []) {
    if (event.event === "request.created") {
      const input = typeof event.payload.input === "string" ? event.payload.input : "";
      steps.push({ summary: input ? `收到问题：「${input}」` : "收到问题，准备进入检索链路" });
    } else if (event.event === "retrieval.progress") {
      steps.push({
        summary: getProgressSummary(event.payload.summary, event.payload.stage),
      });
    } else if (event.event === "retrieval.trace" && Array.isArray(event.payload.trace)) {
      for (const item of event.payload.trace) {
        const trace = item as { stage?: string; summary?: string; metrics?: Record<string, unknown> };
        steps.push({
          summary: getTraceSummary(trace),
        });
      }
    } else if (event.event === "answer.delta" && !hasAnswerDelta) {
      hasAnswerDelta = true;
      steps.push({ summary: "开始根据证据流式组织回答" });
    } else if (event.event === "answer.completed") {
      steps.push({
        summary: "回答完成，已整理引用来源",
      });
    }
  }
  return steps.length > 0 ? steps : [{ summary: "正在准备检索链路" }];
}

function findPreviousUserQuestion(messages: ChatMessage[], assistantMessageId: string): string {
  const index = messages.findIndex((message) => message.id === assistantMessageId);
  if (index <= 0) {
    return "";
  }
  for (let cursor = index - 1; cursor >= 0; cursor -= 1) {
    const message = messages[cursor];
    if (message.role === "user") {
      return message.content;
    }
  }
  return "";
}

function getTraceItems(events: AgentEvent[]): Array<{ title: string; summary: string; meta?: string }> {
  return events.flatMap((event) => {
    if (event.event === "retrieval.trace" && Array.isArray(event.payload.trace)) {
      return event.payload.trace.map((item) => {
        const trace = item as { stage?: string; summary?: string; metrics?: Record<string, unknown> };
        return {
          title: getTraceTitle(String(trace.stage ?? "trace")),
          summary: String(trace.summary ?? "已记录检索阶段"),
          meta: trace.metrics ? JSON.stringify(trace.metrics) : undefined,
        };
      });
    }
    if (event.event === "retrieval.progress") {
      return [{
        title: getTraceTitle(String(event.payload.stage ?? "retrieval.progress")),
        summary: String(event.payload.summary ?? "检索处理中"),
      }];
    }
    if (event.event === "answer.delta" && event.payload.chunk_id) {
      const summary = String(
        event.payload.content ??
          event.payload.snippet ??
          event.payload.text ??
          event.payload.title ??
          "已命中片段",
      );
      return [{
        title: "命中片段",
        summary,
        meta: `chunk_id: ${String(event.payload.chunk_id)}`,
      }];
    }
    return [];
  });
}

function TraceDetails({ events }: { events: AgentEvent[] }) {
  const items = getTraceItems(events);
  const citations = getCitationItems(events);
  if (items.length === 0 && citations.length === 0) {
    return <span className="muted-text">暂无 trace</span>;
  }
  return (
    <div className="trace-detail-stack">
      {citations.length > 0 ? (
        <section className="citation-list">
          <strong>引用来源</strong>
          <div className="citation-table-wrap">
            <table className="citation-table">
              <thead>
                <tr>
                  <th>文档</th>
                  <th>标题</th>
                  <th>命中片段</th>
                  <th>分数</th>
                </tr>
              </thead>
              <tbody>
                {citations.map((item, index) => (
                  <tr key={`${item.chunk_id ?? "citation"}-${index}`}>
                    <td>{item.document_name ?? "-"}</td>
                    <td>{item.title ?? "-"}</td>
                    <td>{getCitationSnippet(item)}</td>
                    <td>{getCitationScore(item.score)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}
      <div className="trace-card-list">
        {items.map((item, index) => (
          <div className="trace-card" key={`${item.title}-${index}`}>
            <strong>{item.title}</strong>
            <span>{item.summary}</span>
            {item.meta ? <small>{item.meta}</small> : null}
          </div>
        ))}
      </div>
    </div>
  );
}

function ThinkingPanel({
  events,
  isStreaming,
}: {
  events: AgentEvent[] | undefined;
  isStreaming: boolean;
}) {
  const steps = getThinkingSteps(events);
  return (
    <details className="chat-thinking" open={isStreaming}>
      <summary>
        <span className="streaming-dot" aria-hidden="true" />
        <strong>{getThinkingTitle(isStreaming)}</strong>
      </summary>
      <ol className="chat-thinking__steps">
        {steps.map((step, index) => (
          <li key={`${step.summary}-${index}`}>
            <span>{step.summary}</span>
            {step.meta ? <small>{step.meta}</small> : null}
          </li>
        ))}
      </ol>
      {isStreaming ? (
        <div className="chat-thinking__loading">
          <span className="streaming-dot" aria-hidden="true" />
          <span>检索中，请稍候…</span>
        </div>
      ) : null}
    </details>
  );
}

function MarkdownAnswer({
  content,
  isStreaming,
  progressText,
}: {
  content: string;
  isStreaming: boolean;
  progressText: string;
}) {
  if (!content.trim() && isStreaming) {
    return null;
  }

  return (
    <div className="chat-answer">
      {isStreaming ? (
        <div className="chat-answer__status">
          <span className="streaming-dot" aria-hidden="true" />
          <span>{progressText}</span>
        </div>
      ) : null}
      {content.trim() ? (
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          components={{
            a: ({ children, href }) => (
              <a href={href} rel="noreferrer" target="_blank">
                {children}
              </a>
            ),
            img: ({ alt, src }) => <img alt={alt ?? ""} loading="lazy" src={src ?? ""} />,
          }}
        >
          {content}
        </ReactMarkdown>
      ) : null}
    </div>
  );
}

function ChatScopePicker({
  knowledgeBases,
  value,
  onChange,
}: {
  knowledgeBases: KnowledgeBase[];
  value: string[];
  onChange: (value: string[]) => void;
}) {
  const [isExpanded, setIsExpanded] = useState(false);
  const [query, setQuery] = useState("");
  const selectedItems = knowledgeBases.filter((item) => value.includes(item.id));
  const publishedCount = knowledgeBases.filter(isPublishedKnowledgeBase).length;
  const filteredItems = knowledgeBases.filter((item) => item.name.toLowerCase().includes(query.trim().toLowerCase()));
  const selectedSummary = selectedItems.length > 0
    ? selectedItems.slice(0, 2).map((item) => item.name).join("、")
    : "未选择知识库";
  const overflowCount = selectedItems.length - 2;

  function toggle(item: KnowledgeBase) {
    if (!isPublishedKnowledgeBase(item)) {
      return;
    }
    if (value.includes(item.id)) {
      onChange(value.filter((id) => id !== item.id));
    } else {
      onChange([...value, item.id]);
    }
  }

  return (
    <section className="chat-scope">
      <button
        aria-expanded={isExpanded}
        className="chat-scope__summary"
        type="button"
        onClick={() => setIsExpanded((current) => !current)}
      >
        <span>
          <strong>知识库范围</strong>
          <small>
            已选 {selectedItems.length} 个 · 可用 {publishedCount} 个
          </small>
        </span>
        <em>
          {selectedSummary}
          {overflowCount > 0 ? ` 等 ${selectedItems.length} 个` : ""}
        </em>
      </button>
      {isExpanded ? (
        <div className="chat-scope__panel">
          <label className="chat-scope__search">
            <span>搜索知识库</span>
            <input
              aria-label="搜索知识库"
              placeholder="按名称过滤"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
          </label>
          <div className="chat-scope__list">
            {filteredItems.length > 0 ? filteredItems.map((item) => (
              <label className="chat-scope__item" key={item.id}>
                <input
                  aria-label={item.name}
                  checked={value.includes(item.id)}
                  disabled={!isPublishedKnowledgeBase(item)}
                  type="checkbox"
                  onChange={() => toggle(item)}
                />
                <span>
                  <strong>{item.name}</strong>
                  <small>{isPublishedKnowledgeBase(item) ? "已发布，可用于聊天" : getDisabledReason(item)}</small>
                </span>
              </label>
            )) : <span className="muted-text">没有匹配的知识库</span>}
          </div>
          <button className="icon-button" type="button" onClick={() => setIsExpanded(false)}>
            收起知识库范围
          </button>
        </div>
      ) : null}
    </section>
  );
}

export function ChatAssistant() {
  const { items: knowledgeBases, isLoading, isError, refetch } = useKnowledgeBases();
  const [isOpen, setIsOpen] = useState(false);
  const [sessions, setSessions] = useState<ChatSession[]>([createDefaultSession()]);
  const [activeSessionId, setActiveSessionId] = useState(DEFAULT_SESSION_ID);
  const [draft, setDraft] = useState("");
  const [streamState, setStreamState] = useState<StreamState>({
    status: "idle",
    output: "",
    events: [],
  });
  const [evidenceEvents, setEvidenceEvents] = useState<AgentEvent[] | null>(null);
  const [topK, setTopK] = useState(5);
  const [temperature, setTemperature] = useState(0.2);
  const [useContext, setUseContext] = useState(false);
  const pendingFeedbackRef = useRef<Record<string, "like" | "dislike">>({});
  const publishedKbIds = useMemo(
    () => knowledgeBases.filter(isPublishedKnowledgeBase).map((item) => item.id),
    [knowledgeBases],
  );
  const activeSession = sessions.find((session) => session.id === activeSessionId) ?? sessions[0];
  const selectedKbIds = activeSession?.kbIds ?? [];
  const canSend = draft.trim().length > 0 && selectedKbIds.length > 0 && streamState.status !== "streaming";

  useEffect(() => {
    if (!isOpen) {
      return;
    }
    void loadSessions();
  }, [isOpen]);

  useEffect(() => {
    if (!activeSession || selectedKbIds.length > 0 || publishedKbIds.length === 0) {
      return;
    }
    updateActiveSession({ kbIds: [publishedKbIds[0]] });
  }, [activeSession?.id, publishedKbIds.join(","), selectedKbIds.length]);

  useEffect(() => {
    if (!isOpen || !activeSessionId || activeSessionId === DEFAULT_SESSION_ID) {
      return;
    }
    void loadSessionRuns(activeSessionId);
  }, [isOpen, activeSessionId]);

  function updateActiveSession(patch: Partial<ChatSession>) {
    setSessions((current) =>
      current.map((session) => (session.id === activeSessionId ? { ...session, ...patch } : session)),
    );
  }

  async function loadSessions() {
    try {
      const remoteSessions = await listAgentSessions(CHAT_USER_ID);
      if (remoteSessions.length === 0) {
        return;
      }
      const nextSessions = remoteSessions.map(fromAgentSession);
      setSessions(nextSessions);
      setActiveSessionId(nextSessions[0].id);
    } catch {
      return;
    }
  }

  async function loadSessionRuns(sessionId: string) {
    try {
      const runs = await listAgentRuns(CHAT_USER_ID, sessionId);
      const eventsByRun = await loadRunEvents(sessionId, runs);
      setSessions((current) =>
        current.map((session) =>
          session.id === sessionId ? { ...session, messages: messagesFromRuns(runs, eventsByRun) } : session,
        ),
      );
    } catch {
      return;
    }
  }

  async function loadRunEvents(sessionId: string, runs: AgentRun[]): Promise<Record<string, AgentEvent[]>> {
    const entries = await Promise.all(
      runs.map(async (run) => {
        try {
          return [run.run_id, await listAgentEvents(CHAT_USER_ID, sessionId, run.run_id)] as const;
        } catch {
          return [run.run_id, []] as const;
        }
      }),
    );
    return Object.fromEntries(entries);
  }

  function appendMessage(message: ChatMessage) {
    setSessions((current) =>
      current.map((session) =>
        session.id === activeSessionId ? { ...session, messages: [...session.messages, message] } : session,
      ),
    );
  }

  function updateMessage(messageId: string, patch: Partial<ChatMessage>) {
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
  }

  async function handleNewSession() {
    const kbIds = publishedKbIds.length > 0 ? [publishedKbIds[0]] : [];
    const nextSession = await createSession(kbIds);
    setSessions((current) => [nextSession, ...current]);
    setActiveSessionId(nextSession.id);
    setDraft("");
    setStreamState({ status: "idle", output: "", events: [] });
  }

  async function createSession(kbIds: string[]): Promise<ChatSession> {
    try {
      const remoteSession = await createAgentSession(CHAT_USER_ID, {
        title: "新的检索会话",
        metadata: { knowledge_base_ids: kbIds },
      });
      const nextSession = fromAgentSession(remoteSession);
      return { ...nextSession, kbIds };
    } catch {
      return {
        id: `session-${Date.now()}`,
        title: "新的检索会话",
        kbIds,
        messages: [],
      };
    }
  }

  async function handleSend() {
    const question = draft.trim();
    if (!question || selectedKbIds.length === 0) {
      return;
    }
    const assistantMessageId = `assistant-${Date.now()}`;
    const historyQuestions = activeSession.messages
      .filter((message) => message.role === "user")
      .map((message) => message.content)
      .filter(Boolean)
      .slice(-3);
    appendMessage({ id: `user-${Date.now()}`, role: "user", content: question });
    appendMessage({
      id: assistantMessageId,
      role: "assistant",
      content: "",
      status: "streaming",
      sourceQuestion: question,
      knowledgeBaseIds: selectedKbIds,
      showThinking: true,
    });
    setDraft("");
    await streamAssistantAnswer(question, assistantMessageId, selectedKbIds, historyQuestions);
  }

  async function streamAssistantAnswer(
    question: string,
    assistantMessageId: string,
    knowledgeBaseIds: string[],
    historyQuestions: string[] = [],
  ) {
    const startedAt = Date.now();
    setStreamState({ status: "streaming", output: "", events: [], startedAt });
    let nextState: StreamState = { status: "streaming", output: "", events: [], startedAt };
    try {
      await readRetrievalStream(
        {
          input: question,
          knowledge_base_ids: knowledgeBaseIds,
          top_k: topK,
          temperature,
          use_context: useContext,
          history_questions: useContext ? historyQuestions : undefined,
          user_id: CHAT_USER_ID,
          session_id: activeSessionId,
        },
        (event) => {
          nextState = appendStreamEvent(nextState, event);
          setStreamState(nextState);
          updateMessage(assistantMessageId, {
            content: nextState.output,
            status: nextState.status === "error" ? "error" : "streaming",
            requestId: event.request_id ?? nextState.events.find((item) => item.request_id)?.request_id ?? null,
            trace: nextState.events.map((streamEvent, index) => ({
              event_id: `stream-${index}`,
              event: streamEvent.event,
              user_id: CHAT_USER_ID,
              session_id: activeSessionId,
              run_id: null,
              request_id: streamEvent.request_id ?? null,
              sequence: index + 1,
              payload: streamEvent.payload,
              created_at: "",
            })),
          });
        },
      );
      const finishedAt = Date.now();
      const durationMs = finishedAt - startedAt;
      const completedRequestId = [...nextState.events].reverse().find((event) => event.request_id)?.request_id ?? null;
      updateMessage(assistantMessageId, {
        content: nextState.output || "未检索到可用回答",
        status: "success",
        durationMs,
        requestId: completedRequestId,
      });
      setStreamState((state) => ({
        ...state,
        status: state.status === "error" ? "error" : "success",
        finishedAt,
        durationMs,
      }));
      const pendingVote = pendingFeedbackRef.current[assistantMessageId];
      if (completedRequestId && pendingVote) {
        delete pendingFeedbackRef.current[assistantMessageId];
        void submitFeedback(assistantMessageId, completedRequestId, pendingVote, { rerunOnDislike: pendingVote === "dislike" });
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : "生成失败，请重试。";
      const durationMs = Date.now() - startedAt;
      updateMessage(assistantMessageId, { content: message, status: "error", durationMs });
      setStreamState({ status: "error", output: "", events: [], error: message, startedAt, durationMs });
    }
  }

  async function submitFeedback(
    messageId: string,
    requestId: string,
    vote: "like" | "dislike",
    options: { rerunOnDislike: boolean },
  ) {
    try {
      const feedback = await sendAnswerFeedback({ request_id: requestId, vote, user_id: CHAT_USER_ID });
      if (vote === "dislike" && feedback.deleted !== true) {
        throw new Error("答案缓存未删除");
      }
      updateMessage(messageId, { feedbackStatus: vote === "like" ? "liked" : "disliked" });
      if (vote === "dislike" && options.rerunOnDislike) {
        const message = activeSession.messages.find((item) => item.id === messageId);
        const question = message?.sourceQuestion ?? findPreviousUserQuestion(activeSession.messages, messageId);
        const knowledgeBaseIds = message?.knowledgeBaseIds ?? selectedKbIds;
        if (!question || knowledgeBaseIds.length === 0) {
          throw new Error("缺少重新检索上下文");
        }
        updateMessage(messageId, {
          content: "",
          status: "streaming",
          trace: [],
          durationMs: undefined,
          requestId: null,
          showThinking: true,
        });
        await streamAssistantAnswer(question, messageId, knowledgeBaseIds);
      }
    } catch {
      updateMessage(messageId, { feedbackStatus: "error" });
    }
  }

  async function handleFeedback(messageId: string, requestId: string | null | undefined, vote: "like" | "dislike") {
    const message = activeSession.messages.find((item) => item.id === messageId);
    if (!requestId || message?.status === "streaming") {
      pendingFeedbackRef.current[messageId] = vote;
      updateMessage(messageId, { feedbackStatus: "queued" });
      return;
    }
    await submitFeedback(messageId, requestId, vote, { rerunOnDislike: true });
  }

  return (
    <>
      <button
        aria-label="打开 Recall 助手"
        className="chat-launcher"
        type="button"
        onClick={() => setIsOpen(true)}
      >
        <span aria-hidden="true">Q</span>
      </button>
      {isOpen ? (
        <section aria-label="Recall 助手" aria-modal="true" className="chat-panel" role="dialog">
          <header className="chat-panel__header">
            <div>
              <small>Retrieval Copilot</small>
              <strong>Recall 助手</strong>
              <span>证据优先回答</span>
              <span>只检索已发布知识库</span>
            </div>
            <div className="chat-panel__actions">
              <label>
                <span>会话</span>
                <select value={activeSessionId} onChange={(event) => setActiveSessionId(event.target.value)}>
                  {sessions.map((session) => (
                    <option key={session.id} value={session.id}>
                      {session.title}
                    </option>
                  ))}
                </select>
              </label>
              <button className="icon-button" type="button" onClick={handleNewSession}>
                新建会话
              </button>
              <button aria-label="关闭 Recall 助手" className="icon-button" type="button" onClick={() => setIsOpen(false)}>
                关闭
              </button>
            </div>
          </header>
          <div className="chat-panel__kb">
            <ChatScopePicker
              knowledgeBases={knowledgeBases}
              value={selectedKbIds}
              onChange={(kbIds) => updateActiveSession({ kbIds })}
            />
            {isLoading ? <LoadingState label="加载可用知识库中" /> : null}
            {isError ? <ErrorState title="知识库加载失败" onRetry={refetch} /> : null}
          </div>
          <div className="chat-messages" aria-live="polite">
            {activeSession.messages.length === 0 ? (
              <div className="chat-empty">
                <strong>{publishedKbIds.length > 0 ? "选择知识库后开始提问" : "暂无可检索的已发布知识库"}</strong>
                <button type="button" onClick={() => setDraft("这个知识库主要包含什么？")}>
                  这个知识库主要包含什么？
                </button>
                <button type="button" onClick={() => setDraft("帮我查找 ES 过滤字段怎么配置")}>
                  帮我查找 ES 过滤字段怎么配置
                </button>
              </div>
            ) : (
              activeSession.messages.map((message) => (
                <article className={`chat-message chat-message--${message.role}`} key={message.id}>
                  <span>{message.role === "user" ? "你" : "Recall"}</span>
                  {message.role === "assistant" ? (
                    <>
                      {message.showThinking ? (
                        <ThinkingPanel
                          events={message.trace}
                          isStreaming={message.status === "streaming"}
                        />
                      ) : null}
                      <MarkdownAnswer
                        content={message.content}
                        isStreaming={message.status === "streaming"}
                        progressText={getLatestProgressSummary(message.trace)}
                      />
                    </>
                  ) : (
                    <p>{message.content}</p>
                  )}
                  {message.role === "assistant" ? (
                    <div className="chat-message__meta">
                      {message.durationMs !== undefined ? <span>耗时 {formatDuration(message.durationMs)}</span> : null}
                      <button
                        aria-label="点赞这条回答"
                        className="chat-feedback-button"
                        type="button"
                        onClick={() => void handleFeedback(message.id, message.requestId, "like")}
                      >
                        👍
                      </button>
                      <button
                        aria-label="点踩并重新检索"
                        className="chat-feedback-button"
                        type="button"
                        onClick={() => void handleFeedback(message.id, message.requestId, "dislike")}
                      >
                        👎
                      </button>
                      {getFeedbackText(message.feedbackStatus) ? <span>{getFeedbackText(message.feedbackStatus)}</span> : null}
                    </div>
                  ) : null}
                  {message.role === "assistant" ? (
                    <button
                      className="chat-evidence-button"
                      type="button"
                      onClick={() => setEvidenceEvents((message.trace as AgentEvent[] | undefined) ?? [])}
                    >
                      查看证据与 Trace
                    </button>
                  ) : null}
                </article>
              ))
            )}
          </div>
          <footer className="chat-composer">
            <div className="chat-composer__controls">
              <label>
                <span>检索条数</span>
                <select
                  aria-label="检索条数"
                  value={topK}
                  onChange={(event) => setTopK(Number(event.target.value))}
                >
                  <option value={3}>3</option>
                  <option value={5}>5</option>
                  <option value={8}>8</option>
                  <option value={10}>10</option>
                </select>
              </label>
              <label>
                <span>生成温度</span>
                <select
                  aria-label="生成温度"
                  value={temperature}
                  onChange={(event) => setTemperature(Number(event.target.value))}
                >
                  <option value={0}>0.0</option>
                  <option value={0.2}>0.2</option>
                  <option value={0.5}>0.5</option>
                  <option value={0.7}>0.7</option>
                  <option value={1}>1.0</option>
                </select>
              </label>
              <label className="check-row">
                <input
                  aria-label="关联上下文"
                  checked={useContext}
                  type="checkbox"
                  onChange={(event) => setUseContext(event.target.checked)}
                />
                <span>关联上下文</span>
              </label>
            </div>
            <label>
              <span className="sr-only">输入问题</span>
              <textarea
                aria-label="输入问题"
                placeholder="输入问题，Shift + Enter 换行..."
                rows={3}
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
              />
            </label>
            <button className="button" type="button" disabled={!canSend} onClick={handleSend}>
              {streamState.status === "streaming" ? "生成中" : "发送"}
            </button>
            <span className="chat-composer__meta">已选 {selectedKbIds.length} 个已发布知识库</span>
          </footer>
          {evidenceEvents ? (
            <aside aria-label="证据与 Trace" aria-modal="true" className="evidence-drawer" role="dialog">
              <header>
                <div>
                  <small>Evidence</small>
                  <strong>证据与 Trace</strong>
                </div>
                <button className="icon-button" type="button" onClick={() => setEvidenceEvents(null)}>
                  关闭
                </button>
              </header>
              <div className="evidence-drawer__body">
                <TraceDetails events={evidenceEvents} />
              </div>
            </aside>
          ) : null}
        </section>
      ) : null}
    </>
  );
}
