import { Sparkles, ThumbsDown, ThumbsUp } from "lucide-react";

import type { AgentEvent } from "../../../api/sessions";
import { Button } from "@/components/ui/button";
import { MarkdownAnswer } from "./MarkdownAnswer";
import { RecommendationSection } from "./RecommendationSection";
import { ThinkingPanel } from "./ThinkingPanel";
import { formatDuration, getLatestAnswerTiming, TimingSummarySection } from "./TimingSummarySection";

/**
 * 单条聊天消息的视图模型。
 *
 * @author lvdaxianerplus
 * @date 2026-06-06
 */
export interface ChatMessageViewModel {
  id: string;
  role: "user" | "assistant";
  content: string;
  status?: "streaming" | "success" | "error";
  trace?: AgentEvent[];
  durationMs?: number;
  requestId?: string | null;
  feedbackStatus?: "liked" | "disliked" | "queued" | "error";
  showThinking?: boolean;
}

/**
 * 反馈状态 → 用户可见的提示文案。
 * 注意：状态 enum 与文案一一对应；新增状态时务必同步更新。
 *
 * @author lvdaxianerplus
 * @date 2026-06-06
 */
const FEEDBACK_TEXT: Record<"liked" | "disliked" | "queued" | "error", string> = {
  liked: "已增加信任权重",
  disliked: "这题不算，我让它重新想一遍",
  queued: "反馈会在回答完成后提交",
  error: "反馈提交失败",
};

/**
 * 取反馈状态对应的展示文案。
 *
 * @param status - 反馈状态
 * @returns 反馈文案，状态为空时返回 undefined
 * @author lvdaxianerplus
 * @date 2026-06-06
 */
function getFeedbackText(status?: ChatMessageViewModel["feedbackStatus"]): string | undefined {
  return status ? FEEDBACK_TEXT[status] : undefined;
}

/**
 * 单条消息配置对象（用于减少 13.2 函数参数数量）。
 *
 * @author lvdaxianerplus
 * @date 2026-06-06
 */
export interface ChatMessageProps {
  message: ChatMessageViewModel;
  progressText?: string;
  onFeedback: (messageId: string, requestId: string | null | undefined, vote: "like" | "dislike") => void;
  onOpenEvidence: (events: AgentEvent[]) => void;
}

/**
 * 单条消息：用户消息右对齐、emerald 色块；
 * 助手消息走 elevated card（白底 + 轻 shadow），含思考面板 + markdown + 反馈按钮。
 *
 * @param props - 消息配置
 * @returns 单条消息 UI
 * @author lvdaxianerplus
 * @date 2026-06-06
 */
export function ChatMessage({ message, progressText, onFeedback, onOpenEvidence }: ChatMessageProps) {
  const timing = getLatestAnswerTiming(message.trace, message.durationMs);
  const feedbackText = getFeedbackText(message.feedbackStatus);

  return message.role === "user" ? (
    // 用户消息：右对齐 emerald 实心块
    (
      <article
        className="flex max-w-[88%] flex-col items-end gap-1"
        data-message-id={message.id}
        data-message-role={message.role}
      >
        <p className="whitespace-pre-wrap rounded-2xl rounded-tr-md border border-emerald-600 bg-emerald-600 px-3.5 py-2 text-sm leading-6 text-white shadow-sm">
          {message.content}
        </p>
      </article>
    )
  ) : (
    // 助手消息：白底 elevated card + 思考面板 + markdown + 反馈
    <article
      className="flex max-w-[88%] flex-col gap-2"
      data-message-id={message.id}
      data-message-role={message.role}
    >
      <header className="flex items-center gap-2 text-xs text-slate-500">
        {/* 品牌标 */}
        <span
          aria-hidden="true"
          className="grid size-5 place-items-center rounded-md bg-emerald-50 text-emerald-700"
        >
          <Sparkles className="size-3" />
        </span>
        <span className="font-medium text-slate-700">Recall</span>
        {/* 耗时（右对齐） */}
        {timing?.totalDurationMs !== undefined && timing.stages.length === 0 ? (
          <span className="ml-auto font-mono text-[11px] text-slate-400">
            总耗时 {formatDuration(timing.totalDurationMs)}
          </span>
        ) : null}
      </header>
      <TimingSummarySection timing={timing} />
      {/* 思考面板（仅当消息配置 showThinking 时渲染） */}
      {message.showThinking ? (
        <ThinkingPanel events={message.trace} isStreaming={message.status === "streaming"} />
      ) : null}
      <MarkdownAnswer
        content={message.content}
        isStreaming={message.status === "streaming"}
        progressText={progressText}
      />
      <RecommendationSection events={message.trace} />
      {/* 反馈按钮 + 查看证据 */}
      <div className="flex flex-wrap items-center gap-1.5">
        <Button
          aria-label="点赞这条回答"
          className="size-7 rounded-full border border-slate-200 bg-white text-slate-500 transition-colors hover:border-emerald-300 hover:bg-emerald-50 hover:text-emerald-700"
          size="icon-sm"
          type="button"
          variant="ghost"
          onClick={() => onFeedback(message.id, message.requestId, "like")}
        >
          <ThumbsUp aria-hidden="true" className="h-3.5 w-3.5" />
        </Button>
        <Button
          aria-label="点踩并重新检索"
          className="size-7 rounded-full border border-slate-200 bg-white text-slate-500 transition-colors hover:border-red-300 hover:bg-red-50 hover:text-red-700"
          size="icon-sm"
          type="button"
          variant="ghost"
          onClick={() => onFeedback(message.id, message.requestId, "dislike")}
        >
          <ThumbsDown aria-hidden="true" className="h-3.5 w-3.5" />
        </Button>
        {/* 反馈状态文案（仅在已反馈时展示） */}
        {feedbackText ? <span className="text-[11px] text-slate-500">{feedbackText}</span> : undefined}
        <button
          className="ml-auto inline-flex h-7 items-center gap-1.5 rounded-md border border-slate-200 bg-white px-2.5 text-[11px] font-medium text-slate-700 transition-colors hover:border-slate-300 hover:bg-slate-50"
          type="button"
          onClick={() => onOpenEvidence(message.trace ?? [])}
        >
          查看证据与 Trace
        </button>
      </div>
    </article>
  );
}
