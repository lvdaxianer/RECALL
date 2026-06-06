/**
 * Recall · 聊天助手（抽屉形态）
 *
 * 全局挂载在 App.tsx 根节点；通过 isOpen 状态控制抽屉开合。
 * 抽屉展开后是三栏 grid：会话列表（260） + 对话（1fr） + 证据（360，按需展示）。
 *
 * 核心设计：
 * 1. 会话状态 / 加载流 / 反馈队列分别走自定义 hook（useChatSessions / useFeedbackSubmit）
 * 2. 流式回答走独立模块 streamAssistantAnswer（纯函数 + 回调），与 useChatSessions 解耦
 * 3. AssistantRuntimeProvider 仅在抽屉打开时挂载，确保 ComposerPrimitive 有 AuiProvider
 * 4. 进度回调 buildMessageProgressHandler / 完成回调 buildMessageCompleteHandler 工厂化
 * 5. 悬浮按钮（关闭时）走右下角 fixed，不参与抽屉结构
 * 6. KB 范围自动选中第一个已发布 KB（首次进入时）
 * 7. KB 选择变化同步到 useChatSessions 的 updateActiveSession（不重新初始化）
 * 8. 错误状态：sendError / sessionError 分两条横幅展示，不抢同一位置
 * 9. 抽屉宽度 1180px 上限（不超过视口 - 28px），适应大屏
 * 10. useEffect 监听 isOpen 自动加载会话列表
 * 11. useCallback 稳定 handleSend 引用，避免 ChatComposer 每次重建
 *
 * @author lvdaxianerplus
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { MessageSquare } from "lucide-react";
import { AssistantRuntimeProvider } from "@assistant-ui/react";

import { ErrorState } from "../../components/common/ErrorState";
import { LoadingState } from "../../components/common/LoadingState";
import { useKnowledgeBases } from "../../hooks/useKnowledgeBases";
import type { StreamState } from "../../hooks/useRetrievalStream";
import { ChatComposer } from "./components/ChatComposer";
import { ChatScopeSelector } from "./components/ChatScopeSelector";
import { ChatThread } from "./components/ChatThread";
import { ChatAssistantHeader } from "./components/ChatAssistantHeader";
import { ChatSessionList } from "./components/ChatSessionList";
import { ChatEvidencePanel } from "./components/ChatEvidencePanel";
import { streamAssistantAnswer } from "./streamAssistantAnswer";
import { DEFAULT_USER_ID } from "./runtime/chatConstants";
import { getLatestProgressSummary } from "./runtime/chatHelpers";
import {
  buildMessageCompleteHandler,
  buildMessageProgressHandler,
} from "./runtime/streamHandlers";
import { isPublishedKnowledgeBase, type ChatMessage } from "./runtime/chatModels";
import { useChatSessions } from "./useChatSessions";
import { useFeedbackSubmit } from "./useFeedbackSubmit";
import { useRecallAssistantRuntime } from "./runtime/useRecallAssistantRuntime";

/**
 * Recall 聊天助手。
 *
 * 布局：右滑抽屉（最大 1180px），三栏 = 会话列表 · 对话 · 证据。
 * 每栏自带 elevation / border，跟主页面节奏一致。
 *
 * @author lvdaxianerplus
 */
export function ChatAssistant() {
  const { items: knowledgeBases, isLoading, isError, refetch } = useKnowledgeBases();
  const [isOpen, setIsOpen] = useState(false);
  const [streamState, setStreamState] = useState<StreamState>({
    status: "idle",
    output: "",
    events: [],
  });
  const [evidenceEvents, setEvidenceEvents] = useState<Parameters<typeof ChatEvidencePanel>[0]["events"]>(null);
  const [evidenceOpen, setEvidenceOpen] = useState(true);
  const [topK, setTopK] = useState(5);
  const [temperature, setTemperature] = useState(0.2);
  const [useContext, setUseContext] = useState(false);
  const [sendError, setSendError] = useState<string | null>(null);

  const {
    sessions,
    activeSessionId,
    activeSession,
    setActiveSessionId,
    updateActiveSession,
    appendMessage,
    updateMessage,
    handleNewSession,
    sessionError,
  } = useChatSessions(isOpen);

  const { handleFeedback, flushPendingFeedback } = useFeedbackSubmit({
    messages: activeSession.messages,
    selectedKbIds: activeSession.kbIds,
    activeSessionId,
    topK,
    temperature,
    useContext,
    updateMessage,
    setStreamState,
  });

  const [draft, setDraft] = useState("");
  const publishedKbIds = useMemo(
    () => knowledgeBases.filter(isPublishedKnowledgeBase).map((item) => item.id),
    [knowledgeBases],
  );
  const selectedKbIds = activeSession.kbIds;
  const canSend = draft.trim().length > 0 && selectedKbIds.length > 0 && streamState.status !== "streaming";

  // 包装 @assistant-ui 的本地 runtime，使 ChatComposer 内的 ComposerPrimitive 可用；
  // 同时让本地 store 跟随 ChatThread 渲染出的消息刷新。
  const assistantMessages = useMemo<ChatMessage[]>(() => activeSession.messages, [activeSession.messages]);
  const assistantRuntime = useRecallAssistantRuntime({
    // @assistant-ui/react 的 ThreadMessageLike 状态枚举与本地 ChatMessage 略有差异；
    // 本地 ChatMessage 多了 "error"，此处转为 ThreadMessageLike 兼容的子集。
    messages: assistantMessages as unknown as Parameters<typeof useRecallAssistantRuntime>[0]["messages"],
    request: {
      knowledge_base_ids: selectedKbIds,
      top_k: topK,
      temperature,
      use_context: useContext,
      user_id: DEFAULT_USER_ID,
      session_id: activeSessionId,
    },
  });

  /**
   * 首次进入时如果当前会话没有 KB 且存在已发布 KB，自动选中第一个。
   *
   * @author lvdaxianerplus
   */
  useEffect(() => {
    if (!activeSession) {
      return;
    }
    if (selectedKbIds.length > 0) {
      return;
    }
    if (publishedKbIds.length === 0) {
      return;
    }
    updateActiveSession({ kbIds: [publishedKbIds[0]] });
  }, [activeSession?.id, publishedKbIds]);

  /**
   * 提交用户输入并启动一次流式检索。
   *
   * @author lvdaxianerplus
   */
  async function handleSend(): Promise<void> {
    const question = draft.trim();
    if (!question || selectedKbIds.length === 0) {
      return;
    }
    setSendError(null);
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
    await streamAssistantAnswer({
      question,
      assistantMessageId,
      knowledgeBaseIds: selectedKbIds,
      historyQuestions,
      topK,
      temperature,
      useContext,
      userId: DEFAULT_USER_ID,
      sessionId: activeSessionId,
      onState: setStreamState,
      onProgress: buildMessageProgressHandler(assistantMessageId, (id, patch) => {
        updateMessage(id, patch);
      }),
      onComplete: buildMessageCompleteHandler(
        assistantMessageId,
        (id, patch) => {
          updateMessage(id, patch);
        },
        ({ completedRequestId }) => {
          void flushPendingFeedback(assistantMessageId, completedRequestId);
        },
      ),
    });
  }

  // 把 onSend 的 useCallback 提前稳定引用，避免 ChatComposer 每次都重建。
  const handleSendCallback = useCallback(() => {
    void handleSend();
  }, [
    draft,
    selectedKbIds,
    topK,
    temperature,
    useContext,
    activeSession?.id,
    activeSession?.messages,
  ]);

  // 1. 抽屉关闭时只渲染右下角悬浮按钮（避免抽屉结构进入 DOM）
  if (!isOpen) {
    return (
      <button
        aria-label="打开 Recall 助手"
        // 悬浮按钮：右下角圆形 emerald，hover 缩放
        className="fixed bottom-7 right-7 z-40 grid size-14 place-items-center rounded-full border border-emerald-600 bg-emerald-600 text-lg font-bold text-white shadow-lg shadow-emerald-900/30 transition-all duration-200 hover:scale-105 hover:bg-emerald-700 hover:shadow-xl hover:shadow-emerald-900/40"
        type="button"
        onClick={() => setIsOpen(true)}
      >
        <MessageSquare aria-hidden="true" className="size-6" />
      </button>
    );
  }

  return (
    // AssistantRuntimeProvider 为 ComposerPrimitive 提供 AuiProvider
    <AssistantRuntimeProvider runtime={assistantRuntime}>
      <section
        aria-label="Recall 助手"
        aria-modal="true"
        // 抽屉：固定定位 + 桌面 1180px 上限（不超过视口 - 28px）
        className="fixed inset-y-0 right-0 z-50 flex w-full flex-col border-l border-slate-200 bg-slate-50 shadow-2xl shadow-slate-900/30 ring-1 ring-slate-900/5 sm:w-[min(1180px,calc(100vw-28px))]"
        data-assistant-ui-runtime="local"
        role="dialog"
      >
        <ChatAssistantHeader
          evidenceOpen={evidenceOpen}
          onClose={() => setIsOpen(false)}
          onToggleEvidence={() => setEvidenceOpen((current) => !current)}
        />

        {/* 三栏 grid：会话列表 260 / 对话 1fr / 证据 360（按 evidenceOpen 条件追加） */}
        <div
          className="grid min-h-0 flex-1"
          style={{ gridTemplateColumns: `260px minmax(0,1fr)${evidenceOpen ? " 360px" : ""}` }}
        >
          <ChatSessionList
            activeSessionId={activeSessionId}
            onCreateSession={() => void handleNewSession(publishedKbIds)}
            onSelectSession={setActiveSessionId}
            publishedKbCount={publishedKbIds.length}
            sessions={sessions}
          />

          {/* 中间栏：KB 选择 + 消息 + 输入 */}
          <div className="flex min-h-0 flex-col">
            {/* 顶部：KB 范围选择 + 加载态 */}
            <div className="border-b border-slate-200 bg-white px-5 py-3">
              <ChatScopeSelector
                knowledgeBases={knowledgeBases}
                onChange={(kbIds) => updateActiveSession({ kbIds })}
                value={selectedKbIds}
              />
              {isLoading ? <LoadingState label="加载可用知识库中" /> : null}
              {isError ? <ErrorState title="知识库加载失败" onRetry={refetch} /> : null}
            </div>
            {/* 主体：消息线程 */}
            <div className="min-h-0 flex-1 overflow-hidden bg-slate-50">
              <ChatThread
                getProgressText={(message) => getLatestProgressSummary(message.trace)}
                messages={activeSession.messages as ChatMessage[]}
                onFeedback={(messageId, requestId, vote) => void handleFeedback(messageId, requestId, vote)}
                // 打开证据时同时确保证据面板展开
                onOpenEvidence={(events) => {
                  setEvidenceEvents(events);
                  setEvidenceOpen(true);
                }}
                onPrompt={setDraft}
                publishedKbCount={publishedKbIds.length}
              />
            </div>
            {/* 底部：输入区 */}
            <ChatComposer
              canSend={canSend}
              draft={draft}
              isStreaming={streamState.status === "streaming"}
              onDraftChange={setDraft}
              onSend={handleSendCallback}
              onTemperatureChange={setTemperature}
              onTopKChange={setTopK}
              onUseContextChange={setUseContext}
              selectedKbCount={selectedKbIds.length}
              temperature={temperature}
              topK={topK}
              useContext={useContext}
            />
          </div>

          {/* 右侧栏：证据面板（按需渲染） */}
          {evidenceOpen ? (
            <ChatEvidencePanel
              events={evidenceEvents}
              isOpen={evidenceOpen}
              onClose={() => setEvidenceOpen(false)}
            />
          ) : null}
        </div>

        {sendError ? (
          <div
            aria-live="assertive"
            className="border-t border-red-200 bg-red-50 px-5 py-2 text-sm text-red-700"
            role="alert"
          >
            {sendError}
          </div>
        ) : null}
        {sessionError ? (
          <div
            aria-live="polite"
            className="border-t border-amber-200 bg-amber-50 px-5 py-2 text-sm text-amber-700"
            role="status"
          >
            {sessionError}
          </div>
        ) : null}
      </section>
    </AssistantRuntimeProvider>
  );
}
