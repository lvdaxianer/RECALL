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
 * 单条消息。
 *
 * @param props - 消息配置
 * @returns 单条消息 UI
 * @author lvdaxianerplus
 * @date 2026-06-06
 */
export function ChatMessage({ message, progressText, onFeedback, onOpenEvidence }: ChatMessageProps) {
  const timing = getLatestAnswerTiming(message.trace, message.durationMs);
  const feedbackText = getFeedbackText(message.feedbackStatus);

  return message.role === "user"
    ? <UserMessage message={message} />
    : (
      <AssistantMessage
        feedbackText={feedbackText}
        message={message}
        progressText={progressText}
        timing={timing}
        onFeedback={onFeedback}
        onOpenEvidence={onOpenEvidence}
      />
    );
}

/**
 * 用户消息气泡。
 *
 * @param props - message 为用户消息视图模型
 * @returns 用户消息 UI
 * @author lvdaxianerplus
 * @date 2026-06-06
 */
function UserMessage({ message }: { message: ChatMessageViewModel }) {
  return (
    <article
      className="flex max-w-[88%] flex-col items-end gap-1"
      data-message-id={message.id}
      data-message-role={message.role}
    >
      <p className="whitespace-pre-wrap rounded-2xl rounded-tr-md border border-emerald-600 bg-emerald-600 px-3.5 py-2 text-sm leading-6 text-white shadow-sm">
        {message.content}
      </p>
    </article>
  );
}

/**
 * 助手消息配置对象。
 *
 * @author lvdaxianerplus
 * @date 2026-06-06
 */
interface AssistantMessageProps extends ChatMessageProps {
  feedbackText?: string;
  timing: ReturnType<typeof getLatestAnswerTiming>;
}

/**
 * 助手消息主体。
 *
 * @param props - 助手消息渲染配置
 * @returns 助手消息 UI
 * @author lvdaxianerplus
 * @date 2026-06-06
 */
function AssistantMessage(props: AssistantMessageProps) {
  const { feedbackText, message, progressText, timing, onFeedback, onOpenEvidence } = props;
  return (
    <article
      className="flex max-w-[88%] flex-col gap-2"
      data-message-id={message.id}
      data-message-role={message.role}
    >
      <AssistantHeader timing={timing} />
      <TimingSummarySection timing={timing} />
      <ThinkingArea message={message} />
      <MarkdownAnswer
        content={message.content}
        isStreaming={message.status === "streaming"}
        progressText={progressText}
      />
      <RecommendationSection events={message.trace} />
      <FeedbackActions
        feedbackText={feedbackText}
        message={message}
        onFeedback={onFeedback}
        onOpenEvidence={onOpenEvidence}
      />
    </article>
  );
}

/**
 * 助手消息头部。
 *
 * @param props - timing 为耗时信息
 * @returns 助手消息头部 UI
 * @author lvdaxianerplus
 * @date 2026-06-06
 */
function AssistantHeader({ timing }: { timing: ReturnType<typeof getLatestAnswerTiming> }) {
  return (
    <header className="flex items-center gap-2 text-xs text-slate-500">
      <AssistantBrand />
      {timing?.totalDurationMs !== undefined && timing.stages.length === 0 ? (
        <HeaderDuration durationMs={timing.totalDurationMs} />
      ) : undefined}
    </header>
  );
}

/**
 * 助手品牌标识。
 *
 * @returns 品牌标识 UI
 * @author lvdaxianerplus
 * @date 2026-06-06
 */
function AssistantBrand() {
  return (
    <>
      <span aria-hidden="true" className="grid size-5 place-items-center rounded-md bg-emerald-50 text-emerald-700">
        <Sparkles className="size-3" />
      </span>
      <span className="font-medium text-slate-700">Recall</span>
    </>
  );
}

/**
 * 头部总耗时标签。
 *
 * @param props - durationMs 为总耗时毫秒数
 * @returns 总耗时 UI
 * @author lvdaxianerplus
 * @date 2026-06-06
 */
function HeaderDuration({ durationMs }: { durationMs: number }) {
  return (
    <span className="ml-auto font-mono text-[11px] text-slate-400">
      总耗时 {formatDuration(durationMs)}
    </span>
  );
}

/**
 * 思考面板区域。
 *
 * @param props - message 为助手消息
 * @returns 思考面板 UI；未开启时不渲染
 * @author lvdaxianerplus
 * @date 2026-06-06
 */
function ThinkingArea({ message }: { message: ChatMessageViewModel }) {
  return message.showThinking ? (
    <ThinkingPanel events={message.trace} isStreaming={message.status === "streaming"} />
  ) : undefined;
}

/**
 * 反馈区配置对象。
 *
 * @author lvdaxianerplus
 * @date 2026-06-06
 */
interface FeedbackActionsProps {
  feedbackText?: string;
  message: ChatMessageViewModel;
  onFeedback: ChatMessageProps["onFeedback"];
  onOpenEvidence: ChatMessageProps["onOpenEvidence"];
}

/**
 * 反馈按钮区。
 *
 * @param props - 反馈按钮区配置
 * @returns 反馈按钮 UI
 * @author lvdaxianerplus
 * @date 2026-06-06
 */
function FeedbackActions({ feedbackText, message, onFeedback, onOpenEvidence }: FeedbackActionsProps) {
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <FeedbackButton label="点赞这条回答" vote="like" message={message} onFeedback={onFeedback} />
      <FeedbackButton label="点踩并重新检索" vote="dislike" message={message} onFeedback={onFeedback} />
      {feedbackText ? <span className="text-[11px] text-slate-500">{feedbackText}</span> : undefined}
      <EvidenceButton events={message.trace ?? []} onOpenEvidence={onOpenEvidence} />
    </div>
  );
}

/**
 * 单个反馈按钮配置对象。
 *
 * @author lvdaxianerplus
 * @date 2026-06-06
 */
interface FeedbackButtonProps {
  label: string;
  vote: "like" | "dislike";
  message: ChatMessageViewModel;
  onFeedback: ChatMessageProps["onFeedback"];
}

/**
 * 单个反馈按钮。
 *
 * @param props - 反馈按钮配置
 * @returns 反馈按钮 UI
 * @author lvdaxianerplus
 * @date 2026-06-06
 */
function FeedbackButton({ label, vote, message, onFeedback }: FeedbackButtonProps) {
  const Icon = vote === "like" ? ThumbsUp : ThumbsDown;
  const hoverClass = vote === "like" ? "hover:border-emerald-300 hover:bg-emerald-50 hover:text-emerald-700" : "hover:border-red-300 hover:bg-red-50 hover:text-red-700";
  return (
    <Button
      aria-label={label}
      className={`size-7 rounded-full border border-slate-200 bg-white text-slate-500 transition-colors ${hoverClass}`}
      size="icon-sm"
      type="button"
      variant="ghost"
      onClick={() => onFeedback(message.id, message.requestId, vote)}
    >
      <Icon aria-hidden="true" className="h-3.5 w-3.5" />
    </Button>
  );
}

/**
 * 查看证据按钮。
 *
 * @param props - events 为证据事件流
 * @returns 证据按钮 UI
 * @author lvdaxianerplus
 * @date 2026-06-06
 */
function EvidenceButton({ events, onOpenEvidence }: { events: AgentEvent[]; onOpenEvidence: ChatMessageProps["onOpenEvidence"] }) {
  return (
    <button
      className="ml-auto inline-flex h-7 items-center gap-1.5 rounded-md border border-slate-200 bg-white px-2.5 text-[11px] font-medium text-slate-700 transition-colors hover:border-slate-300 hover:bg-slate-50"
      type="button"
      onClick={() => onOpenEvidence(events)}
    >
      查看证据与 Trace
    </button>
  );
}
