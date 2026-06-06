/**
 * Recall · 文档录入页
 *
 * 流程：选 KB → 写 Markdown → 提交；解析进度请到知识库详情页查看（本页不重复展示）。
 * 仅"可写入"状态的 KB（排除 deleted / archived / publishing）才允许提交。
 *
 * @author lvdaxianerplus
 */
import { useEffect, useState } from "react";

import { uploadDocument } from "../../api/documents";
import { EmptyState } from "../../components/common/EmptyState";
import { ErrorState } from "../../components/common/ErrorState";
import { LoadingState } from "../../components/common/LoadingState";
import { SectionCard } from "../../components/common/SectionCard";
import { StatusBadge } from "../../components/recall/StatusBadge";
import { MetricStrip } from "../../components/recall/MetricStrip";
import { PageHeader } from "../../components/recall/PageHeader";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { Textarea } from "../../components/ui/textarea";
import { useKnowledgeBases } from "../../hooks/useKnowledgeBases";
import { type StatusBadgeVariant } from "../../components/recall/StatusBadge";
import { KB_STATUS } from "../chat/runtime/chatConstants";

/**
 * 提交状态机：`idle → loading → success | error`。
 *
 * @author lvdaxianerplus
 */
type SubmitStatus = "idle" | "loading" | "success" | "error";

/**
 * 不可写入 KB 状态集合（与后端 KB 状态枚举严格一致）。
 *
 * @author lvdaxianerplus
 */
const NON_WRITABLE_STATUSES: ReadonlySet<string> = new Set([
  KB_STATUS.DELETED,
  KB_STATUS.ARCHIVED,
  KB_STATUS.PUBLISHING,
]);

/**
 * 判断 KB 状态是否可写入文档。
 *
 * @param status KB 状态字符串
 * @returns 是否可写入
 * @author lvdaxianerplus
 */
function canIngest(status: string): boolean {
  return !NON_WRITABLE_STATUSES.has(status);
}

/**
 * KB 状态 → StatusBadgeVariant 映射（策略模式替代 if-else 链）。
 *
 * @author lvdaxianerplus
 */
const KB_STATUS_TO_VARIANT: Record<string, StatusBadgeVariant> = {
  [KB_STATUS.PUBLISHED]: "ready",
  [KB_STATUS.ACTIVE]: "ready",
  [KB_STATUS.PUBLISH_FAILED]: "error",
  [KB_STATUS.DELETED]: "error",
  [KB_STATUS.PUBLISHING]: "warning",
  [KB_STATUS.DRAFT]: "warning",
  [KB_STATUS.ARCHIVED]: "paused",
};

/**
 * 文档录入页组件。
 *
 * @author lvdaxianerplus
 */
export function DocumentIngestPage() {
  // 1. 拉取 KB 列表
  const { items, isLoading, isError, status: loadStatus, refetch } = useKnowledgeBases();
  // 2. 表单 state
  const [selectedKbId, setSelectedKbId] = useState("");
  const [name, setName] = useState("");
  const [content, setContent] = useState("");
  const [submitStatus, setSubmitStatus] = useState<SubmitStatus>("idle");

  /**
   * 进入页面时若用户未选 KB，自动选中第一个可写入的 KB。
   *
   * @author lvdaxianerplus
   */
  useEffect(() => {
    if (selectedKbId || items.length === 0) {
      return;
    }
    const firstWritable = items.find((item) => canIngest(item.status));
    if (firstWritable) {
      setSelectedKbId(firstWritable.id);
    }
  }, [items, selectedKbId]);

  // 当前选中的 KB 视图模型
  const selectedKb = items.find((item) => item.id === selectedKbId);
  // 提交按钮的可点击性
  const canSubmit = Boolean(
    selectedKb && canIngest(selectedKb.status) && name && content && submitStatus !== "loading",
  );

  /**
   * 提交文档到选中的 KB。
   *
   * @author lvdaxianerplus
   */
  async function handleUpload(): Promise<void> {
    if (!selectedKbId) {
      return;
    }
    setSubmitStatus("loading");
    try {
      // 走非流式 upload（后端一次性返回 KnowledgeDocument）
      await uploadDocument(selectedKbId, {
        name,
        content,
        content_type: "text/markdown",
        owner_id: "default",
      });
      // 重置表单 + 刷新 KB 列表（KB 状态可能变为"有未发布变更"）
      setName("");
      setContent("");
      setSubmitStatus("success");
      await refetch();
    } catch {
      // 静默：UI 走 ErrorState
      setSubmitStatus("error");
    }
  }

  return (
    <div className="space-y-4">
      {/* 顶部页眉 */}
      <PageHeader
        eyebrow="Document Intake"
        title="文档录入"
        description="把纯文本或 Markdown 录入知识库，形成可追踪的检索证据。"
      />
      {/* 顶部指标条 */}
      <MetricStrip
        items={[
          { label: "content type", value: "Markdown only" },
          { label: "index", value: "ES / Milvus" },
          { label: "publish", value: "draft to release" },
        ]}
      />
      {/* 左右两栏：左录入表单 / 右规则说明 */}
      <div className="grid gap-4 lg:grid-cols-2">
        <SectionCard title="录入表单">
          {/* KB 下拉（不可写入的 KB 在下拉里 disabled） */}
          <div className="grid gap-1.5">
            <label className="text-sm font-medium text-slate-900" htmlFor="ingest-kb">
              选择知识库
            </label>
            <select
              aria-label="选择知识库"
              className="h-9 rounded-md border border-slate-200 bg-white px-3 text-sm transition-colors focus-visible:border-emerald-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500"
              id="ingest-kb"
              value={selectedKbId}
              onChange={(event) => setSelectedKbId(event.target.value)}
            >
              <option value="">请选择知识库</option>
              {items.map((item) => (
                <option disabled={!canIngest(item.status)} key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </select>
          </div>
          {/* 当前选中 KB 的状态徽章 */}
          {selectedKb ? (
            <div className="mt-3 flex items-center justify-between gap-3 rounded-lg border border-slate-200 bg-slate-50 p-3">
              <span className="text-sm text-slate-700">{selectedKb.name}</span>
              <StatusBadge variant={KB_STATUS_TO_VARIANT[selectedKb.status] ?? "neutral"}>
                {selectedKb.status}
              </StatusBadge>
            </div>
          ) : null}
          {/* 顶部错误 / 加载态 */}
          {isLoading ? <LoadingState label="加载知识库中" /> : null}
          {isError ? <ErrorState title="知识库加载失败" onRetry={refetch} /> : null}
          {loadStatus === "empty" ? <EmptyState title="暂无知识库" description="先创建知识库后再录入文档。" /> : null}
          {/* 文档名 + Markdown 内容 */}
          <div className="mt-3 grid gap-1.5">
            <label className="text-sm font-medium text-slate-900" htmlFor="ingest-name">
              文档名称
            </label>
            <Input
              id="ingest-name"
              placeholder="README.md"
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
          </div>
          <div className="mt-3 grid gap-1.5">
            <label className="text-sm font-medium text-slate-900" htmlFor="ingest-content">
              Markdown 内容
            </label>
            <Textarea
              id="ingest-content"
              placeholder="# 标题&#10;正文"
              rows={10}
              value={content}
              onChange={(event) => setContent(event.target.value)}
            />
          </div>
          <Button className="mt-3" disabled={!canSubmit} type="button" onClick={handleUpload}>
            {submitStatus === "loading" ? "录入中" : "提交录入"}
          </Button>
          {/* 提交态：loading / error / success */}
          {submitStatus === "loading" ? <LoadingState label="正在写入检索索引" /> : null}
          {submitStatus === "error" ? <ErrorState title="录入失败" onRetry={handleUpload} /> : null}
          {submitStatus === "success" ? (
            <EmptyState
              title="录入完成"
              description="到 知识库 → 文档列表 可查看解析进度；发布后才会进入聊天检索。"
            />
          ) : null}
        </SectionCard>
        {/* 右侧规则说明 */}
        <SectionCard title="录入规则">
          <ul className="space-y-2 text-sm text-slate-600">
            <li>仅支持纯文本和 Markdown 内容。</li>
            <li>录入后知识库会进入有未发布变更状态。</li>
            <li>聊天问答只会检索已发布知识库。</li>
            <li>
              文档解析进度请到 <strong className="font-medium text-slate-900">知识库 → 文档列表</strong> 查看。
            </li>
          </ul>
        </SectionCard>
      </div>
    </div>
  );
}
