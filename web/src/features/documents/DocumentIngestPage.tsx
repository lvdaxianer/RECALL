import { useCallback, useEffect, useState } from "react";

import { listDocuments, uploadDocument } from "../../api/documents";
import type { DocumentParseStatus, KnowledgeDocument } from "../../api/documents";
import { EmptyState } from "../../components/common/EmptyState";
import { ErrorState } from "../../components/common/ErrorState";
import { LoadingState } from "../../components/common/LoadingState";
import { SectionCard } from "../../components/common/SectionCard";
import { StatusBadge } from "../../components/common/StatusBadge";
import { useKnowledgeBases } from "../../hooks/useKnowledgeBases";

function canIngest(status: string): boolean {
  return !["deleted", "archived", "publishing"].includes(status);
}

const PARSE_STATUS_LABELS: Record<DocumentParseStatus, string> = {
  queued: "排队中",
  processing: "解析中",
  parsed: "已分块",
  indexed: "已入库",
  failed: "失败",
};

function getParseStatus(document: KnowledgeDocument): DocumentParseStatus {
  const status = document.parse_status;
  if (status && status in PARSE_STATUS_LABELS) {
    return status;
  }
  return "indexed";
}

export function DocumentIngestPage() {
  const { items, isLoading, isError, status: loadStatus, refetch } = useKnowledgeBases();
  const [selectedKbId, setSelectedKbId] = useState("");
  const [name, setName] = useState("");
  const [content, setContent] = useState("");
  const [submitStatus, setSubmitStatus] = useState<"idle" | "loading" | "success" | "error">("idle");
  const [documents, setDocuments] = useState<KnowledgeDocument[]>([]);
  const [documentsStatus, setDocumentsStatus] = useState<"idle" | "loading" | "success" | "error">("idle");

  useEffect(() => {
    if (selectedKbId || items.length === 0) {
      return;
    }
    const firstWritable = items.find((item) => canIngest(item.status));
    if (firstWritable) {
      setSelectedKbId(firstWritable.id);
    }
  }, [items, selectedKbId]);

  const loadDocuments = useCallback(async (kbId: string) => {
    if (!kbId) {
      setDocuments([]);
      setDocumentsStatus("idle");
      return;
    }
    setDocumentsStatus("loading");
    try {
      const nextDocuments = await listDocuments(kbId);
      setDocuments(nextDocuments);
      setDocumentsStatus("success");
    } catch {
      setDocuments([]);
      setDocumentsStatus("error");
    }
  }, []);

  useEffect(() => {
    void loadDocuments(selectedKbId);
  }, [loadDocuments, selectedKbId]);

  const selectedKb = items.find((item) => item.id === selectedKbId);
  const canSubmit = Boolean(selectedKb && canIngest(selectedKb.status) && name && content && submitStatus !== "loading");

  async function handleUpload() {
    if (!selectedKbId) {
      return;
    }
    setSubmitStatus("loading");
    try {
      await uploadDocument(selectedKbId, {
        name,
        content,
        content_type: "text/markdown",
        owner_id: "default",
      });
      setName("");
      setContent("");
      setSubmitStatus("success");
      await loadDocuments(selectedKbId);
      await refetch();
    } catch {
      setSubmitStatus("error");
    }
  }

  return (
    <div className="page-grid">
      <section className="page-hero">
        <div>
          <span>Document Intake</span>
          <h2>文档录入</h2>
          <p>把纯文本或 Markdown 录入知识库，形成可追踪的检索证据。</p>
        </div>
        <div className="summary-strip">
          <div>
            <span>content type</span>
            <strong>Markdown only</strong>
          </div>
          <div>
            <span>index</span>
            <strong>ES / Milvus</strong>
          </div>
          <div>
            <span>publish</span>
            <strong>draft to release</strong>
          </div>
        </div>
      </section>
      <div className="page-grid page-grid--two">
      <SectionCard title="录入表单">
        <label className="form-field">
          <span>选择知识库</span>
          <select
            aria-label="选择知识库"
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
        </label>
        {selectedKb ? (
          <div className="selected-kb-row">
            <span>{selectedKb.name}</span>
            <StatusBadge status={selectedKb.status} />
          </div>
        ) : null}
        {isLoading ? <LoadingState label="加载知识库中" /> : null}
        {isError ? <ErrorState title="知识库加载失败" onRetry={refetch} /> : null}
        {loadStatus === "empty" ? <EmptyState title="暂无知识库" description="先创建知识库后再录入文档。" /> : null}
        <label className="form-field">
          <span>文档名称</span>
          <input placeholder="README.md" value={name} onChange={(event) => setName(event.target.value)} />
        </label>
        <label className="form-field">
          <span>Markdown 内容</span>
          <textarea
            placeholder="# 标题&#10;正文"
            rows={10}
            value={content}
            onChange={(event) => setContent(event.target.value)}
          />
        </label>
        <button className="button" type="button" onClick={handleUpload} disabled={!canSubmit}>
          {submitStatus === "loading" ? "录入中" : "提交录入"}
        </button>
        {submitStatus === "loading" ? <LoadingState label="正在写入检索索引" /> : null}
        {submitStatus === "error" ? <ErrorState title="录入失败" onRetry={handleUpload} /> : null}
        {submitStatus === "success" ? (
          <EmptyState title="录入完成" description="知识库已有未发布变更，发布后才会进入聊天检索。" />
        ) : null}
      </SectionCard>
      <SectionCard title="录入规则">
        <div className="rule-list">
          <p>仅支持纯文本和 Markdown 内容。</p>
          <p>录入后知识库会进入有未发布变更状态。</p>
          <p>聊天问答只会检索已发布知识库。</p>
        </div>
      </SectionCard>
      <SectionCard title="文档解析状态">
        {documentsStatus === "loading" ? <LoadingState label="加载文档状态中" /> : null}
        {documentsStatus === "error" ? (
          <ErrorState title="文档状态加载失败" onRetry={() => loadDocuments(selectedKbId)} />
        ) : null}
        {documentsStatus === "success" && documents.length === 0 ? (
          <EmptyState title="暂无文档" description="提交录入后可在这里查看解析和入库进度。" />
        ) : null}
        {documents.length > 0 ? (
          <div className="document-status-list">
            {documents.map((document) => {
              const parseStatus = getParseStatus(document);
              return (
                <article className="document-status-card" key={document.id}>
                  <div>
                    <strong>{document.document_name}</strong>
                    <small>{document.chunk_count} chunks</small>
                  </div>
                  <div className="document-status-card__meta">
                    <span className={`parse-status parse-status--${parseStatus}`}>
                      {PARSE_STATUS_LABELS[parseStatus]}
                    </span>
                    <span>{document.parse_attempts ?? 0}/3 次</span>
                  </div>
                  {document.parse_error ? <p>{document.parse_error}</p> : null}
                </article>
              );
            })}
          </div>
        ) : null}
      </SectionCard>
      </div>
    </div>
  );
}
