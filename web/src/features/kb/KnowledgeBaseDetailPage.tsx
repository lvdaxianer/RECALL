import { useEffect, useState } from "react";

import { listDocumentChunks, listDocuments, uploadDocument, type DocumentParseStatus, type KnowledgeChunk, type KnowledgeDocument } from "../../api/documents";
import { EmptyState } from "../../components/common/EmptyState";
import { ErrorState } from "../../components/common/ErrorState";
import { LoadingState } from "../../components/common/LoadingState";
import { SectionCard } from "../../components/common/SectionCard";

interface KnowledgeBaseDetailPageProps {
  kbId: string;
  kbName?: string;
  onBack?: () => void;
  onUploaded?: () => void | Promise<void>;
}

type LoadStatus = "idle" | "loading" | "success" | "empty" | "error" | "retrying";

const DOCUMENT_PAGE_SIZE = 10;
const CHUNK_PAGE_SIZE = 5;
const PARSE_STATUS_LABELS: Record<DocumentParseStatus, string> = {
  queued: "排队中",
  processing: "解析中",
  parsed: "已分块",
  indexed: "已入库",
  failed: "失败",
};

export function KnowledgeBaseDetailPage({ kbId, kbName, onBack, onUploaded }: KnowledgeBaseDetailPageProps) {
  const [name, setName] = useState("");
  const [content, setContent] = useState("");
  const [status, setStatus] = useState<"idle" | "loading" | "success" | "error">("idle");
  const [documents, setDocuments] = useState<KnowledgeDocument[]>([]);
  const [documentsStatus, setDocumentsStatus] = useState<LoadStatus>("idle");
  const [documentQuery, setDocumentQuery] = useState("");
  const [documentPage, setDocumentPage] = useState(1);
  const [selectedDocumentId, setSelectedDocumentId] = useState("");
  const [chunks, setChunks] = useState<KnowledgeChunk[]>([]);
  const [chunksStatus, setChunksStatus] = useState<LoadStatus>("idle");
  const [showChunkConfig, setShowChunkConfig] = useState(false);
  const [isChunkDrawerOpen, setIsChunkDrawerOpen] = useState(false);
  const [chunkPage, setChunkPage] = useState(1);

  useEffect(() => {
    setSelectedDocumentId("");
    setShowChunkConfig(false);
    setChunks([]);
    setIsChunkDrawerOpen(false);
    setChunkPage(1);
    setDocumentPage(1);
    setDocumentQuery("");
    void loadDocuments("loading");
  }, [kbId]);

  useEffect(() => {
    if (!selectedDocumentId) {
      setChunks([]);
      setChunksStatus("idle");
      return;
    }
    setChunkPage(1);
    void loadChunks(selectedDocumentId, "loading");
  }, [kbId, selectedDocumentId]);

  useEffect(() => {
    const visibleDocuments = getVisibleDocuments(documents, documentQuery, documentPage);
    const hasSelectedDocument = visibleDocuments.some((document) => document.id === selectedDocumentId);
    if (!hasSelectedDocument) {
      setSelectedDocumentId(visibleDocuments[0]?.id ?? "");
      setShowChunkConfig(false);
      setIsChunkDrawerOpen(false);
    }
  }, [documentPage, documentQuery, documents, selectedDocumentId]);

  async function loadDocuments(nextStatus: LoadStatus = "loading") {
    setDocumentsStatus(nextStatus);
    try {
      const data = await listDocuments(kbId);
      const nextDocuments = Array.isArray(data) ? data : [];
      setDocuments(nextDocuments);
      setDocumentPage(1);
      setDocumentsStatus(nextDocuments.length > 0 ? "success" : "empty");
      if (nextDocuments.length > 0) {
        setSelectedDocumentId((current) => current || nextDocuments[0].id);
      }
    } catch {
      setDocumentsStatus("error");
    }
  }

  async function loadChunks(documentId: string, nextStatus: LoadStatus = "loading") {
    setChunksStatus(nextStatus);
    try {
      const data = await listDocumentChunks(kbId, documentId);
      const nextChunks = Array.isArray(data) ? data : [];
      setChunks(nextChunks);
      setChunksStatus(nextChunks.length > 0 ? "success" : "empty");
    } catch {
      setChunksStatus("error");
    }
  }

  async function handleUpload() {
    setStatus("loading");
    try {
      await uploadDocument(kbId, {
        name,
        content,
        content_type: "text/markdown",
        owner_id: "default",
      });
      setStatus("success");
      setName("");
      setContent("");
      await loadDocuments("retrying");
      await onUploaded?.();
    } catch {
      setStatus("error");
    }
  }

  const selectedDocument = documents.find((item) => item.id === selectedDocumentId);
  const totalChunks = documents.reduce((sum, item) => sum + item.chunk_count, 0);
  const filteredDocuments = filterDocuments(documents, documentQuery);
  const totalDocumentPages = Math.max(1, Math.ceil(filteredDocuments.length / DOCUMENT_PAGE_SIZE));
  const visibleDocuments = filteredDocuments.slice(
    (documentPage - 1) * DOCUMENT_PAGE_SIZE,
    documentPage * DOCUMENT_PAGE_SIZE,
  );
  const totalChunkPages = Math.max(1, Math.ceil(chunks.length / CHUNK_PAGE_SIZE));
  const visibleChunks = chunks.slice((chunkPage - 1) * CHUNK_PAGE_SIZE, chunkPage * CHUNK_PAGE_SIZE);

  return (
    <div className="kb-detail-page">
      <div className="detail-page-heading">
        <div>
          <span>知识库文档</span>
          <h2>{kbName ?? kbId}</h2>
          <p>{kbId}</p>
        </div>
        {onBack ? (
          <button className="button button--secondary" type="button" onClick={onBack}>
            返回知识库列表
          </button>
        ) : null}
      </div>
      <div className="kb-detail-grid">
      <SectionCard title="上传文档">
        <label className="form-field">
          <span>目标知识库</span>
          <input readOnly value={kbId} />
        </label>
        {kbName ? <p className="muted-text">{kbName}</p> : null}
        <label className="form-field">
          <span>文档名称</span>
          <input placeholder="README.md" value={name} onChange={(event) => setName(event.target.value)} />
        </label>
        <label className="form-field">
          <span>Markdown 内容</span>
          <textarea
            placeholder="# 标题&#10;正文"
            rows={8}
            value={content}
            onChange={(event) => setContent(event.target.value)}
          />
        </label>
        <button className="button" type="button" onClick={handleUpload} disabled={!name || !content || status === "loading"}>
          {status === "loading" ? "录入中" : "提交录入"}
        </button>
        {status === "loading" ? <LoadingState label="正在写入检索索引" /> : null}
        {status === "error" ? <ErrorState title="录入失败" onRetry={handleUpload} /> : null}
        {status === "success" ? <EmptyState title="录入完成" description="文档已进入知识库和检索索引。" /> : null}
      </SectionCard>
      <SectionCard title="文档列表">
        <div className="document-toolbar">
          <label className="document-search">
            <span>搜索文档</span>
            <input
              aria-label="搜索文档"
              placeholder="按名称、状态或类型搜索"
              value={documentQuery}
              onChange={(event) => {
                setDocumentQuery(event.target.value);
                setDocumentPage(1);
                setShowChunkConfig(false);
              }}
            />
          </label>
          <button className="button button--secondary" type="button" onClick={() => loadDocuments("retrying")}>
            刷新文档
          </button>
        </div>
        {documentsStatus === "loading" || documentsStatus === "retrying" ? <LoadingState label="加载文档中" /> : null}
        {documentsStatus === "error" ? <ErrorState title="文档加载失败" onRetry={() => loadDocuments("retrying")} /> : null}
        {documentsStatus === "empty" ? (
          <EmptyState title={`知识库 ${kbId} 暂无文档`} description="上传纯文本或 Markdown 后会显示在这里。" />
        ) : null}
        {documents.length > 0 && filteredDocuments.length === 0 ? (
          <EmptyState title="没有匹配文档" description="换一个关键词，或刷新文档后再试。" />
        ) : null}
        {visibleDocuments.length > 0 ? (
          <div className="document-table">
            {visibleDocuments.map((document) => (
              <article
                className={document.id === selectedDocumentId ? "document-row document-row--active" : "document-row"}
                key={document.id}
              >
                <button
                  aria-label={`查看 ${document.document_name} 的 Chunk`}
                  type="button"
                  onClick={() => {
                    setSelectedDocumentId(document.id);
                    setShowChunkConfig(false);
                    setIsChunkDrawerOpen(true);
                    setChunkPage(1);
                  }}
                >
                  <strong>{document.document_name}</strong>
                  <span>{document.content_type ?? "text/markdown"} · {document.status}</span>
                  <span className={`parse-status parse-status--${getParseStatus(document)}`}>
                    {PARSE_STATUS_LABELS[getParseStatus(document)]}
                  </span>
                  {document.parse_error ? <span className="document-row__error">{document.parse_error}</span> : null}
                </button>
                <div className="document-row__meta">
                  <small>{document.chunk_count} chunks</small>
                  <button
                    aria-label={`查看 ${document.document_name} 的分块配置`}
                    className="button button--secondary button--compact"
                    type="button"
                    onClick={() => {
                      setSelectedDocumentId(document.id);
                      setShowChunkConfig(true);
                      setIsChunkDrawerOpen(false);
                    }}
                  >
                    查看配置
                  </button>
                </div>
              </article>
            ))}
          </div>
        ) : null}
        {filteredDocuments.length > DOCUMENT_PAGE_SIZE ? (
          <div className="pagination-bar">
            <button
              aria-label="上一页文档"
              className="button button--secondary button--compact"
              type="button"
              disabled={documentPage <= 1}
              onClick={() => {
                setDocumentPage((current) => Math.max(1, current - 1));
                setShowChunkConfig(false);
                setIsChunkDrawerOpen(false);
              }}
            >
              上一页
            </button>
            <span>文档分页 {documentPage} / {totalDocumentPages}</span>
            <button
              aria-label="下一页文档"
              className="button button--secondary button--compact"
              type="button"
              disabled={documentPage >= totalDocumentPages}
              onClick={() => {
                setDocumentPage((current) => Math.min(totalDocumentPages, current + 1));
                setShowChunkConfig(false);
                setIsChunkDrawerOpen(false);
              }}
            >
              下一页
            </button>
          </div>
        ) : filteredDocuments.length > 0 ? (
          <div className="pagination-bar pagination-bar--quiet">
            <span>文档分页 {documentPage} / {totalDocumentPages}</span>
          </div>
        ) : null}
      </SectionCard>
      {showChunkConfig && selectedDocument ? (
        <SectionCard title="分块策略">
          <div className="chunk-policy">
            <div>
              <span>策略</span>
              <strong>按 Markdown 标题切分</strong>
            </div>
            <div>
              <span>窗口</span>
              <strong>1200 字符</strong>
            </div>
            <div>
              <span>重叠</span>
              <strong>120 字符</strong>
            </div>
            <div>
              <span>当前文档</span>
              <strong>{selectedDocument.chunk_count} chunks</strong>
            </div>
            <div>
              <span>知识库规模</span>
              <strong>{documents.length} 文档 / {totalChunks} chunks</strong>
            </div>
          </div>
          <div className="rule-list">
            <p>Markdown 标题会作为 chunk 标题保留，长正文使用滑动窗口切分。</p>
            <p>纯文本没有标题时会按正文窗口切分。</p>
            <p>每次文档 upsert 会替换该文档旧 chunk，并同步写入 ES/Milvus。</p>
          </div>
        </SectionCard>
      ) : null}
      </div>
      {isChunkDrawerOpen && selectedDocument ? (
        <aside
          aria-label={`${selectedDocument.document_name} Chunk 明细`}
          className="chunk-drawer"
          role="dialog"
        >
          <div className="chunk-drawer__header">
            <div>
              <span>Chunk 明细</span>
              <strong>{selectedDocument.document_name}</strong>
              <small>{selectedDocument.chunk_count} chunks</small>
            </div>
            <button
              aria-label="关闭 Chunk 明细"
              className="icon-button"
              type="button"
              onClick={() => setIsChunkDrawerOpen(false)}
            >
              关闭
            </button>
          </div>
          <div className="chunk-drawer__body">
            {chunksStatus === "loading" || chunksStatus === "retrying" ? <LoadingState label="加载 Chunk 中" /> : null}
            {chunksStatus === "error" ? (
              <ErrorState title="Chunk 加载失败" onRetry={() => loadChunks(selectedDocument.id, "retrying")} />
            ) : null}
            {chunksStatus === "empty" ? <EmptyState title="暂无 Chunk" description="该文档还没有可展示的分块。" /> : null}
            {visibleChunks.length > 0 ? (
              <div className="chunk-list">
                {visibleChunks.map((chunk) => (
                  <article className="chunk-card" key={chunk.id}>
                    <div>
                      <strong>Chunk #{chunk.chunk_index}</strong>
                      <span>{chunk.title || "无标题"} · {chunk.token_count ?? chunk.content.length} tokens</span>
                    </div>
                    <p>{chunk.content || "空内容"}</p>
                  </article>
                ))}
              </div>
            ) : null}
          </div>
          {chunks.length > 0 ? (
            <div className="pagination-bar chunk-drawer__pagination">
              <button
                aria-label="上一页 Chunk"
                className="button button--secondary button--compact"
                type="button"
                disabled={chunkPage <= 1}
                onClick={() => setChunkPage((current) => Math.max(1, current - 1))}
              >
                上一页
              </button>
              <span>Chunk 分页 {chunkPage} / {totalChunkPages}</span>
              <button
                aria-label="下一页 Chunk"
                className="button button--secondary button--compact"
                type="button"
                disabled={chunkPage >= totalChunkPages}
                onClick={() => setChunkPage((current) => Math.min(totalChunkPages, current + 1))}
              >
                下一页
              </button>
            </div>
          ) : null}
        </aside>
      ) : null}
    </div>
  );
}

function filterDocuments(documents: KnowledgeDocument[], query: string): KnowledgeDocument[] {
  const normalizedQuery = query.trim().toLowerCase();
  if (!normalizedQuery) {
    return documents;
  }
  return documents.filter((document) => {
    const searchableText = [
      document.document_name,
      document.content_type ?? "",
      document.status,
      getParseStatus(document),
      document.parse_error ?? "",
      String(document.chunk_count),
    ].join(" ").toLowerCase();
    return searchableText.includes(normalizedQuery);
  });
}

function getParseStatus(document: KnowledgeDocument): DocumentParseStatus {
  const status = document.parse_status;
  return status && status in PARSE_STATUS_LABELS ? status : "indexed";
}

function getVisibleDocuments(documents: KnowledgeDocument[], query: string, page: number): KnowledgeDocument[] {
  const filteredDocuments = filterDocuments(documents, query);
  return filteredDocuments.slice((page - 1) * DOCUMENT_PAGE_SIZE, page * DOCUMENT_PAGE_SIZE);
}
