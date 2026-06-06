/**
 * Recall · @assistant-ui/react 本地 runtime hook
 *
 * 适配 Recall 检索流到 Assistant UI 的 ChatModelAdapter：
 * - 接收 `messages`（已渲染历史）+ `request`（检索参数）
 * - 当 Assistant UI 调用 `run` 时，触发 readRetrievalStream 并把每条事件转换为 content
 * - 把 citations / trace 放到 metadata.custom 方便面板读取
 *
 * @author lvdaxianerplus
 */
import { useMemo } from "react";
import {
  useLocalRuntime,
  type ChatModelAdapter,
  type ChatModelRunOptions,
  type ChatModelRunResult,
  type ThreadMessage,
  type ThreadMessageLike,
} from "@assistant-ui/react";

import { readRetrievalStream, type RetrievalStreamRequest } from "../../../hooks/useRetrievalStream";
import type { RecallRunState } from "./recallChatTypes";
import { applyRecallStreamEvent, createRecallRunState } from "./recallStreamAdapter";

/**
 * useRecallAssistantRuntime 入参。
 *
 * @author lvdaxianerplus
 */
interface RecallAssistantRuntimeOptions {
  /** 已渲染的 Assistant UI 消息列表 */
  messages: ThreadMessageLike[];
  /** 检索参数（不含 input） */
  request: Omit<RetrievalStreamRequest, "input">;
  /** run 状态更新回调（可选） */
  onRunUpdate?: (state: RecallRunState) => void;
}

/**
 * 把 Assistant UI 消息列表的最后一条 user 消息提取为 query。
 *
 * @param messages Assistant UI 消息列表
 * @returns 最新 user 消息内容（已 trim）
 * @author lvdaxianerplus
 */
function getLatestUserMessage(messages: readonly ThreadMessage[]): string {
  // 1. 倒序查找，避免全量遍历
  const latest = [...messages].reverse().find((message) => message.role === "user");
  if (!latest) {
    return "";
  }
  // 2. 把多模态 content 拼接成纯文本
  return latest.content
    .map((part) => (part.type === "text" ? part.text : ""))
    .join("")
    .trim();
}

/**
 * @assistant-ui/react 本地 runtime hook：把 Recall 检索流适配到 Assistant UI。
 *
 * @param options 入参
 * @returns 本地 runtime
 * @author lvdaxianerplus
 */
export function useRecallAssistantRuntime({
  messages,
  request,
  onRunUpdate,
}: RecallAssistantRuntimeOptions) {
  // 把 stream 适配成 ChatModelAdapter；request / onRunUpdate 变化时重建
  const adapter = useMemo<ChatModelAdapter>(() => ({
    async run(options: ChatModelRunOptions): Promise<ChatModelRunResult> {
      return runRecallChatModel(options, request, onRunUpdate);
    },
  }), [request, onRunUpdate]);

  return useLocalRuntime(adapter, { initialMessages: messages });
}

/**
 * 跑一次 Assistant UI run：把用户输入 + 历史问题流式产出 assistant text。
 *
 * @param options Assistant UI run 选项
 * @param request 检索参数
 * @param onRunUpdate run 状态回调
 * @returns ChatModelRunResult
 * @author lvdaxianerplus
 */
async function runRecallChatModel(
  options: ChatModelRunOptions,
  request: Omit<RetrievalStreamRequest, "input">,
  onRunUpdate?: (state: RecallRunState) => void,
): Promise<ChatModelRunResult> {
  // 1. 抽 user 问题 + 初始化 run state
  const question = getLatestUserMessage(options.messages);
  let state = createRecallRunState(question);

  // 2. 调 SSE hook；每条事件触发 stream adapter + 状态回调
  await readRetrievalStream(
    {
      ...request,
      input: question,
    },
    (event) => {
      state = applyRecallStreamEvent(state, event);
      onRunUpdate?.(state);
    },
  );

  // 3. 组装 Assistant UI 的返回结构
  return {
    content: [{ type: "text", text: state.content || state.error || "" }],
    status: state.status === "error"
      ? { type: "incomplete", reason: "error", error: state.error ?? "生成失败" }
      : { type: "complete", reason: "stop" },
    metadata: {
      custom: {
        citations: state.citations,
        requestId: state.requestId,
        trace: state.trace,
      },
    },
  };
}
