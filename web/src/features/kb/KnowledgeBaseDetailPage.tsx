/**
 * Recall · 知识库详情页
 *
 * 视图编排（两列 + 抽屉）：
 * 1. 顶部：KB 名 + id + 返回按钮
 * 2. 左列：DocumentUploadCard（写 Markdown + 提交）
 * 3. 右列：搜索 + 文档列表 DocumentStatusTable（分页）
 * 4. 抽屉：ChunkConfigDrawer（分块策略只读）+ ChunkDetailDrawer（chunk 明细分页）
 *
 * 子组件：DocumentUploadCard / DocumentStatusTable / ChunkConfigDrawer / ChunkDetailDrawer
 *
 * 设计要点：
 * 1. kbId 变化时 useEffect 重置 selectedDocument / page / query 等
 * 2. 文档 / chunk 分页各自维护 page state
 * 3. visibleDocuments 切页时若选中行不在可见区，自动重选第一行
 * 4. 错误通过 setDocumentError 暴露到 UI，catch 内静默
 * 5. 上传完成后 refetch（KB 状态可能变更）
 *
 * @author lvdaxianerplus
 */
import { useEffect, useState } from "react";

import { listDocumentChunks, listDocuments, type KnowledgeChunk, type KnowledgeDocument } from "../../api/documents";
import { EmptyState } from "../../components/common/EmptyState";
import { ErrorState } from "../../components/common/ErrorState";
import { LoadingState } from "../../components/common/LoadingState";
import { SectionCard } from "../../components/common/SectionCard";
import { DocumentStatusTable } from "../../components/recall/DocumentStatusTable";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { ChunkConfigDrawer } from "./ChunkConfigDrawer";
import { ChunkDetailDrawer } from "./ChunkDetailDrawer";
import { DocumentUploadCard } from "./DocumentUploadCard";

/**
 * 知识库详情页 props。
 *
 * @author lvdaxianerplus
 */
interface KnowledgeBaseDetailPageProps {
  kbId: string;
  kbName?: string;
  onBack?: () => void;
  onUploaded?: () => void | Promise<void>;
}

/**
 * 加载状态枚举。
 *
 * @author lvdaxianerplus
 */
type LoadStatus = "idle" | "loading" | "success" | "empty" | "error" | "retrying";

const DOCUMENT_PAGE_SIZE = 10;
const CHUNK_PAGE_SIZE = 5;

/**
 * 按名称/状态过滤文档。
 *
 * @param documents 全部文档
 * @param query 搜索关键词
 * @author lvdaxianerplus
 */
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
      document.parse_status ?? "",
      document.parse_error ?? "",
      String(document.chunk_count),
    ].join(" ").toLowerCase();
    return searchableText.includes(normalizedQuery);
  });
}

/**
 * 知识库详情页：上传 + 文档列表 + Chunk 明细 + 分块配置。
 *
 * @param props.kbId 目标 KB id
 * @param props.kbName 目标 KB 名称
 * @param props.onBack 返回回调
 * @param props.onUploaded 录入完成回调
 * @author lvdaxianerplus
 */
export function KnowledgeBaseDetailPage({ kbId, kbName, onBack, onUploaded }: KnowledgeBaseDetailPageProps) {
  const [documents, setDocuments] = useState<KnowledgeDocument[]>([]);
  const [documentsStatus, setDocumentsStatus] = useState<LoadStatus>("idle");
  const [documentError, setDocumentError] = useState<string | null>(null);
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

  /**
   * 加载指定 KB 的文档列表。
   *
   * @param nextStatus 加载状态
   * @author lvdaxianerplus
   */
  async function loadDocuments(nextStatus: LoadStatus = "loading"): Promise<void> {
    setDocumentsStatus(nextStatus);
    try {
      const data = await listDocuments(kbId);
      const nextDocuments = Array.isArray(data) ? data : [];
      setDocuments(nextDocuments);
      setDocumentPage(1);
      setDocumentsStatus(nextDocuments.length > 0 ? "success" : "empty");
      setDocumentError(null);
      if (nextDocuments.length > 0) {
        setSelectedDocumentId((current) => current || nextDocuments[0].id);
      }
    } catch (err) {
      setDocumentsStatus("error");
      setDocumentError(err instanceof Error ? err.message : "文档加载失败");
    }
  }

  /**
   * 加载指定文档的 Chunk 列表。
   *
   * @param documentId 文档 id
   * @param nextStatus 加载状态
   * @author lvdaxianerplus
   */
  async function loadChunks(documentId: string, nextStatus: LoadStatus = "loading"): Promise<void> {
    setChunksStatus(nextStatus);
    try {
      const data = await listDocumentChunks(kbId, documentId);
      const nextChunks = Array.isArray(data) ? data : [];
      setChunks(nextChunks);
      setChunksStatus(nextChunks.length > 0 ? "success" : "empty");
    } catch (err) {
      setChunksStatus("error");
      setDocumentError(err instanceof Error ? err.message : "Chunk 加载失败");
    }
    // chunkError 当前未在 UI 展示；保留 setDocumentError 用以兜底
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

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 rounded-lg border border-slate-200 bg-white p-5 shadow-sm md:flex-row md:items-center md:justify-between">
        <div className="min-w-0">
          <span className="text-xs font-semibold uppercase tracking-wider text-emerald-600">知识库文档</span>
          <h2 className="mt-1 text-xl font-semibold text-slate-900">{kbName ?? kbId}</h2>
          <p className="mt-0.5 font-mono text-xs text-slate-500">{kbId}</p>
        </div>
        {onBack ? (
          <Button type="button" variant="secondary" onClick={onBack}>
            返回知识库列表
          </Button>
        ) : null}
      </div>
      <div className="grid gap-4 lg:grid-cols-[minmax(0,420px)_minmax(0,1fr)]">
        <DocumentUploadCard
          kbId={kbId}
          kbName={kbName}
          onUploaded={() => loadDocuments("retrying")}
        />
        <SectionCard title="文档列表">
          <div className="mb-4 grid gap-3 sm:grid-cols-[1fr_auto] sm:items-end">
            <div className="grid gap-1.5">
              <label className="text-sm font-medium text-slate-900" htmlFor="doc-search">搜索文档</label>
              <Input
                id="doc-search"
                aria-label="搜索文档"
                placeholder="按名称、状态或类型搜索"
                value={documentQuery}
                onChange={(event) => {
                  setDocumentQuery(event.target.value);
                  setDocumentPage(1);
                  setShowChunkConfig(false);
                  setIsChunkDrawerOpen(false);
                }}
              />
            </div>
            <Button type="button" variant="secondary" onClick={() => loadDocuments("retrying")}>
              刷新文档
            </Button>
          </div>
          {documentsStatus === "loading" || documentsStatus === "retrying" ? <LoadingState label="加载文档中" /> : null}
          {documentsStatus === "error" ? (
            <ErrorState
              title="文档加载失败"
              description={documentError ?? undefined}
              onRetry={() => loadDocuments("retrying")}
            />
          ) : null}
          {documentsStatus === "empty" ? (
            <EmptyState title={`知识库 ${kbId} 暂无文档`} description="上传纯文本或 Markdown 后会显示在这里。" />
          ) : null}
          {documents.length > 0 && filteredDocuments.length === 0 ? (
            <EmptyState title="没有匹配文档" description="换一个关键词，或刷新文档后再试。" />
          ) : null}
          {visibleDocuments.length > 0 ? (
            <DocumentStatusTable
              documents={visibleDocuments}
              onOpenChunks={(document) => {
                setSelectedDocumentId(document.id);
                setShowChunkConfig(false);
                setIsChunkDrawerOpen(true);
                setChunkPage(1);
              }}
              onOpenConfig={(document) => {
                setSelectedDocumentId(document.id);
                setShowChunkConfig(true);
                setIsChunkDrawerOpen(false);
              }}
              selectedDocumentId={selectedDocumentId}
            />
          ) : null}
          {filteredDocuments.length > DOCUMENT_PAGE_SIZE ? (
            <div className="mt-3 flex items-center justify-end gap-2 text-sm text-slate-500">
              <Button
                aria-label="上一页文档"
                disabled={documentPage <= 1}
                size="sm"
                type="button"
                variant="secondary"
                onClick={() => {
                  setDocumentPage((current) => Math.max(1, current - 1));
                  setShowChunkConfig(false);
                  setIsChunkDrawerOpen(false);
                }}
              >
                上一页
              </Button>
              <span>文档分页 {documentPage} / {totalDocumentPages}</span>
              <Button
                aria-label="下一页文档"
                disabled={documentPage >= totalDocumentPages}
                size="sm"
                type="button"
                variant="secondary"
                onClick={() => {
                  setDocumentPage((current) => Math.min(totalDocumentPages, current + 1));
                  setShowChunkConfig(false);
                  setIsChunkDrawerOpen(false);
                }}
              >
                下一页
              </Button>
            </div>
          ) : filteredDocuments.length > 0 ? (
            <div className="mt-3 flex items-center justify-start gap-2 text-sm text-slate-500">
              <span>文档分页 {documentPage} / {totalDocumentPages}</span>
            </div>
          ) : null}
        </SectionCard>
      </div>
      {showChunkConfig ? (
        <ChunkConfigDrawer
          selectedDocument={selectedDocument ?? null}
          totalChunks={totalChunks}
          totalDocuments={documents.length}
          onClose={() => setShowChunkConfig(false)}
        />
      ) : null}
      {isChunkDrawerOpen && selectedDocument ? (
        <ChunkDetailDrawer
          chunks={chunks}
          chunksStatus={chunksStatus}
          onClose={() => setIsChunkDrawerOpen(false)}
          onPageChange={setChunkPage}
          onRetry={() => loadChunks(selectedDocument.id, "retrying")}
          page={chunkPage}
          pageSize={CHUNK_PAGE_SIZE}
          selectedDocument={selectedDocument}
          totalPages={totalChunkPages}
        />
      ) : null}
    </div>
  );
}

/**
 * 文档分页 + 过滤。
 *
 * @param documents 全部文档
 * @param query 搜索关键词
 * @param page 页码
 * @author lvdaxianerplus
 */
function getVisibleDocuments(documents: KnowledgeDocument[], query: string, page: number): KnowledgeDocument[] {
  return filterDocuments(documents, query).slice(
    (page - 1) * DOCUMENT_PAGE_SIZE,
    page * DOCUMENT_PAGE_SIZE,
  );
}
