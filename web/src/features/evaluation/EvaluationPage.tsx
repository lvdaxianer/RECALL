import { useState } from "react";

import { searchRetrieval, type RetrievalResponse } from "../../api/retrieval";
import { EmptyState } from "../../components/common/EmptyState";
import { ErrorState } from "../../components/common/ErrorState";
import { LoadingState } from "../../components/common/LoadingState";
import { SectionCard } from "../../components/common/SectionCard";
import { useKnowledgeBases } from "../../hooks/useKnowledgeBases";

export function EvaluationPage() {
  const { items, isLoading, isError, refetch } = useKnowledgeBases();
  const [question, setQuestion] = useState("");
  const [selectedKbId, setSelectedKbId] = useState("");
  const [result, setResult] = useState<RetrievalResponse | undefined>();
  const [evaluationStatus, setEvaluationStatus] = useState<"idle" | "loading" | "error" | "success">("idle");
  const publishedKnowledgeBases = items.filter((item) => item.status === "published");
  const canEvaluate = Boolean(question.trim() && selectedKbId && evaluationStatus !== "loading");

  async function handleEvaluate() {
    if (!canEvaluate) {
      return;
    }
    setEvaluationStatus("loading");
    try {
      const response = await searchRetrieval({
        input: question.trim(),
        knowledge_base_ids: [selectedKbId],
        top_k: 5,
      });
      setResult(response);
      setEvaluationStatus("success");
    } catch {
      setEvaluationStatus("error");
    }
  }

  return (
    <div className="page-grid">
      <section className="page-hero">
        <div>
          <span>Retrieval Evaluation</span>
          <h2>效果评测</h2>
          <p>用真实问题验证检索质量、命中证据和评分链路。</p>
        </div>
        <div className="summary-strip">
          <div>
            <span>trace</span>
            <strong>score trace</strong>
          </div>
          <div>
            <span>routing</span>
            <strong>route plan</strong>
          </div>
          <div>
            <span>evidence</span>
            <strong>top-k hits</strong>
          </div>
        </div>
      </section>
      <div className="page-grid page-grid--two">
      <SectionCard title="评测输入">
        <label className="form-field">
          <span>评测问题</span>
          <textarea
            aria-label="评测问题"
            rows={5}
            placeholder="输入用于验证检索质量的问题"
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
          />
        </label>
        <label className="form-field">
          <span>评测知识库</span>
          <select
            aria-label="评测知识库"
            value={selectedKbId}
            onChange={(event) => setSelectedKbId(event.target.value)}
          >
            <option value="">请选择已发布知识库</option>
            {publishedKnowledgeBases.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </select>
        </label>
        <button className="button" type="button" disabled={!canEvaluate} onClick={handleEvaluate}>
          {evaluationStatus === "loading" ? "评测中" : "开始评测"}
        </button>
        {isLoading ? <LoadingState label="加载知识库中" /> : null}
        {isError ? <ErrorState title="知识库加载失败" onRetry={refetch} /> : null}
        {evaluationStatus === "error" ? <ErrorState title="评测失败" onRetry={handleEvaluate} /> : null}
      </SectionCard>
      <SectionCard title="评测结果">
        {evaluationStatus === "loading" ? <LoadingState label="正在执行基线检索" /> : null}
        {evaluationStatus !== "loading" && !result ? (
          <EmptyState title="暂无评测结果" description="选择已发布知识库并输入问题后开始评测。" />
        ) : null}
        {evaluationStatus === "success" && result ? <EvaluationResult result={result} /> : null}
      </SectionCard>
      </div>
    </div>
  );
}

function EvaluationResult({ result }: { result: RetrievalResponse }) {
  const topScore = result.results[0]?.score;
  return (
    <div className="evaluation-result">
      <div className="metric-grid">
        <MetricCard label="Query Scope" value={result.query_scope} />
        <MetricCard label="命中数量" value={`${result.results.length} 条命中`} />
        <MetricCard label="Top Score" value={topScore === undefined ? "暂无" : String(topScore)} />
      </div>
      {result.results.length === 0 ? (
        <EmptyState title="没有命中结果" description="可以调整问题或重新发布知识库后再评测。" />
      ) : (
        <div className="result-stack">
          {result.results.map((item) => (
            <article className="result-item" key={item.chunk_id}>
              <div>
                <strong>{item.title || item.document_name}</strong>
                <span>{item.document_name}</span>
              </div>
              <p>{item.content}</p>
              <small>{JSON.stringify(item.score_trace)}</small>
            </article>
          ))}
        </div>
      )}
      <div className="trace-card-list">
        {result.trace.map((item, index) => (
          <div className="trace-card" key={`${String(item.stage ?? "trace")}-${index}`}>
            <strong>{String(item.stage ?? "trace")}</strong>
            <span>{String(item.summary ?? "已记录检索阶段")}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function MetricCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="metric-card">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}
