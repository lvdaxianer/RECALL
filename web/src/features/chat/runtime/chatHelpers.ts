import type { AgentEvent } from "../../../api/sessions";

/**
 * 取最近一条 `retrieval.progress` 的 summary。
 *
 * @param events 事件流
 * @returns summary 文案，缺省返回 `"正在检索证据"`
 * @author lvdaxianerplus
 */
export function getLatestProgressSummary(events: AgentEvent[] | undefined): string {
  const progress = [...(events ?? [])]
    .reverse()
    .find((event) => event.event === "retrieval.progress" && typeof event.payload.summary === "string");
  return typeof progress?.payload.summary === "string" ? progress.payload.summary : "正在检索证据";
}
