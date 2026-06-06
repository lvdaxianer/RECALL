import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Sparkles, ThumbsDown, ThumbsUp } from "lucide-react";

import type { AgentEvent } from "../../../api/sessions";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/**
 * 单条聊天消息的视图模型。
 *
 * @author lvdaxianerplus
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
 */
const FEEDBACK_TEXT: Record<"liked" | "disliked" | "queued" | "error", string> = {
  liked: "已增加信任权重",
  disliked: "这题不算，我让它重新想一遍",
  queued: "反馈会在回答完成后提交",
  error: "反馈提交失败",
};

/**
 * 格式化耗时（毫秒 → ms / s）。
 *
 * @param durationMs 毫秒数
 * @returns 形如 `1.23s` 或 `120ms`
 * @author lvdaxianerplus
 */
function formatDuration(durationMs: number): string {
  if (durationMs >= 1000) {
    return `${(durationMs / 1000).toFixed(2)}s`;
  }
  return `${Math.max(0, Math.round(durationMs))}ms`;
}

/**
 * 取反馈状态对应的展示文案。
 *
 * @param status 反馈状态
 * @returns 反馈文案，状态为空时返回 null
 * @author lvdaxianerplus
 */
function getFeedbackText(status?: ChatMessageViewModel["feedbackStatus"]): string | null {
  if (!status) {
    return null;
  }
  return FEEDBACK_TEXT[status] ?? null;
}

/**
 * 把 (stage, summary) 转成用户友好的进度文案。
 *
 * @param summary 原始 summary 字段
 * @param stage 原始 stage 字段
 * @returns 用户友好文案
 * @author lvdaxianerplus
 */
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

/**
 * 把 trace 步骤翻译成"思考中"面板展示的友好文案。
 *
 * @param trace 单条 trace 步骤
 * @returns 友好文案
 * @author lvdaxianerplus
 */
function getTraceStepText(trace: { stage?: string; summary?: string; metrics?: Record<string, unknown> }): string {
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

/**
 * 从事件流里抽取"思考中"步骤的展示文案列表。
 *
 * @param events 事件流
 * @returns 步骤文案数组
 * @author lvdaxianerplus
 */
function getThinkingSteps(events: AgentEvent[] | undefined): Array<{ summary: string; meta?: string }> {
  const steps: Array<{ summary: string; meta?: string }> = [];
  let hasAnswerDelta = false;
  for (const event of events ?? []) {
    if (event.event === "request.created") {
      const input = typeof event.payload.input === "string" ? event.payload.input : "";
      steps.push({ summary: input ? `收到问题：「${input}」` : "收到问题，准备进入检索链路" });
      continue;
    }
    if (event.event === "retrieval.progress") {
      steps.push({ summary: getProgressSummary(event.payload.summary, event.payload.stage) });
      continue;
    }
    if (event.event === "retrieval.trace" && Array.isArray(event.payload.trace)) {
      for (const item of event.payload.trace) {
        const trace = item as { stage?: string; summary?: string; metrics?: Record<string, unknown> };
        steps.push({ summary: getTraceStepText(trace) });
      }
      continue;
    }
    if (event.event === "answer.delta" && !hasAnswerDelta) {
      hasAnswerDelta = true;
      steps.push({ summary: "开始根据证据流式组织回答" });
      continue;
    }
    if (event.event === "answer.completed") {
      steps.push({ summary: "回答完成，已整理引用来源" });
    }
  }
  return steps.length > 0 ? steps : [{ summary: "正在准备检索链路" }];
}

/**
 * 取最近一条 `retrieval.progress` 的 summary。
 *
 * 业务上游 `ChatAssistant` 也会调同名函数（`runtime/chatHelpers`），
 * 这里的版本作为组件内 fallback，优先级低于外部 prop。
 *
 * @param events 事件流
 * @returns summary 文案，缺省返回 `"正在检索证据"`
 * @author lvdaxianerplus
 */
function getLatestProgressSummary(events: AgentEvent[] | undefined): string {
  // 倒序查找最近一条 retrieval.progress 事件，提取其 summary
  const progress = [...(events ?? [])]
    .reverse()
    .find((event) => event.event === "retrieval.progress" && typeof event.payload.summary === "string");
  return typeof progress?.payload.summary === "string" ? progress.payload.summary : "正在检索证据";
}

/**
 * 思考中面板：折叠态只露"思考中 / 已完成思考" + 流式 dot；
 * 展开态显示 step-by-step 检索阶段。
 *
 * @author lvdaxianerplus
 */
interface ThinkingPanelProps {
  events: AgentEvent[] | undefined;
  isStreaming: boolean;
}
function ThinkingPanel({ events, isStreaming }: ThinkingPanelProps) {
  // 1. 把事件流翻译成步骤文案列表
  const steps = getThinkingSteps(events);
  return (
    // 流式中默认展开，完成后折叠；用户可手动 toggle
    <details
      className="group rounded-lg border border-slate-200 bg-white p-3 shadow-xs transition-shadow hover:shadow-sm open:bg-slate-50/40"
      open={isStreaming}
    >
      <summary className="inline-flex cursor-pointer list-none items-center gap-2 text-slate-500 select-none [&::-webkit-details-marker]:hidden">
        {/* 状态点：流式中是 emerald + animate-pulse，完成后是 slate */}
        <span
          aria-hidden="true"
          className={cn(
            "size-2 rounded-full",
            isStreaming
              ? "animate-pulse bg-emerald-500 shadow-[0_0_0_4px_rgba(5,150,105,0.15)]"
              : "bg-slate-300",
          )}
        />
        <strong className="text-xs font-medium text-slate-900">
          {isStreaming ? "思考中" : "已完成思考"}
        </strong>
        {/* 折叠箭头：open 时旋转 180° */}
        <span aria-hidden="true" className="ml-auto text-xs text-slate-400 transition-transform group-open:rotate-180">▾</span>
      </summary>
      <ol className="mt-2 grid list-decimal gap-1.5 pl-5 text-xs leading-6 text-slate-600">
        {steps.map((step, index) => (
          <li key={`${step.summary}-${index}`}>
            {step.summary}
            {step.meta ? <small className="mt-0.5 block break-words text-[11px] text-slate-400">{step.meta}</small> : null}
          </li>
        ))}
      </ol>
    </details>
  );
}

/**
 * Markdown 回答区：助手回答包在 elevated card 里；流式时顶部有"打字中"指示。
 *
 * @author lvdaxianerplus
 */
interface MarkdownAnswerProps {
  content: string;
  isStreaming: boolean;
  progressText?: string;
}
function MarkdownAnswer({ content, isStreaming, progressText }: MarkdownAnswerProps) {
  // 流式中若完全空内容，不渲染整张卡片（避免空白抖动）
  if (!content.trim() && isStreaming) {
    return null;
  }
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-xs transition-shadow hover:shadow-sm">
      {/* 顶部打字中提示：仅在流式时出现 */}
      {isStreaming ? (
        <div className="mb-2 inline-flex items-center gap-1.5 text-xs text-slate-500">
          <span aria-hidden="true" className="size-1.5 animate-pulse rounded-full bg-emerald-500" />
          {progressText ?? "正在检索证据"}
        </div>
      ) : null}
      {content.trim() ? (
        // prose 样式：标题/段落/列表/代码/引用/图片/表格 全部以"原子"覆盖类对齐
        <div className="chat-answer text-sm leading-7 text-slate-800 [&_h1]:text-base [&_h1]:font-semibold [&_h2]:text-base [&_h2]:font-semibold [&_h3]:text-sm [&_h3]:font-semibold [&_h4]:text-sm [&_h4]:font-medium [&_p]:m-0 [&_ul]:m-0 [&_ol]:m-0 [&_ul]:grid [&_ul]:gap-1 [&_ol]:grid [&_ol]:gap-1 [&_ul]:pl-5 [&_ol]:pl-5 [&_blockquote]:rounded-md [&_blockquote]:border-l-2 [&_blockquote]:border-emerald-500 [&_blockquote]:bg-slate-50 [&_blockquote]:px-3 [&_blockquote]:py-2 [&_blockquote]:text-slate-500 [&_code]:rounded [&_code]:bg-slate-100 [&_code]:px-1 [&_code]:py-px [&_code]:font-mono [&_code]:text-[0.9em] [&_pre]:max-h-44 [&_pre]:overflow-auto [&_pre]:rounded-md [&_pre]:border [&_pre]:border-slate-200 [&_pre]:bg-slate-50 [&_pre]:p-2.5 [&_a]:font-medium [&_a]:text-emerald-700 [&_a]:no-underline hover:[&_a]:underline [&_img]:max-h-64 [&_img]:rounded-md [&_img]:border [&_img]:border-slate-200 [&_img]:bg-slate-50 [&_img]:object-contain [&_table]:block [&_table]:max-w-full [&_table]:overflow-x-auto [&_table]:rounded-md [&_table]:border [&_table]:border-slate-200 [&_table]:text-sm [&_th]:border-b [&_th]:border-slate-200 [&_th]:bg-slate-50 [&_th]:px-2.5 [&_th]:py-2 [&_th]:text-left [&_th]:font-semibold [&_td]:border-b [&_td]:border-slate-200 [&_td]:px-2.5 [&_td]:py-2 [&_td]:text-left [&_td]:align-top">
          <ReactMarkdown
            components={{
              // 外部链接强制 noopener + noreferrer + target=_blank
              a: ({ children, href }) => (
                <a href={href} rel="noreferrer" target="_blank">{children}</a>
              ),
              // 图片懒加载
              img: ({ alt, src }) => <img alt={alt ?? ""} loading="lazy" src={src ?? ""} />,
            }}
            remarkPlugins={[remarkGfm]}
          >
            {content}
          </ReactMarkdown>
        </div>
      ) : null}
    </div>
  );
}

/**
 * 单条消息配置对象（用于减少 13.2 函数参数数量）。
 *
 * @author lvdaxianerplus
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
 * @param props 消息配置
 * @author lvdaxianerplus
 */
export function ChatMessage({ message, progressText, onFeedback, onOpenEvidence }: ChatMessageProps) {
  // 用户消息：右对齐 emerald 实心块
  if (message.role === "user") {
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

  // 助手消息：白底 elevated card + 思考面板 + markdown + 反馈
  return (
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
        {message.durationMs !== undefined ? (
          <span className="ml-auto font-mono text-[11px] text-slate-400">
            耗时 {formatDuration(message.durationMs)}
          </span>
        ) : null}
      </header>
      {/* 思考面板（仅当消息配置 showThinking 时渲染） */}
      {message.showThinking ? (
        <ThinkingPanel events={message.trace} isStreaming={message.status === "streaming"} />
      ) : null}
      <MarkdownAnswer
        content={message.content}
        isStreaming={message.status === "streaming"}
        progressText={progressText}
      />
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
        {getFeedbackText(message.feedbackStatus) ? (
          <span className="text-[11px] text-slate-500">{getFeedbackText(message.feedbackStatus)}</span>
        ) : null}
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
