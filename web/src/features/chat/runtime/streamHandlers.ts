/**
 * Recall · 流式回调工厂
 *
 * 为 `streamAssistantAnswer` 构造 onProgress / onComplete 回调：
 * - 进度回调：把累积 state 写到指定消息（content / status / requestId / trace）
 * - 完成回调：写入最终态（成功 / 错误）+ 触发 `onSettled` 副作用（用于消费等待中的反馈）
 *
 * @author lvdaxianerplus
 */
import type { AgentEvent } from "../../../api/sessions";
import type { StreamState } from "../../../hooks/useRetrievalStream";

/**
 * 进度回调写入消息的 patch 形状。
 *
 * @author lvdaxianerplus
 */
export interface MessageProgressPatch {
  /** 累积输出文本 */
  content: string;
  /** 中间状态（error 表示当前 stream 出错但尚未结束） */
  status: "streaming" | "error";
  /** 已知的 request_id（从流事件中提取） */
  requestId: string | null;
  /** 累积的 AgentEvent 列表 */
  trace: AgentEvent[];
}

/**
 * 完成回调写入消息的 patch 形状。
 *
 * @author lvdaxianerplus
 */
export interface MessageCompletePatch {
  /** 最终输出文本 */
  content: string;
  /** 终态（成功 / 错误） */
  status: "success" | "error";
  /** 耗时（毫秒） */
  durationMs: number;
  /** request_id（成功时才有） */
  requestId?: string | null;
}

/**
 * 构造 streamAssistantAnswer.onProgress 回调：把进度写到指定消息。
 *
 * @param assistantMessageId 要更新的消息 id
 * @param updateMessage 父组件提供的更新函数
 * @returns 适配 onProgress 签名的回调
 * @author lvdaxianerplus
 */
export function buildMessageProgressHandler(
  assistantMessageId: string,
  updateMessage: (messageId: string, patch: MessageProgressPatch) => void,
) {
  return (params: { nextState: StreamState; nextAgentEvents: AgentEvent[] }) => {
    // 1. 解构参数
    const { nextState, nextAgentEvents } = params;
    // 2. 从 events 中找最早的 request_id（同一 run 内共享）
    const requestId = nextState.events.find((item) => item.request_id)?.request_id ?? null;
    // 3. 写入消息：content 累积、status 跟随 stream 状态、trace 全部累积
    updateMessage(assistantMessageId, {
      content: nextState.output,
      status: nextState.status === "error" ? "error" : "streaming",
      requestId,
      trace: nextAgentEvents,
    });
  };
}

/**
 * 构造 streamAssistantAnswer.onComplete 回调：写入最终状态 + 触发等待中的反馈。
 *
 * @param assistantMessageId 要更新的消息 id
 * @param updateMessage 父组件提供的更新函数
 * @param onSettled 完成时的副作用（如提交已入队的反馈）
 * @returns 适配 onComplete 签名的回调
 * @author lvdaxianerplus
 */
export function buildMessageCompleteHandler(
  assistantMessageId: string,
  updateMessage: (messageId: string, patch: MessageCompletePatch) => void,
  onSettled?: (params: { completedRequestId: string | null }) => void,
) {
  return (params: {
    finalState: StreamState;
    completedRequestId: string | null;
    durationMs: number;
    errorMessage?: string;
  }) => {
    // 错误分支：把 errorMessage 作为内容展示，状态切到 error
    if (params.errorMessage) {
      updateMessage(assistantMessageId, {
        content: params.errorMessage,
        status: "error",
        durationMs: params.durationMs,
      });
      onSettled?.({ completedRequestId: null });
      return;
    }
    // 成功分支：写最终内容 / 耗时 / request_id
    updateMessage(assistantMessageId, {
      content: params.finalState.output || "未检索到可用回答",
      status: "success",
      durationMs: params.durationMs,
      requestId: params.completedRequestId,
    });
    // 触发副作用（业务态：消费 pending feedback 等）
    onSettled?.({ completedRequestId: params.completedRequestId });
  };
}
