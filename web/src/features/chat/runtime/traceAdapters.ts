import type { AgentEvent } from "../../../api/sessions";
import type { StreamEvent } from "../../../hooks/useRetrievalStream";

/**
 * 通用事件流类型（兼容 AgentEvent / StreamEvent）。
 *
 * @author lvdaxianerplus
 */
export type TimelineEvent = { event: string; payload?: Record<string, unknown> };

/**
 * 接受任意后端事件类型；调用方可以传入 AgentEvent[] / StreamEvent[]，内部按 event 字段统一处理。
 *
 * @author lvdaxianerplus
 */
export type AnyBackendEvent = AgentEvent | StreamEvent;

/**
 * Trace 阶段标题映射：阶段 ID → 中文标题。
 * 用于统一 chat 抽屉、证据面板、TraceTimeline 的标题展示。
 *
 * @author lvdaxianerplus
 */
export const STAGE_LABELS: Record<string, string> = {
  query_scope: "查询范围",
  candidate_scoring: "候选评分",
  engine_fallback: "降级检索",
};

/**
 * 取阶段的中文标题，未匹配时回退到原始 stage 字符串。
 *
 * @param stage 阶段 ID（后端事件中的 stage 字段）
 * @returns 中文标题
 * @author lvdaxianerplus
 */
export function getStageTitle(stage: string): string {
  return STAGE_LABELS[stage] ?? stage;
}

/**
 * 单条引用（来自后端 `answer.completed.payload.results`）。
 *
 * @author lvdaxianerplus
 */
export interface CitationItem {
  chunk_id?: string;
  document_name?: string;
  title?: string;
  content?: string;
  snippet?: string;
  text?: string;
  score?: number;
}

/**
 * 评分等级：用于给引用点上不同颜色。
 *
 * @author lvdaxianerplus
 */
export type ScoreBand = "emerald" | "amber" | "red";

/**
 * Trace 摘要条目：标题 + 摘要 + 可选指标元信息。
 *
 * @author lvdaxianerplus
 */
export interface TraceSummaryItem {
  title: string;
  summary: string;
  meta?: string;
}

/**
 * 从事件流中抽取引用（citations）列表。
 * 仅当事件类型为 `answer.completed` 且 `payload.results` 为数组时返回非空结果。
 *
 * @param events 任意事件数组（兼容 AgentEvent / StreamEvent）
 * @returns 归一化后的引用列表
 * @author lvdaxianerplus
 */
export function extractCitations(events: ReadonlyArray<TimelineEvent>): CitationItem[] {
  const result: CitationItem[] = [];
  for (const event of events) {
    if (event.event !== "answer.completed") {
      continue;
    }
    const payload = event.payload as { results?: unknown } | undefined;
    if (!Array.isArray(payload?.results)) {
      continue;
    }
    for (const raw of payload.results) {
      result.push(normalizeCitation(raw));
    }
  }
  return result;
}

/**
 * 把后端返回的引用条目归一化为前端视图模型。
 * 字段缺失时使用兜底字符串，保证 UI 渲染安全。
 *
 * @param raw 后端原始条目
 * @returns 归一化后的引用条目
 * @author lvdaxianerplus
 */
export function normalizeCitation(raw: unknown): CitationItem {
  const item = (raw ?? {}) as Record<string, unknown>;
  return {
    chunk_id: item.chunk_id !== undefined ? String(item.chunk_id) : undefined,
    document_name: String(item.document_name ?? item.source ?? item.document_id ?? "未知来源"),
    title: String(item.title ?? "-"),
    content: String(item.content ?? item.snippet ?? item.text ?? item.chunk_text ?? "暂无片段"),
    score: typeof item.score === "number" ? item.score : undefined,
  };
}

/**
 * 从事件流中抽取 trace 摘要条目。
 * 处理三类事件：
 *   - `retrieval.trace.payload.trace` 数组 → 多条目
 *   - `retrieval.progress` → 单条进度
 *   - `answer.delta.payload.chunk_id` → 命中片段
 *
 * @param events 事件流
 * @returns trace 摘要条目数组（可能为空）
 * @author lvdaxianerplus
 */
export function extractTraceSummaries(events: ReadonlyArray<TimelineEvent>): TraceSummaryItem[] {
  const items: TraceSummaryItem[] = [];
  for (const event of events) {
    const payload = (event.payload ?? {}) as Record<string, unknown>;
    if (event.event === "retrieval.trace" && Array.isArray(payload.trace)) {
      for (const raw of payload.trace) {
        const trace = raw as { stage?: string; summary?: string; metrics?: Record<string, unknown> };
        items.push({
          title: getStageTitle(String(trace.stage ?? "trace")),
          summary: String(trace.summary ?? "已记录检索阶段"),
          meta: trace.metrics ? JSON.stringify(trace.metrics) : undefined,
        });
      }
      continue;
    }
    if (event.event === "retrieval.progress") {
      items.push({
        title: getStageTitle(String(payload.stage ?? "retrieval.progress")),
        summary: String(payload.summary ?? "检索处理中"),
      });
      continue;
    }
    if (event.event === "answer.delta" && payload.chunk_id !== undefined) {
      const summary = String(payload.content ?? payload.snippet ?? payload.text ?? payload.title ?? "已命中片段");
      items.push({
        title: "命中片段",
        summary,
        meta: `chunk_id: ${String(payload.chunk_id)}`,
      });
    }
  }
  return items;
}

/**
 * 把评分映射到颜色档位：
 *   - `>= 0.85` → emerald（高置信）
 *   - `>= 0.40` → amber（中等）
 *   - 其它      → red（弱相关）
 *
 * @param score 评分（可选）
 * @returns 颜色档位
 * @author lvdaxianerplus
 */
export function getScoreBand(score: number | undefined): ScoreBand {
  if (typeof score !== "number") {
    return "amber";
  }
  if (score >= 0.85) {
    return "emerald";
  }
  if (score >= 0.4) {
    return "amber";
  }
  return "red";
}

/**
 * 把分值格式化为 3 位小数字符串。
 *
 * @param score 评分（可选）
 * @returns 形如 `0.923`，缺省返回 `-`
 * @author lvdaxianerplus
 */
export function formatScore(score: number | undefined): string {
  return typeof score === "number" ? score.toFixed(3) : "-";
}
