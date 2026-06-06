import type { AgentEvent } from "../../../api/sessions";

const MILLISECONDS_PER_SECOND = 1000;
const ZERO_DURATION_MS = 0;
const UNKNOWN_STAGE_ORDER = 999;

const STAGE_DURATION_LABELS: Record<string, string> = {
  answer_cache: "缓存检查",
  answer_generation: "回答生成",
  candidate_scoring: "候选评分",
  deep_search_planning: "深度检索规划",
  engine_fallback: "降级检索",
  query_scope: "范围判断",
  retrieval: "检索",
};

const STAGE_DURATION_ORDER: Record<string, number> = {
  answer_cache: 10,
  deep_search_planning: 20,
  query_scope: 30,
  retrieval: 40,
  candidate_scoring: 50,
  engine_fallback: 60,
  answer_generation: 70,
};

/**
 * 单个阶段耗时展示项。
 *
 * @author lvdaxianerplus
 * @date 2026-06-06
 */
interface StageDurationItem {
  key: string;
  label: string;
  durationMs: number;
}

/**
 * 回答耗时汇总，包含总耗时与阶段拆分。
 *
 * @author lvdaxianerplus
 * @date 2026-06-06
 */
export interface TimingSummary {
  totalDurationMs?: number;
  stages: StageDurationItem[];
}

/**
 * 格式化耗时（毫秒 -> ms / s）。
 *
 * @param durationMs - 毫秒数
 * @returns 形如 `1.23s` 或 `120ms`
 * @author lvdaxianerplus
 * @date 2026-06-06
 */
export function formatDuration(durationMs: number): string {
  return durationMs >= MILLISECONDS_PER_SECOND
    ? `${(durationMs / MILLISECONDS_PER_SECOND).toFixed(2)}s`
    : `${Math.max(ZERO_DURATION_MS, Math.round(durationMs))}ms`;
}

/**
 * 把未知值转换成可展示的毫秒数。
 *
 * @param value - 后端事件中的耗时字段
 * @returns 有效毫秒数，无法解析时返回 undefined
 * @author lvdaxianerplus
 * @date 2026-06-06
 */
function toDurationMs(value: unknown): number | undefined {
  const parsed = typeof value === "string" && value.trim() ? Number(value) : value;
  return typeof parsed === "number" && Number.isFinite(parsed) ? parsed : undefined;
}

/**
 * 生成阶段耗时的中文标签。
 *
 * @param stage - 后端阶段名
 * @param answerCacheHit - 是否命中回答缓存
 * @returns 用户可读的阶段名称
 * @author lvdaxianerplus
 * @date 2026-06-06
 */
function getStageDurationLabel(stage: string, answerCacheHit: boolean): string {
  return stage === "answer_cache" && answerCacheHit
    ? "命中缓存"
    : STAGE_DURATION_LABELS[stage] ?? stage.replaceAll("_", " ");
}

/**
 * 取阶段排序权重，未知阶段放到最后。
 *
 * @param stage - 后端阶段名
 * @returns 排序权重
 * @author lvdaxianerplus
 * @date 2026-06-06
 */
function getStageOrder(stage: string): number {
  return STAGE_DURATION_ORDER[stage] ?? UNKNOWN_STAGE_ORDER;
}

/**
 * 从事件流中抽取回答耗时汇总。
 *
 * @param events - 聊天消息事件流
 * @param fallbackDurationMs - 无后端总耗时时的本地兜底耗时
 * @returns 耗时汇总；没有任何耗时信息时返回 undefined
 * @author lvdaxianerplus
 * @date 2026-06-06
 */
export function getLatestAnswerTiming(
  events: AgentEvent[] | undefined,
  fallbackDurationMs?: number,
): TimingSummary | undefined {
  const completed = [...(events ?? [])]
    .reverse()
    .find((event) => event.event === "answer.completed");
  const payload = (completed?.payload ?? {}) as Record<string, unknown>;
  const answerCacheHit = payload.answer_cache_hit === true;
  const stageDurations = new Map<string, StageDurationItem>();

  collectStageDurationsFromAnswer(payload, answerCacheHit, stageDurations);
  collectStageDurationsFromTrace(events, stageDurations);

  const totalDurationMs = toDurationMs(payload.duration_ms) ?? fallbackDurationMs;
  const stages = [...stageDurations.values()].sort(
    (left, right) => getStageOrder(left.key) - getStageOrder(right.key),
  );

  return totalDurationMs === undefined && stages.length === 0
    ? undefined
    : { totalDurationMs, stages };
}

/**
 * 从 answer.completed 事件中收集阶段耗时。
 *
 * @param payload - answer.completed 的 payload
 * @param answerCacheHit - 是否命中回答缓存
 * @param stageDurations - 阶段耗时收集表
 * @author lvdaxianerplus
 * @date 2026-06-06
 */
function collectStageDurationsFromAnswer(
  payload: Record<string, unknown>,
  answerCacheHit: boolean,
  stageDurations: Map<string, StageDurationItem>,
): void {
  const rawDurations = payload.stage_durations_ms;
  const entries = typeof rawDurations === "object" && rawDurations !== null
    ? Object.entries(rawDurations as Record<string, unknown>)
    : [];
  entries
    .map(([stage, rawDuration]) => createStageDurationItem(stage, rawDuration, answerCacheHit))
    .filter((item): item is StageDurationItem => item !== undefined)
    .forEach((item) => stageDurations.set(item.key, item));
}

/**
 * 从 retrieval.trace 事件中补充阶段耗时。
 *
 * @param events - 聊天消息事件流
 * @param stageDurations - 阶段耗时收集表
 * @author lvdaxianerplus
 * @date 2026-06-06
 */
function collectStageDurationsFromTrace(
  events: AgentEvent[] | undefined,
  stageDurations: Map<string, StageDurationItem>,
): void {
  (events ?? [])
    .flatMap((event) => getTraceItems(event))
    .map((item) => createTraceStageDurationItem(item, stageDurations))
    .filter((item): item is StageDurationItem => item !== undefined)
    .forEach((item) => stageDurations.set(item.key, item));
}

/**
 * 将 answer.completed 中的阶段耗时转换成展示项。
 *
 * @param stage - 后端阶段名
 * @param rawDuration - 原始耗时字段
 * @param answerCacheHit - 是否命中回答缓存
 * @returns 阶段耗时展示项；无有效耗时时返回 undefined
 * @author lvdaxianerplus
 * @date 2026-06-06
 */
function createStageDurationItem(
  stage: string,
  rawDuration: unknown,
  answerCacheHit: boolean,
): StageDurationItem | undefined {
  const durationMs = toDurationMs(rawDuration);
  return durationMs === undefined
    ? undefined
    : {
      key: stage,
      label: getStageDurationLabel(stage, answerCacheHit),
      durationMs,
    };
}

/**
 * 从 retrieval.trace 事件中安全读取 trace 条目。
 *
 * @param event - 后端事件
 * @returns trace 条目数组；非 retrieval.trace 时返回空数组
 * @author lvdaxianerplus
 * @date 2026-06-06
 */
function getTraceItems(event: AgentEvent): unknown[] {
  return event.event === "retrieval.trace" && Array.isArray(event.payload.trace)
    ? event.payload.trace
    : [];
}

/**
 * 将单条 trace 转换成阶段耗时展示项。
 *
 * @param item - retrieval.trace.payload.trace 条目
 * @param stageDurations - 已收集阶段耗时，用于去重
 * @returns 阶段耗时展示项；无有效耗时时返回 undefined
 * @author lvdaxianerplus
 * @date 2026-06-06
 */
function createTraceStageDurationItem(
  item: unknown,
  stageDurations: Map<string, StageDurationItem>,
): StageDurationItem | undefined {
  const trace = item as { stage?: unknown; metrics?: Record<string, unknown> };
  const stage = typeof trace.stage === "string" ? trace.stage : "";
  const durationMs = toDurationMs(trace.metrics?.duration_ms);
  return stage && !stageDurations.has(stage) && durationMs !== undefined
    ? {
      key: stage,
      label: getStageDurationLabel(stage, false),
      durationMs,
    }
    : undefined;
}

/**
 * 聊天消息里的阶段耗时摘要条。
 *
 * @param props - timing 为耗时汇总，缺省时不渲染
 * @returns 阶段耗时 UI
 * @author lvdaxianerplus
 * @date 2026-06-06
 */
export function TimingSummarySection({ timing }: { timing: TimingSummary | undefined }) {
  return timing && timing.stages.length > 0 ? (
    <section className="rounded-xl border border-slate-200 bg-slate-50/80 px-3 py-2.5 shadow-xs">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-[11px] font-medium tracking-wide text-slate-500">阶段耗时</span>
        {timing.totalDurationMs !== undefined ? (
          <span className="inline-flex items-center rounded-full bg-white px-2.5 py-1 font-mono text-[11px] font-medium text-slate-700 shadow-xs">
            总耗时 {formatDuration(timing.totalDurationMs)}
          </span>
        ) : null}
        {timing.stages.map((item) => (
          <span
            key={`${item.key}-${item.durationMs}`}
            className="inline-flex items-center rounded-full border border-slate-200 bg-white px-2.5 py-1 font-mono text-[11px] text-slate-600 shadow-xs"
          >
            {item.label} {formatDuration(item.durationMs)}
          </span>
        ))}
      </div>
    </section>
  ) : undefined;
}
