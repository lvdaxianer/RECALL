/**
 * Recall · 效果评测页
 *
 * 流程：选已发布 KB → 输问题 → 跑一次基线检索 → 看命中证据 + trace。
 * 与检索控制台的区别：本页只暴露检索质量结果，不参与实时调试。
 *
 * 设计要点：
 * 1. 仅展示已发布 KB（评测目的是检索质量，未发布不可比）
 * 2. topK 固定 5（v1.4 起尚未暴露为可调）
 * 3. 走非流式 searchRetrieval（不暴露 SSE 增量）
 * 4. 错误用 ErrorState 提示，不把 stack 抛到 UI
 * 5. EvaluationResult 子组件渲染 3 个指标卡 + 命中列表 + trace 列表
 * 6. 命中列表用 chunk_id 作 key；空命中走 EmptyState
 *
 * @author lvdaxianerplus
 */
import { useState } from "react";

import { searchRetrieval, type RetrievalResponse } from "../../api/retrieval";
import { EmptyState } from "../../components/common/EmptyState";
import { ErrorState } from "../../components/common/ErrorState";
import { LoadingState } from "../../components/common/LoadingState";
import { SectionCard } from "../../components/common/SectionCard";
import { MetricStrip } from "../../components/recall/MetricStrip";
import { PageHeader } from "../../components/recall/PageHeader";
import { Button } from "../../components/ui/button";
import { Textarea } from "../../components/ui/textarea";
import { useKnowledgeBases } from "../../hooks/useKnowledgeBases";

/**
 * 评测状态机：`idle → loading → success | error`。
 *
 * @author lvdaxianerplus
 */
type EvaluationStatus = "idle" | "loading" | "error" | "success";

/**
 * 效果评测页组件。
 *
 * 流程：
 * 1. 拉取 KB 列表（仅已发布）
 * 2. 用户选 KB + 输问题
 * 3. 走非流式 searchRetrieval（topK=5）
 * 4. 展示命中结果 + 指标 + trace
 *
 * 状态机：idle → loading → success | error。
 * 错误走 ErrorState 提示，不抛 stack。
 *
 * @author lvdaxianerplus
 */
export function EvaluationPage() {
  // 1. 拉取 KB 列表（用于下拉）
  const { items, isLoading, isError, refetch } = useKnowledgeBases();
  // 2. 表单 state
  const [question, setQuestion] = useState("");
  const [selectedKbId, setSelectedKbId] = useState("");
  // 3. 评测结果 + 状态
  const [result, setResult] = useState<RetrievalResponse | undefined>();
  const [evaluationStatus, setEvaluationStatus] = useState<EvaluationStatus>("idle");
  // 4. 仅展示已发布 KB（评测的目的是检索质量，draft / archived 不可比）
  const publishedKnowledgeBases = items.filter((item) => item.status === "published");
  // 5. 表单可提交判定
  const canEvaluate = Boolean(question.trim() && selectedKbId && evaluationStatus !== "loading");

  /**
   * 触发一次基线检索评测。
   *
   * @author lvdaxianerplus
   */
  async function handleEvaluate(): Promise<void> {
    if (!canEvaluate) {
      return;
    }
    setEvaluationStatus("loading");
    try {
      // 走非流式 searchRetrieval（评测场景不需要 SSE 增量）
      const response = await searchRetrieval({
        input: question.trim(),
        knowledge_base_ids: [selectedKbId],
        top_k: 5,
      });
      setResult(response);
      setEvaluationStatus("success");
    } catch {
      // 静默：UI 走 ErrorState 提示
      setEvaluationStatus("error");
    }
  }

  return (
    <div className="space-y-4">
      {/* 顶部页眉 */}
      <PageHeader
        eyebrow="Retrieval Evaluation"
        title="效果评测"
        description="用真实问题验证检索质量、命中证据和评分链路。"
      />
      {/* 三个指标条（trace / routing / evidence 风格占位） */}
      <MetricStrip
        items={[
          { label: "trace", value: "score trace" },
          { label: "routing", value: "route plan" },
          { label: "evidence", value: "top-k hits" },
        ]}
      />
      {/* 左右两栏：左输入 / 右结果 */}
      <div className="grid gap-4 lg:grid-cols-2">
        <SectionCard title="评测输入">
          {/* 问题输入 */}
          <div className="grid gap-1.5">
            <label className="text-sm font-medium text-slate-900" htmlFor="eval-question">
              评测问题
            </label>
            <Textarea
              aria-label="评测问题"
              id="eval-question"
              placeholder="输入用于验证检索质量的问题"
              rows={5}
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
            />
          </div>
          {/* KB 下拉（仅已发布） */}
          <div className="mt-3 grid gap-1.5">
            <label className="text-sm font-medium text-slate-900" htmlFor="eval-kb">
              评测知识库
            </label>
            <select
              aria-label="评测知识库"
              className="h-9 rounded-md border border-slate-200 bg-white px-3 text-sm focus-visible:border-emerald-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500"
              id="eval-kb"
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
          </div>
          <Button className="mt-3" disabled={!canEvaluate} type="button" onClick={handleEvaluate}>
            {evaluationStatus === "loading" ? "评测中" : "开始评测"}
          </Button>
          {/* 错误 / 加载态展示 */}
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

/**
 * 评测结果展示：3 个指标卡 + 命中列表 + trace 列表。
 *
 * @author lvdaxianerplus
 */
interface EvaluationResultProps {
  result: RetrievalResponse;
}
function EvaluationResult({ result }: EvaluationResultProps) {
  // 取首条命中分数用于"Top Score"指标
  const topScore = result.results[0]?.score;
  return (
    <div className="space-y-3">
      {/* 3 列指标卡 */}
      <div className="grid gap-3 sm:grid-cols-3">
        <MetricCard label="Query Scope" value={result.query_scope} />
        <MetricCard label="命中数量" value={`${result.results.length} 条命中`} />
        <MetricCard
          label="Top Score"
          value={topScore === undefined ? "暂无" : String(topScore)}
        />
      </div>
      {/* 命中结果列表：空态走 EmptyState */}
      {result.results.length === 0 ? (
        <EmptyState title="没有命中结果" description="可以调整问题或重新发布知识库后再评测。" />
      ) : (
        <div className="space-y-2">
          {result.results.map((item) => (
            <article
              className="flex flex-col gap-1.5 rounded-lg border border-slate-200 bg-white p-3"
              key={item.chunk_id}
            >
              <div className="flex items-baseline justify-between gap-2">
                {/* 标题兜底文档名 */}
                <strong className="truncate text-sm font-semibold text-slate-900">
                  {item.title || item.document_name}
                </strong>
                <span className="text-xs text-slate-500">{item.document_name}</span>
              </div>
              <p className="text-sm leading-6 text-slate-700">{item.content}</p>
              {/* score_trace 以等宽字体展示，便于对照调试 */}
              <small className="font-mono text-xs text-slate-500">
                {JSON.stringify(item.score_trace)}
              </small>
            </article>
          ))}
        </div>
      )}
      {/* trace 列表（仅在服务端返回 trace 时展示） */}
      {result.trace.length > 0 ? (
        <div className="space-y-2">
          {result.trace.map((item, index) => (
            <div
              className="rounded-md border border-slate-200 bg-slate-50 p-3"
              key={`${String(item.stage ?? "trace")}-${index}`}
            >
              <strong className="block text-sm font-medium text-slate-900">
                {String(item.stage ?? "trace")}
              </strong>
              <span className="text-sm text-slate-600">
                {String(item.summary ?? "已记录检索阶段")}
              </span>
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}

/**
 * 指标卡（评测页定制版，比通用 MetricStrip 更轻量）。
 *
 * @author lvdaxianerplus
 */
interface MetricCardProps {
  label: string;
  value: string;
}
function MetricCard({ label, value }: MetricCardProps) {
  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
      <span className="block text-xs text-slate-500">{label}</span>
      <strong className="mt-1 block font-mono text-base font-semibold tabular-nums text-emerald-700">
        {value}
      </strong>
    </div>
  );
}
