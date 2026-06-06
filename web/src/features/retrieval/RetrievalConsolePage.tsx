/**
 * Recall · 检索控制台
 *
 * 流程：选 KB → 输问题 → 启动流式检索 → 实时看输出 + trace。
 * 与 EvaluationPage 的区别：本页参与实时调试（暴露每条 stream 事件）。
 *
 * @author lvdaxianerplus
 */
import { useEffect, useState } from "react";

import type { KnowledgeBase } from "../../api/types";
import { ErrorState } from "../../components/common/ErrorState";
import { LoadingState } from "../../components/common/LoadingState";
import { Multiselect } from "../../components/common/Multiselect";
import { SectionCard } from "../../components/common/SectionCard";
import { MetricStrip } from "../../components/recall/MetricStrip";
import { PageHeader } from "../../components/recall/PageHeader";
import { Button } from "../../components/ui/button";
import { Textarea } from "../../components/ui/textarea";
import { useKnowledgeBases } from "../../hooks/useKnowledgeBases";
import { appendStreamEvent, readRetrievalStream, type StreamState } from "../../hooks/useRetrievalStream";
import { KB_STATUS } from "../chat/runtime/chatConstants";
import { RetrievalTracePanel } from "./RetrievalTracePanel";
import { StreamingResultPanel } from "./StreamingResultPanel";

/**
 * 判断 KB 是否对检索可见（必须已发布）。
 *
 * @param item KB 视图模型
 * @returns 是否可检索
 * @author lvdaxianerplus
 */
function isPublishedKnowledgeBase(item: KnowledgeBase): boolean {
  return item.status === KB_STATUS.PUBLISHED;
}

/**
 * 检索控制台组件。
 *
 * @author lvdaxianerplus
 */
export function RetrievalConsolePage() {
  // 1. 拉取 KB 列表
  const { items: knowledgeBases, isLoading, isError, refetch } = useKnowledgeBases();
  // 2. 表单 state：选中的 KB id 列表 + 问题文本
  const [selectedKbIds, setSelectedKbIds] = useState<string[]>([]);
  const [query, setQuery] = useState("");
  // 3. 流式累积状态
  const [streamState, setStreamState] = useState<StreamState>({
    status: "idle",
    output: "",
    events: [],
  });
  // 4. 抽出 trace 字段供 trace 面板消费（仅 event + payload 减少数据传输）
  const trace = streamState.events.map((event) => ({
    event: event.event,
    payload: event.payload,
  }));
  // 5. 仅已发布 KB 可检索
  const publishedKnowledgeBases = knowledgeBases.filter(isPublishedKnowledgeBase);
  // 6. Multiselect 选项（未发布的 KB 在下拉里 disabled）
  const options = knowledgeBases.map((item) => {
    const published = isPublishedKnowledgeBase(item);
    return {
      label: item.name,
      value: item.id,
      disabled: !published,
      disabledReason: published ? undefined : `${item.name}未发布`,
    };
  });

  /**
   * 首次进入时自动选中第一个已发布 KB。
   *
   * @author lvdaxianerplus
   */
  useEffect(() => {
    if (selectedKbIds.length === 0 && publishedKnowledgeBases.length > 0) {
      setSelectedKbIds([publishedKnowledgeBases[0].id]);
    }
  }, [publishedKnowledgeBases, selectedKbIds.length]);

  /**
   * 启动一次流式检索：每条事件通过 appendStreamEvent 累积到 state。
   *
   * @author lvdaxianerplus
   */
  async function startStream(): Promise<void> {
    setStreamState({ status: "streaming", output: "", events: [] });
    try {
      // 调 SSE hook；onEvent 把每条事件塞进 appendStreamEvent
      await readRetrievalStream(
        {
          input: query,
          knowledge_base_ids: selectedKbIds,
          top_k: 5,
        },
        (event) => setStreamState((state) => appendStreamEvent(state, event)),
      );
    } catch (error) {
      // 错误时把状态机切到 error，并把错误消息写入 state
      const message = error instanceof Error ? error.message : "检索失败";
      setStreamState({
        status: "error",
        output: "",
        events: [],
        error: message,
      });
    }
  }

  return (
    <div className="space-y-4">
      {/* 顶部页眉 */}
      <PageHeader
        eyebrow="Retrieval Debugger"
        title="检索控制台"
        description="验证 query scope、summary-first、rerank 候选治理和流式输出。"
      />
      {/* 顶部指标条（route plan / scope / stream 占位） */}
      <MetricStrip
        items={[
          { label: "route plan", value: "summary-first" },
          { label: "scope", value: "query scope" },
          { label: "stream", value: "SSE events" },
        ]}
      />
      {/* 主体两列 + 底部跨列 trace */}
      <div className="grid gap-4 lg:grid-cols-2">
        {/* 左：检索参数 */}
        <SectionCard title="检索参数">
          <Multiselect
            label="知识库范围"
            options={options}
            value={selectedKbIds}
            onChange={setSelectedKbIds}
          />
          {isLoading ? <LoadingState label="加载知识库中" /> : null}
          {isError ? <ErrorState title="知识库加载失败" onRetry={refetch} /> : null}
          {/* 问题输入 */}
          <div className="mt-3 grid gap-1.5">
            <label className="text-sm font-medium text-slate-900" htmlFor="query">
              问题
            </label>
            <Textarea
              aria-label="问题"
              id="query"
              rows={5}
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
          </div>
          <Button
            className="mt-3"
            disabled={!query || selectedKbIds.length === 0}
            type="button"
            onClick={startStream}
          >
            开始流式检索
          </Button>
        </SectionCard>
        {/* 右：流式输出 + 错误展示 */}
        <SectionCard>
          <StreamingResultPanel
            durationMs={streamState.durationMs}
            output={streamState.output}
            status={streamState.status}
          />
          {streamState.status === "error" ? (
            <ErrorState title={streamState.error ?? "检索失败"} onRetry={startStream} />
          ) : null}
        </SectionCard>
        {/* 底部：跨列 trace 面板 */}
        <div className="lg:col-span-2">
          <SectionCard>
            <RetrievalTracePanel trace={trace} />
          </SectionCard>
        </div>
      </div>
    </div>
  );
}
