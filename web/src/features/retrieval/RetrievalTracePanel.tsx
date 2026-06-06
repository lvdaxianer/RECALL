/**
 * Recall · 检索控制台 Trace 面板（轻量壳）
 *
 * 历史上这里有一份独立的 trace 渲染逻辑；v1.3 起直接复用 `TraceTimeline` 组件。
 * 本文件保留为薄壳，便于将来插入"搜索/过滤"等控制项。
 *
 * @author lvdaxianerplus
 */
import { TraceTimeline } from "../../components/recall/TraceTimeline";

/**
 * 检索控制台 Trace 面板 props。
 *
 * @author lvdaxianerplus
 */
export interface RetrievalTracePanelProps {
  /** 事件流（来自流式累积） */
  trace: Array<{ event: string; payload?: Record<string, unknown> }>;
}

/**
 * 检索控制台 Trace 面板。
 *
 * @param props.trace 事件流
 * @author lvdaxianerplus
 */
export function RetrievalTracePanel({ trace }: RetrievalTracePanelProps) {
  return (
    // 简单壳：未来要加搜索/过滤就在这里挂
    <div className="trace-panel">
      <h3 className="text-sm font-semibold text-slate-900">Trace</h3>
      <TraceTimeline events={trace} />
    </div>
  );
}
