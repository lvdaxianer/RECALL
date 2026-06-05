import { useEffect, useState } from "react";

import type { KnowledgeBase } from "../../api/types";
import { Multiselect } from "../../components/common/Multiselect";
import { ErrorState } from "../../components/common/ErrorState";
import { LoadingState } from "../../components/common/LoadingState";
import { SectionCard } from "../../components/common/SectionCard";
import { useKnowledgeBases } from "../../hooks/useKnowledgeBases";
import { appendStreamEvent, readRetrievalStream, type StreamState } from "../../hooks/useRetrievalStream";
import { RetrievalTracePanel } from "./RetrievalTracePanel";
import { StreamingResultPanel } from "./StreamingResultPanel";

export function RetrievalConsolePage() {
  const { items: knowledgeBases, isLoading, isError, refetch } = useKnowledgeBases();
  const [selectedKbIds, setSelectedKbIds] = useState<string[]>([]);
  const [query, setQuery] = useState("");
  const [streamState, setStreamState] = useState<StreamState>({
    status: "idle",
    output: "",
    events: [],
  });
  const trace = streamState.events.map((event) => ({ event: event.event, payload: event.payload }));
  const publishedKnowledgeBases = knowledgeBases.filter(isPublishedKnowledgeBase);
  const options = knowledgeBases.map((item) => ({
    label: item.name,
    value: item.id,
    disabled: !isPublishedKnowledgeBase(item),
    disabledReason: isPublishedKnowledgeBase(item) ? undefined : `${item.name}未发布`,
  }));

  useEffect(() => {
    if (selectedKbIds.length === 0 && publishedKnowledgeBases.length > 0) {
      setSelectedKbIds([publishedKnowledgeBases[0].id]);
    }
  }, [publishedKnowledgeBases, selectedKbIds.length]);

  async function startStream() {
    setStreamState({ status: "streaming", output: "", events: [] });
    try {
      await readRetrievalStream(
        {
          input: query,
          knowledge_base_ids: selectedKbIds,
          top_k: 5,
        },
        (event) => setStreamState((state) => appendStreamEvent(state, event)),
      );
    } catch (error) {
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
    <div className="page-grid">
      <section className="page-hero">
        <div>
          <span>Retrieval Debugger</span>
          <h2>检索控制台</h2>
          <p>验证 query scope、summary-first、rerank 候选治理和流式输出。</p>
        </div>
        <div className="summary-strip">
          <div>
            <span>route plan</span>
            <strong>summary-first</strong>
          </div>
          <div>
            <span>scope</span>
            <strong>query scope</strong>
          </div>
          <div>
            <span>stream</span>
            <strong>SSE events</strong>
          </div>
        </div>
      </section>
      <div className="page-grid page-grid--two">
      <SectionCard title="检索参数">
        <Multiselect
          label="知识库范围"
          options={options}
          value={selectedKbIds}
          onChange={setSelectedKbIds}
        />
        {isLoading ? <LoadingState label="加载知识库中" /> : null}
        {isError ? <ErrorState title="知识库加载失败" onRetry={refetch} /> : null}
        <label className="form-field">
          <span>问题</span>
          <textarea aria-label="问题" value={query} rows={5} onChange={(event) => setQuery(event.target.value)} />
        </label>
        <button className="button" type="button" onClick={startStream} disabled={!query || selectedKbIds.length === 0}>
          开始流式检索
        </button>
      </SectionCard>
      <SectionCard>
        <StreamingResultPanel output={streamState.output} status={streamState.status} durationMs={streamState.durationMs} />
        {streamState.status === "error" ? (
          <ErrorState title={streamState.error ?? "检索失败"} onRetry={startStream} />
        ) : null}
      </SectionCard>
      <SectionCard>
        <RetrievalTracePanel trace={trace} />
      </SectionCard>
      </div>
    </div>
  );
}

function isPublishedKnowledgeBase(item: KnowledgeBase): boolean {
  return item.status === "published";
}
