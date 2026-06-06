import {
  appendStreamEvent,
  readRetrievalStream,
  type StreamEvent,
  type StreamState,
} from "../../hooks/useRetrievalStream";
import type { AgentEvent } from "../../api/sessions";

/**
 * 流式检索参数（不含 input）。
 *
 * @author lvdaxianerplus
 */
export type StreamRequestBase = Omit<Parameters<typeof readRetrievalStream>[0], "input">;

/**
 * 把后端 stream 事件包装成 AgentEvent 视图。
 * 注意：`event_id` 用 stream 序号生成，便于 UI key。
 *
 * @param streamEvent 后端流事件
 * @param index 序号
 * @author lvdaxianerplus
 */
function toAgentEvent(streamEvent: StreamEvent, index: number): AgentEvent {
  return {
    event_id: `stream-${index}`,
    event: streamEvent.event,
    user_id: "",
    session_id: null,
    run_id: null,
    request_id: streamEvent.request_id ?? null,
    sequence: index + 1,
    payload: streamEvent.payload,
    created_at: "",
  };
}

/**
 * 流式检索助手回答配置对象。
 *
 * @author lvdaxianerplus
 */
export interface StreamAssistantParams {
  question: string;
  assistantMessageId: string;
  knowledgeBaseIds: string[];
  historyQuestions?: string[];
  topK: number;
  temperature: number;
  useContext: boolean;
  deepSearchEnabled: boolean;
  userId: string;
  sessionId: string;
  /** 收到每条流事件时回调（用于更新 stream state / 消息内容）。 */
  onProgress: (params: {
    nextState: StreamState;
    nextAgentEvents: AgentEvent[];
    rawEvent: StreamEvent;
  }) => void;
  /** 状态变化回调，用于把 stream 进度写到外层 setState。 */
  onState: (state: StreamState) => void;
  /** 完成时回调（成功 / 失败）。 */
  onComplete: (params: {
    finalState: StreamState;
    completedRequestId: string | null;
    durationMs: number;
    errorMessage?: string;
  }) => void;
}

/**
 * 启动一次流式检索回答。所有副作用通过回调抛给调用方，本函数保持纯逻辑。
 *
 * @param params 流式配置
 * @author lvdaxianerplus
 */
export async function streamAssistantAnswer(params: StreamAssistantParams): Promise<void> {
  // 1. 解构 + 兜底默认
  const {
    question,
    knowledgeBaseIds,
    historyQuestions = [],
    topK,
    temperature,
    useContext,
    deepSearchEnabled,
    userId,
    sessionId,
    onProgress,
    onState,
    onComplete,
  } = params;
  // 2. 记下起始时间，用于计算总耗时
  const startedAt = Date.now();
  // 3. 初始化流式状态 + 立刻推一次 streaming 给 UI（让用户看到"已开始"）
  const initialState: StreamState = { status: "streaming", output: "", events: [], startedAt };
  onState(initialState);
  let nextState: StreamState = initialState;
  // 4. agentEvents 与 stream 同步累积：供 message trace / 证据回放使用
  const agentEvents: AgentEvent[] = [];

  try {
    // 5. 调 SSE hook；每条事件 → 累积 state + 推消息进度
    await readRetrievalStream(
      {
        input: question,
        knowledge_base_ids: knowledgeBaseIds,
        top_k: topK,
        temperature,
        use_context: useContext,
        deep_search_enabled: deepSearchEnabled,
        // 仅在 useContext 为 true 时才传历史问题（避免无谓的请求体膨胀）
        history_questions: useContext ? historyQuestions : undefined,
        user_id: userId,
        session_id: sessionId,
      },
      (event) => {
        // 累积 stream state
        nextState = appendStreamEvent(nextState, event);
        // 把 stream 事件转成 AgentEvent 视图（event_id 序号化便于 key）
        agentEvents.push(toAgentEvent(event, agentEvents.length));
        // 通知外层
        onState(nextState);
        onProgress({ nextState, nextAgentEvents: agentEvents, rawEvent: event });
      },
    );
    // 6. 流结束：计算耗时 + 找 request_id
    const finishedAt = Date.now();
    const durationMs = finishedAt - startedAt;
    const completedRequestId =
      // 倒序找最后一条带 request_id 的事件（通常就是 answer.completed）
      [...nextState.events].reverse().find((event) => event.request_id)?.request_id ?? null;
    onComplete({ finalState: nextState, completedRequestId, durationMs });
  } catch (error) {
    // 7. 异常分支：构造 errorState + 把 error message 暴露给 UI
    const message = error instanceof Error ? error.message : "生成失败，请重试。";
    const durationMs = Date.now() - startedAt;
    const errorState: StreamState = {
      status: "error",
      output: "",
      events: [],
      error: message,
      startedAt,
      durationMs,
    };
    onState(errorState);
    onComplete({
      finalState: errorState,
      completedRequestId: null,
      durationMs,
      errorMessage: message,
    });
  }
}
