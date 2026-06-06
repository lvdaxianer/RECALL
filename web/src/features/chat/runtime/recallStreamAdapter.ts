/**
 * Recall · 流式事件 → 累积状态的纯函数适配器
 *
 * 与 useRetrievalStream 中的 `appendStreamEvent` 类似，但独立维护一个"业务态"
 * 状态机（content / status / trace / citations），方便上游纯函数化测试。
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
  question: string;
  requestId: string | null;
  content: string;
  status: RecallRunStatus;
  trace: StreamEvent[];
  citations: RecallCitation[];
  error?: string;
};

/**
 * 构造初始 run 状态。
 *
 * @param question 用户问题
 * @returns 初始 run 状态
 * @author lvdaxianerplus
 */
export function createRecallRunState(question: string): RecallRunState {
  return {
    question,
    requestId: null,
    content: "",
    status: "idle",
    trace: [],
    citations: [],
  };
}

/**
 * 把单条 stream 事件累积到现有 run 状态（不可变更新）。
 *
 * @param state 当前状态
 * @param event 新事件
 * @returns 累积后的新状态
 * @author lvdaxianerplus
 */
export function applyRecallStreamEvent(state: RecallRunState, event: StreamEvent): RecallRunState {
  // 1. 累积事件 + 提取 request_id
  const trace = [...state.trace, event];
  const requestId = event.request_id ?? state.requestId;

  // 2. answer.delta：追加到 content
  if (event.event === "answer.delta") {
    return {
      ...state,
      requestId,
      trace,
      status: "streaming",
      content: `${state.content}${String(event.payload.text ?? "")}`,
    };
  }

  // 3. answer.completed：写入 citations 并切到 success
  if (event.event === "answer.completed") {
    return {
      ...state,
      requestId,
      trace,
      status: "success",
      citations: getCitations(event.payload.results),
    };
  }

  // 4. error / request.failed：写入 error 并切到 error
  if (event.event === "error" || event.event === "request.failed") {
    return {
      ...state,
      requestId,
      trace,
      status: "error",
      error: String(event.payload.message ?? "生成失败"),
    };
  }

  // 5. 其它事件（retrieval.progress / retrieval.trace 等）：保持 streaming / idle
  return {
    ...state,
    requestId,
    trace,
    status: state.status === "idle" ? "streaming" : state.status,
  };
}

/**
 * 把 `payload.results` 归一化为 `RecallCitation[]`。
 *
 * @param results 原始 results 字段
 * @returns citations 数组
 * @author lvdaxianerplus
 */
function getCitations(results: unknown): RecallCitation[] {
  return Array.isArray(results) ? results.map((item) => item as RecallCitation) : [];
}
