/**
 * Recall · 聊天主线程
 *
 * 消息列表：用户消息右对齐、助手走 elevated card。
 * 空态展示示例 prompt 按钮，引导用户开始第一轮对话。
 *
 * 设计要点：
 * 1. ThreadPrimitive.Root 提供 Assistant UI 的滚动 + 列表渲染能力
 * 2. 容器限宽 max-w-3xl 让长消息居中可读
 * 3. aria-live="polite" 让屏幕阅读器在消息变化时播报
 * 4. 空态示例 prompt 写入草稿框，不直接发送
 * 5. 有消息时按 id 顺序渲染；key 用 message.id
 *
 * @author lvdaxianerplus
 */
import { ThreadPrimitive } from "@assistant-ui/react";

import type { AgentEvent } from "../../../api/sessions";
import { ChatMessage, type ChatMessageViewModel } from "./ChatMessage";

/**
 * 聊天主线程 props 集合。
 *
 * @author lvdaxianerplus
 */
export interface ChatThreadProps {
  /** 当前会话消息列表 */
  messages: ChatMessageViewModel[];
  /** 已发布 KB 数量（用于空态文案） */
  publishedKbCount: number;
  /** 点击示例 prompt 时的回调 */
  onPrompt: (prompt: string) => void;
  /** 取消息进度文本的回调（流式中展示用） */
  getProgressText?: (message: ChatMessageViewModel) => string;
  /** 点赞 / 点踩回调 */
  onFeedback: (messageId: string, requestId: string | null | undefined, vote: "like" | "dislike") => void;
  /** 查看证据与 Trace 回调 */
  onOpenEvidence: (events: AgentEvent[]) => void;
}

/**
 * 聊天主线程组件。
 *
 * @param props.messages 消息列表
 * @param props.publishedKbCount 已发布 KB 数
 * @param props.onPrompt 示例 prompt 回调
 * @param props.getProgressText 取进度文本
 * @param props.onFeedback 反馈回调
 * @param props.onOpenEvidence 查看证据回调
 * @author lvdaxianerplus
 */
export function ChatThread({
  messages,
  publishedKbCount,
  onPrompt,
  getProgressText,
  onFeedback,
  onOpenEvidence,
}: ChatThreadProps) {
  return (
    // ThreadPrimitive 提供 Assistant UI 的滚动 + 列表渲染能力
    <ThreadPrimitive.Root
      aria-live="polite"
      className="h-full overflow-auto bg-slate-50 px-6 py-5"
      data-assistant-ui-thread="true"
    >
      <div className="mx-auto flex max-w-3xl flex-col gap-5">
        {messages.length === 0 ? (
          // 空态：示例 prompt 引导用户开始
          <div className="grid gap-3 rounded-xl border border-dashed border-slate-200 bg-white p-6 text-sm text-slate-500">
            <strong className="text-base text-slate-900">
              {publishedKbCount > 0 ? "选择知识库后开始提问" : "暂无可检索的已发布知识库"}
            </strong>
            <div className="grid gap-2">
              {/* 每个 prompt 按钮点击后写入草稿框 */}
              <button
                className="h-10 rounded-md border border-slate-200 bg-white px-3 text-left text-sm text-slate-900 transition-all hover:-translate-y-0.5 hover:border-slate-300 hover:shadow-sm"
                type="button"
                onClick={() => onPrompt("这个知识库主要包含什么？")}
              >
                这个知识库主要包含什么？
              </button>
              <button
                className="h-10 rounded-md border border-slate-200 bg-white px-3 text-left text-sm text-slate-900 transition-all hover:-translate-y-0.5 hover:border-slate-300 hover:shadow-sm"
                type="button"
                onClick={() => onPrompt("帮我查找 ES 过滤字段怎么配置")}
              >
                帮我查找 ES 过滤字段怎么配置
              </button>
            </div>
          </div>
        ) : (
          // 有消息：按顺序渲染
          messages.map((message) => (
            <ChatMessage
              key={message.id}
              message={message}
              progressText={getProgressText?.(message)}
              onFeedback={onFeedback}
              onOpenEvidence={onOpenEvidence}
            />
          ))
        )}
      </div>
    </ThreadPrimitive.Root>
  );
}
