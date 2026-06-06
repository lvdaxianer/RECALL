/**
 * Recall · 流式检索 hook
 *
 * 封装 SSE 流式检索：发起 fetch + 解析 SSE 块 + 累积事件列表。
 * 业务层只需要订阅 `onEvent` 回调即可拿到每个 stream 事件。
 *
 * @author lvdaxianerplus
 */
import {
  applyRecallStreamEvent,
  createRecallRunState,
} from "../features/chat/runtime/recallStreamAdapter";

/**
 * 单条流式事件（来自后端 SSE）。
 *
 * @author lvdaxianerplus
 */
export interface StreamEvent {
  /** 事件名（request.created / retrieval.progress / answer.delta / answer.completed 等） */
  event: string;
  /** 请求 id（同一次 run 内所有事件共享） */
  request_id?: string | null;
  /** 事件 payload（结构因 event 而异） */
  payload: Record<string, unknown>;
}

/**
 * 累积的流式状态机。
 *
 * @author lvdaxianerplus
 */
export interface StreamState {
  /** 当前状态 */
  status: "idle" | "streaming" | "success" | "error";
  /** 累积的输出文本 */
  output: string;
  /** 累积的事件列表（调试 / 回放用） */
  events: StreamEvent[];
  /** 错误消息（status === 'error' 时） */
  error?: string;
  /** 开始时间戳 */
  startedAt?: number;
  /** 结束时间戳 */
  finishedAt?: number;
  /** 总耗时（毫秒） */
  durationMs?: number;
}

/**
 * 流式检索请求体。
 *
 * @author lvdaxianerplus
 */
export interface RetrievalStreamRequest {
  /** 用户输入 */
  input: string;
  /** 检索目标 KB id 列表 */
  knowledge_base_ids: string[];
  /** 会话 id（可选） */
  session_id?: string;
  /** topK */
  top_k?: number;
  /** 是否关联上下文 */
  use_context?: boolean;
  /** 是否启用 DeepSearch 深度检索 */
  deep_search_enabled?: boolean;
  /** 关联上下文的历史问题 */
  history_questions?: string[];
  /** 生成温度 */
  temperature?: number;
  /** 用户 id */
  user_id?: string;
}

/**
 * 初始流式状态。
 *
 * @author lvdaxianerplus
 */
const INITIAL_STREAM_STATE: StreamState = {
  status: "idle",
  output: "",
  events: [],
};

/**
 * 追加一条流式事件到累积状态。
 *
 * @param state 当前状态
 * @param event 新事件
 * @returns 累积后的新状态
 * @author lvdaxianerplus
 */
export function appendStreamEvent(state: StreamState | undefined, event: StreamEvent): StreamState {
  // 1. 兜底：未传 state 时使用初始值
  const current = state ?? INITIAL_STREAM_STATE;
  // 2. 兜底 startedAt：保证 durationMs 计算正确
  const startedAt = current.startedAt ?? Date.now();
  // 3. 委托给 recall stream adapter 做"业务侧"累积
  const nextRun = applyRecallStreamEvent(
    {
      ...createRecallRunState(""),
      content: current.output,
      status: current.status,
      trace: current.events,
    },
    event,
  );
  // 4. 终态事件单独写 finishedAt / durationMs
  if (event.event === "answer.completed") {
    const finishedAt = Date.now();
    return {
      ...current,
      status: "success",
      output: nextRun.content,
      events: nextRun.trace,
      startedAt,
      finishedAt,
      durationMs: finishedAt - startedAt,
    };
  }
  if (event.event === "request.failed" || event.event === "error") {
    const finishedAt = Date.now();
    return {
      ...current,
      status: "error",
      output: nextRun.content,
      error: nextRun.error ?? "请求失败",
      events: nextRun.trace,
      startedAt,
      finishedAt,
      durationMs: finishedAt - startedAt,
    };
  }
  // 5. 其它事件：把 status 透传（"success" 在中间状态下不应是 success，应为 streaming）
  return {
    ...current,
    status: nextRun.status === "success" ? "streaming" : nextRun.status,
    output: nextRun.content,
    events: nextRun.trace,
    startedAt,
  };
}

/**
 * 发起一次流式检索：解析 SSE 块并回调每条事件。
 *
 * @param payload 请求体
 * @param onEvent 每收到一条事件时回调（可选）
 * @returns 全部事件数组
 * @author lvdaxianerplus
 */
export async function readRetrievalStream(
  payload: RetrievalStreamRequest,
  onEvent?: (event: StreamEvent) => void,
): Promise<StreamEvent[]> {
  // 1. 发起 POST 请求
  const response = await fetch("/api/v1/retrieval/search/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  // 2. 非 2xx 抛错（错误信息优先读后端 detail）
  if (!response.ok) {
    throw new Error(await readErrorMessage(response));
  }
  // 3. 兼容无 body 的情况：把整段响应体作为 SSE 文本解析
  if (!response.body) {
    return emitEvents(parseSseBlocks(await response.text()), onEvent);
  }
  // 4. 走 ReadableStream 增量解析
  return readStreamEvents(response.body, onEvent);
}

/**
 * 从 error response 抽取错误消息。
 *
 * @param response fetch 响应
 * @returns 错误消息字符串
 * @author lvdaxianerplus
 */
async function readErrorMessage(response: Response): Promise<string> {
  try {
    // 优先从后端 ApiResponse.data.detail.message 抽取
    const payload = await response.json();
    return String(payload?.detail?.message ?? payload?.message ?? "请求失败");
  } catch {
    // 解析失败时回退到通用文案
    return "请求失败";
  }
}

/**
 * 把整段 SSE 文本按 `\\n\\n` 切块并解析。
 *
 * @param text 完整 SSE 文本
 * @returns 事件数组
 * @author lvdaxianerplus
 */
export function parseSseBlocks(text: string): StreamEvent[] {
  return text
    .split("\n\n")
    .map((block) => block.trim())
    .filter(Boolean)
    .map(parseSseBlock);
}

/**
 * 解析单个 SSE 块（`event:` + `data:` 行）。
 *
 * @param block SSE 块
 * @returns 解析后的 event
 * @author lvdaxianerplus
 */
function parseSseBlock(block: string): StreamEvent {
  const lines = block.split("\n");
  // SSE 块以 `event: xxx` 开头（event 类型）
  const eventLine = lines.find((line) => line.startsWith("event: "));
  // SSE 块以 `data: {...}` 开头（JSON 数据）
  const dataLine = lines.find((line) => line.startsWith("data: "));
  // 解析 data JSON；如果 data 缺失则用空 payload
  const parsed = dataLine ? JSON.parse(dataLine.replace("data: ", "")) : { payload: {} };
  return {
    event: eventLine ? eventLine.replace("event: ", "") : String(parsed.event ?? "message"),
    request_id: parsed.request_id ?? null,
    payload: parsed.payload ?? {},
  };
}

/**
 * 增量消费 ReadableStream，解析每个完整 SSE 块。
 *
 * @param body ReadableStream
 * @param onEvent 每条事件回调
 * @returns 全部事件数组
 * @author lvdaxianerplus
 */
async function readStreamEvents(
  body: ReadableStream<Uint8Array>,
  onEvent?: (event: StreamEvent) => void,
): Promise<StreamEvent[]> {
  const reader = body.getReader();
  // TextDecoder 配合 stream: true 可在多字节字符边界正确解码
  const decoder = new TextDecoder();
  const events: StreamEvent[] = [];
  let buffer = "";
  let isDone = false;
  while (!isDone) {
    const result = await reader.read();
    isDone = result.done;
    // 流结束时解码器 flush 一次
    buffer += decoder.decode(result.value ?? new Uint8Array(), { stream: !isDone });
    // 截取出所有完整的 SSE 块，剩余的留在 buffer
    const parsed = drainCompleteBlocks(buffer);
    buffer = parsed.rest;
    events.push(...emitEvents(parsed.events, onEvent));
  }
  // 流结束后 buffer 里残留的不完整块也尝试解析
  if (buffer.trim()) {
    events.push(...emitEvents(parseSseBlocks(buffer), onEvent));
  }
  return events;
}

/**
 * 从 buffer 中切出所有完整 SSE 块。
 *
 * @param buffer 累积 buffer
 * @returns 完整事件 + 剩余 buffer
 * @author lvdaxianerplus
 */
function drainCompleteBlocks(buffer: string): { events: StreamEvent[]; rest: string } {
  const parts = buffer.split("\n\n");
  // 最后一段可能是不完整的，留作 rest
  const rest = parts.pop() ?? "";
  return {
    events: parseSseBlocks(parts.join("\n\n")),
    rest,
  };
}

/**
 * 触发 onEvent 回调并返回事件数组（链式调用友好）。
 *
 * @param events 事件数组
 * @param onEvent 回调
 * @returns 原 events
 * @author lvdaxianerplus
 */
function emitEvents(events: StreamEvent[], onEvent?: (event: StreamEvent) => void): StreamEvent[] {
  events.forEach((event) => onEvent?.(event));
  return events;
}
