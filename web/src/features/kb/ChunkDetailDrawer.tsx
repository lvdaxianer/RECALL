import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import type { KnowledgeChunk, KnowledgeDocument } from "../../api/documents";
import { EmptyState } from "../../components/common/EmptyState";
import { ErrorState } from "../../components/common/ErrorState";
import { LoadingState } from "../../components/common/LoadingState";
import { Button } from "../../components/ui/button";

/**
 * Chunk 详情抽屉 props。
 *
 * @author lvdaxianerplus
 */
/**
 * ChunkDetailDrawer 的属性接口（用于 props 契约说明）。
 *
 * 所有字段都从父组件（KnowledgeBaseDetailPage）传入，本组件纯展示。
 */
export interface ChunkDetailDrawerProps {
  selectedDocument: KnowledgeDocument | null;
  chunks: KnowledgeChunk[];
  chunksStatus: "idle" | "loading" | "success" | "empty" | "error" | "retrying";
  page: number;
  totalPages: number;
  pageSize: number;
  onPageChange: (page: number) => void;
  onClose: () => void;
  onRetry: () => void;
}

/**
 * Chunk 详情抽屉：左侧滑出，展示文档分块内容。
 *
 * 设计要点：
 * 1. 仅在 selectedDocument 存在时渲染（防御性条件渲染）
 * 2. visibleChunks 在渲染前切片，避免父组件重复计算
 * 3. 顶部 / 主体 / 分页三段布局；分页仅在有 chunk 时展示
 * 4. Markdown 内容限高 max-h-48 滚动，避免单 chunk 顶穿抽屉
 * 5. 关闭按钮 + 分页按钮走 shadcn Button，保证焦点环一致
 * 6. 所有状态用 props 显式传入，便于父组件集中状态管理
 * 7. token_count 缺失时回退到 content.length，避免 NaN
 * 8. content 缺失时给"（空内容）"占位，避免空白卡片
 * 9. Markdown 走 react-markdown + remark-gfm，与聊天回复样式保持一致
 * 10. prose 样式通过 &_* 原子类覆盖，不引入额外 wrapper
 *
 * @param props 抽屉配置
 * @author lvdaxianerplus
 */
export function ChunkDetailDrawer({
  selectedDocument,
  chunks,
  chunksStatus,
  page,
  totalPages,
  pageSize,
  onPageChange,
  onClose,
  onRetry,
}: ChunkDetailDrawerProps) {
  // 1. 没有选中文档时不渲染抽屉
  if (!selectedDocument) {
    return null;
  }
  // 2. 按当前页截取可见 chunk 列表
  const visibleChunks = chunks.slice((page - 1) * pageSize, page * pageSize);

  // 3. 渲染抽屉：aside 固定定位 + 移动端全宽 / 桌面 520px
  return (
    // 左侧滑出抽屉：固定定位 + 移动端全宽，桌面 520px
    <aside
      aria-label={`${selectedDocument.document_name} Chunk 明细`}
      className="fixed inset-y-0 left-0 z-40 flex w-full flex-col border-r border-slate-200 bg-white shadow-2xl shadow-slate-900/20 ring-1 ring-slate-900/5 sm:left-0 sm:w-[min(520px,calc(100vw-24px))]"
      role="dialog"
    >
      {/* 顶部区：标题 eyebrow + 文档名 + chunk 数 + 关闭按钮 */}
      <div className="flex items-start justify-between gap-4 border-b border-slate-200 p-5">
        <div>
          <span className="text-xs font-semibold uppercase tracking-wider text-emerald-600">Chunk 明细</span>
          <strong className="mt-1 block text-base font-semibold text-slate-900">
            {selectedDocument.document_name}
          </strong>
          <small className="text-xs text-slate-500">{selectedDocument.chunk_count} chunks</small>
        </div>
        <button
          aria-label="关闭 Chunk 明细"
          className="h-8 rounded-md border border-slate-200 bg-white px-3 text-sm text-slate-700 transition-colors hover:border-slate-300 hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500"
          type="button"
          onClick={onClose}
        >
          关闭
        </button>
      </div>
      {/* 主体：状态分派 + chunk 列表 */}
      <div className="min-h-0 flex-1 overflow-auto p-4">
        {/* 加载中 / 重试中：都显示 LoadingState */}
        {chunksStatus === "loading" || chunksStatus === "retrying" ? <LoadingState label="加载 Chunk 中" /> : null}
        {chunksStatus === "error" ? <ErrorState title="Chunk 加载失败" onRetry={onRetry} /> : null}
        {chunksStatus === "empty" ? <EmptyState title="暂无 Chunk" description="该文档还没有可展示的分块。" /> : null}
        {visibleChunks.length > 0 ? (
          <div className="space-y-2">
            {visibleChunks.map((chunk) => (
              // 1. key 用 chunk.id；2. 卡内分三段：头部 / 内容 / 元信息
              <article
                className="flex flex-col gap-2 rounded-lg border border-slate-200 bg-white p-3"
                key={chunk.id}
              >
                {/* 头部：chunk 序号 + 标题 + token 数 */}
                <div className="flex items-center justify-between gap-2">
                  <strong className="text-sm font-medium text-slate-900">Chunk #{chunk.chunk_index}</strong>
                  <span className="font-mono text-xs text-slate-500">
                    {/* token 数兜底 content 长度（未提供 token_count 时） */}
                    {chunk.title || "无标题"} · {chunk.token_count ?? chunk.content.length} tokens
                  </span>
                </div>
                {/* Markdown 内容：限定高度滚动，避免超长 chunk 把抽屉顶穿 */}
                <div className="max-h-48 overflow-auto rounded-md border border-slate-200 bg-slate-50/40 p-3 text-sm leading-6 text-slate-800 [&_a]:font-medium [&_a]:text-emerald-700 [&_a]:no-underline hover:[&_a]:underline [&_blockquote]:rounded [&_blockquote]:border-l-2 [&_blockquote]:border-slate-300 [&_blockquote]:bg-white [&_blockquote]:px-3 [&_blockquote]:py-2 [&_blockquote]:text-slate-500 [&_code]:rounded [&_code]:bg-white [&_code]:px-1 [&_code]:py-px [&_code]:font-mono [&_code]:text-[0.9em] [&_h1]:text-base [&_h1]:font-semibold [&_h2]:text-sm [&_h2]:font-semibold [&_h3]:text-sm [&_h3]:font-semibold [&_h4]:text-sm [&_h4]:font-medium [&_hr]:my-2 [&_hr]:border-slate-200 [&_img]:max-h-40 [&_img]:rounded [&_img]:border [&_img]:border-slate-200 [&_li]:my-0 [&_ol]:m-0 [&_ol]:list-decimal [&_ol]:pl-5 [&_p]:m-0 [&_pre]:overflow-auto [&_pre]:rounded [&_pre]:bg-white [&_pre]:p-2 [&_pre]:font-mono [&_pre]:text-xs [&_table]:block [&_table]:max-w-full [&_table]:overflow-x-auto [&_table]:rounded [&_table]:border [&_table]:border-slate-200 [&_table]:text-xs [&_td]:border-b [&_td]:border-slate-200 [&_td]:px-2 [&_td]:py-1 [&_th]:border-b [&_th]:border-slate-200 [&_th]:bg-white [&_th]:px-2 [&_th]:py-1 [&_th]:text-left [&_th]:font-semibold [&_ul]:m-0 [&_ul]:list-disc [&_ul]:pl-5">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>
                    {/* content 缺失时给"空内容"占位，避免空白卡片 */}
                    {chunk.content || "空内容"}
                  </ReactMarkdown>
                </div>
              </article>
            ))}
          </div>
        ) : null}
      </div>
      {/* 底部：分页控制（仅当有 chunk 时展示） */}
      {chunks.length > 0 ? (
        <div className="flex items-center justify-between gap-2 border-t border-slate-200 p-4 text-sm text-slate-500">
          {/* 上一页：第一页时禁用 */}
          <Button
            aria-label="上一页 Chunk"
            disabled={page <= 1}
            size="sm"
            type="button"
            variant="secondary"
            onClick={() => onPageChange(Math.max(1, page - 1))}
          >
            上一页
          </Button>
          <span>Chunk 分页 {page} / {totalPages}</span>
          {/* 下一页：最后一页时禁用 */}
          <Button
            aria-label="下一页 Chunk"
            disabled={page >= totalPages}
            size="sm"
            type="button"
            variant="secondary"
            onClick={() => onPageChange(Math.min(totalPages, page + 1))}
          >
            下一页
          </Button>
        </div>
      ) : null}
    </aside>
  );
}
