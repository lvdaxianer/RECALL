import type { AgentEvent } from "../../../api/sessions";
import { cn } from "@/lib/utils";

const FIRST_ITEM_OFFSET = 1;
const ZERO_HIT_COUNT = 0;

type ThinkingStep = { summary: string; meta?: string };
type TraceStep = { stage?: string; summary?: string; metrics?: Record<string, unknown> };
type TraceTextResolver = (trace: TraceStep) => string;

const DEFAULT_PROGRESS_SUMMARY = "正在处理检索请求";
const DEFAULT_TRACE_SUMMARY = "已完成一个检索步骤";
const DEFAULT_THINKING_STEP: ThinkingStep = { summary: "正在准备检索链路" };

const PROGRESS_STAGE_TEXT: Record<string, string> = {
  answer_generation: "已找到可用资料，正在整理回答",
  deep_search_planning: "深度检索会拆分问题并多轮检索，可能需要更久",
  query_scope: "正在判断这个问题适合怎么查",
  retrieval: "正在从选中的知识库里查找相关资料",
};

const SUMMARY_KEYWORD_TEXT: Array<{ keyword: string; text: string }> = [
  { keyword: "检索范围", text: "正在判断这个问题适合怎么查" },
  { keyword: "召回", text: "正在从选中的知识库里查找相关资料" },
  { keyword: "组织回答", text: "已找到可用资料，正在整理回答" },
];

const QUERY_SCOPE_TEXT: Record<string, string> = {
  global: "这个问题需要先看知识库整体概览",
  hybrid: "这个问题会同时查概览和具体片段",
};

const TRACE_TEXT_RESOLVERS: Record<string, TraceTextResolver> = {
  answer_cache: () => "命中以前验证过的回答，可以更快返回",
  candidate_scoring: (trace) => getCandidateScoringText(String(trace.metrics?.engine ?? "")),
  engine_fallback: () => "外部检索暂不可用，已切换备用检索方式",
  query_scope: (trace) => getQueryScopeText(String(trace.metrics?.query_scope ?? "")),
};

const EVENT_STEP_RESOLVERS: Record<string, (event: AgentEvent, context: ThinkingContext) => ThinkingStep[]> = {
  "answer.completed": () => [{ summary: "回答完成，已整理引用来源" }],
  "answer.delta": (_event, context) => context.hasAnswerDelta ? [] : [{ summary: "开始根据证据流式组织回答" }],
  "deep_search.plan": (event) => createDeepSearchPlanSteps(event),
  "deep_search.step": (event, context) => createDeepSearchStepSteps(event, context),
  "request.created": (event) => [createRequestCreatedStep(event)],
  "retrieval.progress": (event) => [{ summary: getProgressSummary(event.payload.summary, event.payload.stage) }],
  "retrieval.trace": (event) => createTraceSteps(event),
};

/**
 * 思考步骤生成上下文。
 *
 * @author lvdaxianerplus
 * @date 2026-06-06
 */
interface ThinkingContext {
  hasAnswerDelta: boolean;
  stepCount: number;
}

/**
 * 把检索进度事件转成用户友好的文案。
 *
 * @param summary - 后端 progress summary
 * @param stage - 后端 progress stage
 * @returns 用户可见文案
 * @author lvdaxianerplus
 * @date 2026-06-06
 */
function getProgressSummary(summary: unknown, stage: unknown): string {
  const stageText = String(stage ?? "");
  const raw = String(summary ?? "");
  return (
    PROGRESS_STAGE_TEXT[stageText]
    ?? SUMMARY_KEYWORD_TEXT.find((item) => raw.includes(item.keyword))?.text
    ?? raw
  ) || DEFAULT_PROGRESS_SUMMARY;
}

/**
 * 把 trace 步骤翻译成“思考中”面板展示文案。
 *
 * @param trace - 单条 trace 步骤
 * @returns 用户可见文案
 * @author lvdaxianerplus
 * @date 2026-06-06
 */
function getTraceStepText(trace: TraceStep): string {
  const stage = String(trace.stage ?? "");
  return TRACE_TEXT_RESOLVERS[stage]?.(trace) ?? String(trace.summary ?? DEFAULT_TRACE_SUMMARY);
}

/**
 * 取检索范围阶段的友好文案。
 *
 * @param queryScope - 后端检索范围标识
 * @returns 检索范围文案
 * @author lvdaxianerplus
 * @date 2026-06-06
 */
function getQueryScopeText(queryScope: string): string {
  return QUERY_SCOPE_TEXT[queryScope] ?? "已判断检索方式，准备查找相关资料";
}

/**
 * 取候选评分阶段的友好文案。
 *
 * @param engine - 后端检索引擎标识
 * @returns 候选评分文案
 * @author lvdaxianerplus
 * @date 2026-06-06
 */
function getCandidateScoringText(engine: string): string {
  return engine.includes("rerank")
    ? "正在把候选资料按相关性重新排序"
    : getFallbackCandidateScoringText(engine);
}

/**
 * 取候选评分阶段的降级友好文案。
 *
 * @param engine - 后端检索引擎标识
 * @returns 候选评分降级文案
 * @author lvdaxianerplus
 * @date 2026-06-06
 */
function getFallbackCandidateScoringText(engine: string): string {
  return engine.includes("fallback") || engine.includes("sqlite")
    ? "外部检索暂不可用，已改用本地资料匹配"
    : "正在筛选最可能有帮助的资料";
}

/**
 * 从事件流里抽取“思考中”步骤文案。
 *
 * @param events - 聊天消息事件流
 * @returns 步骤文案数组
 * @author lvdaxianerplus
 * @date 2026-06-06
 */
function getThinkingSteps(events: AgentEvent[] | undefined): ThinkingStep[] {
  const steps: ThinkingStep[] = [];
  const context: ThinkingContext = { hasAnswerDelta: false, stepCount: 0 };
  for (const event of events ?? []) {
    const nextSteps = createThinkingStepsFromEvent(event, context);
    steps.push(...nextSteps);
    context.stepCount = steps.length;
    context.hasAnswerDelta = context.hasAnswerDelta || event.event === "answer.delta";
  }
  return steps.length > 0 ? steps : [DEFAULT_THINKING_STEP];
}

/**
 * 将单个事件追加为思考步骤。
 *
 * @param event - 后端事件
 * @param steps - 步骤收集列表
 * @param hasAnswerDelta - 是否已经出现过回答 delta
 * @author lvdaxianerplus
 * @date 2026-06-06
 */
function createThinkingStepsFromEvent(
  event: AgentEvent,
  context: ThinkingContext,
): ThinkingStep[] {
  return EVENT_STEP_RESOLVERS[event.event]?.(event, context) ?? [];
}

/**
 * 将 retrieval.trace 数组追加为思考步骤。
 *
 * @param traceItems - trace 条目数组
 * @param steps - 步骤收集列表
 * @author lvdaxianerplus
 * @date 2026-06-06
 */
function createTraceSteps(event: AgentEvent): ThinkingStep[] {
  const traceItems = Array.isArray(event.payload.trace) ? event.payload.trace : [];
  return traceItems.map((item) => ({
    summary: getTraceStepText(item as TraceStep),
  }));
}

/**
 * 追加 DeepSearch 规划步骤。
 *
 * @param event - deep_search.plan 事件
 * @param steps - 步骤收集列表
 * @author lvdaxianerplus
 * @date 2026-06-06
 */
function createDeepSearchPlanSteps(event: AgentEvent): ThinkingStep[] {
  const intent = typeof event.payload.intent === "string" ? event.payload.intent : "";
  const planItems = Array.isArray(event.payload.cot_plan) ? event.payload.cot_plan : [];
  return [
    { summary: intent ? `DeepSearch：${intent}` : "DeepSearch 已生成公开检索计划" },
    ...planItems.map((item) => ({ summary: String(item) })),
  ];
}

/**
 * 追加 DeepSearch 子问题步骤。
 *
 * @param event - deep_search.step 事件
 * @param steps - 步骤收集列表
 * @author lvdaxianerplus
 * @date 2026-06-06
 */
function createDeepSearchStepSteps(
  event: AgentEvent,
  context: ThinkingContext,
): ThinkingStep[] {
  const index = Number(event.payload.index ?? context.stepCount + FIRST_ITEM_OFFSET);
  const subQuestion = String(event.payload.sub_question ?? "");
  const hitCount = Number(event.payload.hit_count ?? ZERO_HIT_COUNT);
  const topHits = Array.isArray(event.payload.top_hits) ? event.payload.top_hits : [];
  return [
    { summary: subQuestion ? `子问题 ${index}：${subQuestion}` : `子问题 ${index} 检索完成` },
    { summary: `命中 ${hitCount} 条资料` },
    ...createTopHitSteps(topHits),
  ];
}

/**
 * 追加最高相关命中步骤。
 *
 * @param topHits - 后端返回的 top_hits
 * @param steps - 步骤收集列表
 * @author lvdaxianerplus
 * @date 2026-06-06
 */
function createTopHitSteps(topHits: unknown[]): ThinkingStep[] {
  const firstHit = topHits[0] as { title?: unknown } | undefined;
  const title = firstHit ? String(firstHit.title ?? "") : "";
  return title ? [{ summary: `最高相关：${title}` }] : [];
}

/**
 * 生成收到问题的思考步骤。
 *
 * @param event - request.created 事件
 * @returns 收到问题步骤
 * @author lvdaxianerplus
 * @date 2026-06-06
 */
function createRequestCreatedStep(event: AgentEvent): ThinkingStep {
  const input = typeof event.payload.input === "string" ? event.payload.input : "";
  return { summary: input ? `收到问题：「${input}」` : "收到问题，准备进入检索链路" };
}

/**
 * 聊天消息的思考过程面板。
 *
 * @param props - events 为事件流，isStreaming 表示是否正在生成
 * @returns 思考过程 UI
 * @author lvdaxianerplus
 * @date 2026-06-06
 */
export function ThinkingPanel({
  events,
  isStreaming,
}: {
  events: AgentEvent[] | undefined;
  isStreaming: boolean;
}) {
  const steps = getThinkingSteps(events);
  return (
    <details
      className="group rounded-lg border border-slate-200 bg-white p-3 shadow-xs transition-shadow hover:shadow-sm open:bg-slate-50/40"
      open={isStreaming}
    >
      <summary className="inline-flex cursor-pointer list-none items-center gap-2 text-slate-500 select-none [&::-webkit-details-marker]:hidden">
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
