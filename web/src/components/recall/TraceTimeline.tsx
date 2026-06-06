/**
 * Recall · Trace 事件时间线
 *
 * 把后端事件流展开为可读卡片列表：每条 trace 配 stage 徽章 + summary + metrics 列表 + duration。
 * 复用 `traceAdapters` 的公共摘要解析，自身只负责渲染与时间线专用格式化（duration_ms / stage_durations_ms）。
 *
 * @author lvdaxianerplus
 */
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
// 通用 trace 摘要解析器
import { extractTraceSummaries } from "../../features/chat/runtime/traceAdapters";

/**
 * 单条 trace 条目的视图模型。
 *
 * @author lvdaxianerplus
 */
export interface TraceEntry {
  stage: string;
  summary: string;
  metrics: string[];
  duration?: string;
}

/**
 * 需要在 metrics 中展示的固定 key 列表（顺序敏感）。
 *
 * @author lvdaxianerplus
 */
const METRIC_KEYS = ["query_scope", "route_plan", "strategy", "result_count", "duration_ms"] as const;

/**
 * 通用事件流类型（兼容 AgentEvent / StreamEvent）。
 *
 * @author lvdaxianerplus
 */
export type TimelineEvent = { event: string; payload?: Record<string, unknown> };

/**
 * 把单个 metric value 格式化为可读字符串。
 *
 * @param value 任意 metric 值
 * @returns 可读字符串
 * @author lvdaxianerplus
 */
function formatMetricValue(value: unknown): string {
  if (Array.isArray(value)) {
    return value.map(String).join(", ");
  }
  if (typeof value !== "object" || value === null) {
    return String(value);
  }
  return Object.entries(value as Record<string, unknown>)
    .slice(0, 3)
    .map(([key, nestedValue]) => `${key}=${formatMetricValue(nestedValue)}`)
    .join(", ");
}

/**
 * 按 METRIC_KEYS 顺序过滤并格式化 metrics。
 *
 * @param metrics 原始 metrics 对象
 * @returns 形如 `["key1: val1", ...]` 的字符串数组
 * @author lvdaxianerplus
 */
function formatMetrics(metrics: Record<string, unknown>): string[] {
  return METRIC_KEYS.filter((key) => metrics[key] !== undefined)
    .map((key) => `${key}: ${formatMetricValue(metrics[key])}`);
}

/**
 * 把 `stage_durations_ms` 字典展开为可读字符串数组。
 *
 * @param value 任意值
 * @returns 形如 `["retrieval: 120ms", ...]` 的数组
 * @author lvdaxianerplus
 */
function formatStageDurations(value: unknown): string[] {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return [];
  }
  return Object.entries(value as Record<string, unknown>).map(
    ([key, duration]) => `${key}: ${formatMetricValue(duration)}`,
  );
}

/**
 * 格式化毫秒级时长。无法识别时返回 null。
 *
 * @param value 任意值
 * @returns 形如 `120ms`，无法识别时返回 null
 * @author lvdaxianerplus
 */
function formatDuration(value: unknown): string | null {
  if (typeof value !== "number") {
    return null;
  }
  return `${Math.round(value)}ms`;
}

/**
 * 从事件流构建 trace 条目。
 * 1. 对 `retrieval.trace.payload.trace` 数组：每条都展开成 trace 条目（含 metrics）。
 * 2. 对 `answer.completed`：单条 answer 完成条目（含 duration_ms + stage_durations_ms）。
 * 3. `retrieval.progress` / `answer.delta`：直接复用 extractTraceSummaries。
 *
 * @param events 事件流
 * @returns trace 条目数组
 * @author lvdaxianerplus
 */
function buildEntries(events: ReadonlyArray<TimelineEvent>): TraceEntry[] {
  const entries: TraceEntry[] = [];
  for (const event of events) {
    const payload = (event.payload ?? {}) as Record<string, unknown>;
    if (event.event === "retrieval.trace" && Array.isArray(payload.trace)) {
      for (const item of payload.trace) {
        const trace = item as { stage?: string; summary?: string; metrics?: Record<string, unknown> };
        entries.push({
          stage: String(trace.stage ?? "trace"),
          summary: String(trace.summary ?? "已记录检索阶段"),
          metrics: formatMetrics(trace.metrics ?? {}),
        });
      }
      continue;
    }
    if (event.event === "answer.completed" && payload.duration_ms !== undefined) {
      const durationMs = Number(payload.duration_ms);
      entries.push({
        stage: "answer.completed",
        summary: "回答生成完成",
        metrics: [
          `duration_ms: ${formatMetricValue(durationMs)}`,
          ...formatStageDurations(payload.stage_durations_ms),
        ],
        duration: formatDuration(durationMs) ?? undefined,
      });
      continue;
    }
    // answer.delta 的「命中片段」由引用面板单独展示，这里跳过避免重复。
    if (event.event === "answer.delta") {
      continue;
    }
    // 其余事件（retrieval.progress 等）：复用公共摘要 + 显示 duration_ms。
    for (const summary of extractTraceSummaries([event])) {
      const durationMs = payload.duration_ms;
      entries.push({
        stage: summary.title,
        summary: summary.summary,
        metrics: [],
        duration: typeof durationMs === "number" ? formatDuration(durationMs) ?? undefined : undefined,
      });
    }
  }
  return entries;
}

/**
 * Trace 事件时间线：把事件流展开为可读卡片列表。
 *
 * @author lvdaxianerplus
 */
export interface TraceTimelineProps {
  events: ReadonlyArray<TimelineEvent>;
}

/**
 * Trace 时间线组件。
 *
 * @param props.events 事件流
 * @author lvdaxianerplus
 */
export function TraceTimeline({ events }: TraceTimelineProps) {
  const entries = buildEntries(events);
  if (entries.length === 0) {
    return <span className="text-sm text-muted-foreground">暂无 Trace</span>;
  }

  return (
    <div className="space-y-2">
      {entries.map((item, index) => (
        <Card key={`${item.stage}-${index}`} className="border-muted">
          <CardContent className="flex items-start justify-between gap-3 p-3">
            <div className="min-w-0 space-y-1">
              <Badge variant="secondary">{item.stage}</Badge>
              <p className="break-words text-sm text-muted-foreground">{item.summary}</p>
              {item.metrics.length > 0 ? (
                <ul className="space-y-1 text-xs text-muted-foreground">
                  {item.metrics.map((metric) => <li key={metric}>{metric}</li>)}
                </ul>
              ) : null}
            </div>
            {item.duration ? (
              <span className="shrink-0 font-mono text-xs text-muted-foreground">{item.duration}</span>
            ) : null}
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
