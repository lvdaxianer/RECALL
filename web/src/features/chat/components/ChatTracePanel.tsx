/**
 * Recall · 聊天抽屉里的 Trace 面板（行内版，区别于 Sheet 版 EvidenceSheet）。
 *
 * 同时显示引用表 + Trace 卡片。
 * 复用 `runtime/traceAdapters` 公共工具，避免在多处重复实现 trace 解析。
 *
 * @author lvdaxianerplus
 */
import type { AgentEvent } from "../../../api/sessions";
import {
  extractCitations,
  extractTraceSummaries,
  formatScore,
} from "../runtime/traceAdapters";

/**
 * 聊天 Trace 面板 props 集合。
 *
 * @author lvdaxianerplus
 */
export interface ChatTracePanelProps {
  /** 事件流 */
  events: AgentEvent[];
}

/**
 * 取引用片段的展示文本，按 content → snippet → chunk_id → "-" 兜底。
 *
 * @param item 引用条目
 * @returns 展示文本
 * @author lvdaxianerplus
 */
function getCitationSnippet(item: { content?: string; snippet?: string; chunk_id?: string }): string {
  return String(item.content ?? item.snippet ?? item.chunk_id ?? "-");
}

/**
 * Trace 面板组件。
 *
 * @param props.events 事件流
 * @author lvdaxianerplus
 */
export function ChatTracePanel({ events }: ChatTracePanelProps) {
  // 1. 公共工具拿 trace 摘要 + 引用
  const items = extractTraceSummaries(events);
  const citations = extractCitations(events);
  // 2. 完全空态：直接显示"暂无 trace"
  if (items.length === 0 && citations.length === 0) {
    return <span className="text-sm text-slate-500">暂无 trace</span>;
  }
  return (
    <div className="grid gap-3">
      {/* 引用区：紧凑表格 */}
      {citations.length > 0 ? (
        <section className="rounded-lg border border-slate-200 bg-slate-50 p-3">
          <strong className="mb-3 block text-sm font-semibold text-slate-900">引用来源</strong>
          <div className="max-w-full overflow-x-auto">
            <table className="w-full min-w-[520px] border-collapse rounded-md border border-slate-200 bg-white text-sm">
              <thead>
                <tr>
                  <th className="whitespace-nowrap border-b border-slate-200 bg-slate-50 px-2.5 py-2 text-left font-semibold text-slate-900">文档</th>
                  <th className="border-b border-slate-200 bg-slate-50 px-2.5 py-2 text-left font-semibold text-slate-900">标题</th>
                  <th className="border-b border-slate-200 bg-slate-50 px-2.5 py-2 text-left font-semibold text-slate-900">命中片段</th>
                  <th className="whitespace-nowrap border-b border-slate-200 bg-slate-50 px-2.5 py-2 text-left font-semibold text-slate-900">分数</th>
                </tr>
              </thead>
              <tbody>
                {citations.map((item, index) => (
                  <tr key={`${item.chunk_id ?? "citation"}-${index}`} className="last:border-b-0 hover:bg-slate-50">
                    <td className="border-b border-slate-200 px-2.5 py-2 align-top text-slate-500">{item.document_name ?? "-"}</td>
                    <td className="border-b border-slate-200 px-2.5 py-2 align-top text-slate-500">{item.title ?? "-"}</td>
                    <td className="min-w-[220px] border-b border-slate-200 px-2.5 py-2 align-top leading-6 text-slate-900 break-words">{getCitationSnippet(item)}</td>
                    <td className="border-b border-slate-200 px-2.5 py-2 align-top font-mono text-xs text-slate-700">{formatScore(item.score)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}
      {/* Trace 摘要卡片列表 */}
      <div className="grid gap-2">
        {items.map((item, index) => (
          <div className="rounded-md border border-slate-200 bg-white p-2.5" key={`${item.title}-${index}`}>
            <strong className="block text-sm text-slate-900">{item.title}</strong>
            <span className="block text-sm text-slate-500">{item.summary}</span>
            {/* meta 字段（如 metrics 序列化）以等宽字体展示 */}
            {item.meta ? <small className="font-mono text-xs text-slate-500 break-words">{item.meta}</small> : null}
          </div>
        ))}
      </div>
    </div>
  );
}
