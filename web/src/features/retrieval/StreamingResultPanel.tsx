/**
 * Recall · 检索控制台流式输出面板
 *
 * v1.3 起从 `common` 重新导出改成从 `recall/RetrievalResult` 透传。
 * 保留独立文件以便未来加入"复制"按钮 / "导出 Markdown"等控制项。
 *
 * @author lvdaxianerplus
 */
import { RetrievalResult } from "../../components/recall/RetrievalResult";

/**
 * StreamingResultPanel props 集合。
 *
 * @author lvdaxianerplus
 */
export interface StreamingResultPanelProps {
  /** 累积输出文本 */
  output: string;
  /** 当前状态（streaming / success / error） */
  status: string;
  /** 耗时（毫秒），可选 */
  durationMs?: number;
}

/**
 * 检索控制台流式输出面板。
 *
 * @param props.output 输出文本
 * @param props.status 状态
 * @param props.durationMs 耗时
 * @author lvdaxianerplus
 */
export function StreamingResultPanel({ output, status, durationMs }: StreamingResultPanelProps) {
  // 直接透传：保留独立文件是给将来扩展用
  return <RetrievalResult durationMs={durationMs} output={output} status={status} />;
}
