/**
 * Recall · 证据面板（行内版）
 *
 * 在聊天右栏 / 设置弹框里内联渲染，不走 Sheet Portal、不开新弹框；
 * 同时显示"引用 + Trace"两个区。引用解析、Trace 解析、评分档位映射
 * 全部走 `traceAdapters` 公共工具，避免在多处重复实现。
 *
 * 设计要点：
 * 1. 完全空态（无引用 + 无 trace）走单行"暂无证据"，避免空 section 占据视觉
 * 2. 每条引用配 dot + 文档名 + 分数 + 标题 + Markdown 片段
 * 3. 评分档位（emerald/amber/red）→ 圆点颜色（策略模式替代 if 链）
 * 4. Markdown 样式走 prose 原子类（&_* 覆盖）而非组件级 wrapper
 * 5. 列表 key 用 chunk_id 兜底文档名 + 索引，保证同名 chunk 不冲突
 * 6. 引用列表 + Trace 摘要 + 时间线三段独立展示
 * 7. 卡片有 hover 提升（-translate-y-0.5 + shadow-sm）以增加可点击感
 *
 * @author lvdaxianerplus
 */
import type { AgentEvent } from "../../api/sessions";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { TraceTimeline } from "./TraceTimeline";
// 引用 / Trace 解析、评分格式化与档位映射走公共工具
import {
  extractCitations,
  extractTraceSummaries,
  formatScore,
  getScoreBand,
  type CitationItem,
} from "../../features/chat/runtime/traceAdapters";
import { cn } from "../../lib/utils";

/**
 * 评分档位 → 圆点颜色映射（策略模式替代 if 链）。
 *
 * @author lvdaxianerplus
 */
const SCORE_BAND_DOT: Record<"emerald" | "amber" | "red", string> = {
  emerald: "bg-emerald-500",
  amber: "bg-amber-500",
  red: "bg-red-500",
};

/**
 * 证据面板 props 集合。
 *
 * @author lvdaxianerplus
 */
export interface EvidencePanelProps {
  /** 事件流 */
  events: AgentEvent[];
}

/**
 * 证据面板组件。
 *
 * @param props.events 事件流
 * @author lvdaxianerplus
 */
export function EvidencePanel({ events }: EvidencePanelProps) {
  // 1. 提前解析两个区共用的数据，避免在 JSX 中重复遍历
  const citations: CitationItem[] = extractCitations(events);
  const traceItems = extractTraceSummaries(events);

  // 2. 完全空态：直接展示"暂无证据"，避免空 section 占据视觉
  if (citations.length === 0 && traceItems.length === 0) {
    return <p className="text-sm text-slate-500">暂无证据</p>;
  }

  return (
    <div className="flex flex-col gap-4">
      {/* 引用区：每条引用配 dot + 文档名 + 分数 + 标题 + Markdown 片段 */}
      {citations.length > 0 ? (
        <section>
          <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
            引用来源（{citations.length}）
          </h3>
          <ul className="space-y-2">
            {citations.map((citation, index) => {
              // 评分档位决定圆点配色（高/中/低）
              const band = getScoreBand(citation.score);
              return (
                <li
                  // key 用 chunk_id 兜底文档名 + 索引，保证同名 chunk 也不冲突
                  key={`${citation.chunk_id ?? "citation"}-${index}`}
                  className="rounded-lg border border-slate-200 bg-white p-3 shadow-xs transition-all hover:-translate-y-0.5 hover:border-slate-300 hover:shadow-sm"
                >
                  <header className="mb-1.5 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
                    {/* 评分档位圆点 */}
                    <span
                      aria-hidden="true"
                      className={cn("size-1.5 rounded-full", SCORE_BAND_DOT[band])}
                    />
                    <span className="truncate text-slate-700">{citation.document_name}</span>
                    {/* 分数小标签（右对齐） */}
                    <span className="ml-auto rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[11px] text-slate-700">
                      {formatScore(citation.score)}
                    </span>
                  </header>
                  <p className="text-xs font-medium text-slate-900">{citation.title}</p>
                  {/* Markdown 片段：使用极简 prose 样式，限制字号、行高、链接配色 */}
                  <div className="mt-1 text-xs leading-5 text-slate-700 [&_a]:font-medium [&_a]:text-emerald-700 [&_code]:rounded [&_code]:bg-slate-100 [&_code]:px-1 [&_code]:font-mono [&_p]:m-0 [&_ul]:m-0 [&_ul]:list-disc [&_ul]:pl-4 [&_ol]:m-0 [&_ol]:list-decimal [&_ol]:pl-4 [&_pre]:my-1 [&_pre]:rounded [&_pre]:bg-slate-100 [&_pre]:p-1 [&_pre]:font-mono [&_pre]:text-[0.85em] [&_h1]:text-sm [&_h1]:font-semibold [&_h2]:text-sm [&_h2]:font-semibold [&_h3]:text-xs [&_h3]:font-semibold [&_blockquote]:border-l-2 [&_blockquote]:border-slate-300 [&_blockquote]:pl-2 [&_blockquote]:text-slate-500 [&_img]:max-h-32 [&_img]:rounded [&_img]:border [&_img]:border-slate-200">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>
                      {citation.content ?? ""}
                    </ReactMarkdown>
                  </div>
                </li>
              );
            })}
          </ul>
        </section>
      ) : null}
      {/* Trace 区：每条 trace 摘要 + 时间线 */}
      {traceItems.length > 0 ? (
        <section>
          <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
            Trace（{traceItems.length}）
          </h3>
          <div className="space-y-2">
            {traceItems.map((item, index) => (
              <div
                className="rounded-lg border border-slate-200 bg-slate-50/60 p-2.5"
                key={`${item.title}-${index}`}
              >
                <strong className="block text-xs font-semibold text-slate-900">{item.title}</strong>
                <span className="mt-0.5 block text-xs text-slate-600">{item.summary}</span>
                {item.meta ? (
                  <small className="mt-0.5 block break-words font-mono text-[11px] text-slate-500">
                    {item.meta}
                  </small>
                ) : null}
              </div>
            ))}
            <TraceTimeline events={events} />
          </div>
        </section>
      ) : null}
    </div>
  );
}
