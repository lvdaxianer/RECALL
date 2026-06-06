/**
 * Recall · 分块配置侧栏（只读）
 *
 * 右侧抽屉：展示当前文档的分块策略元信息。
 * 当前只展示后端固定的策略 / 窗口 / 重叠参数（v1.4 起还在演进）。
 * 真实"配置"修改在 `KbSettingsSheet`（按 KB 维度）。
 *
 * 设计要点：
 * 1. 防御性渲染：selectedDocument 为空时不渲染
 * 2. 上半：2x2 网格展示 4 个分块核心参数
 * 3. 下半：知识库规模汇总 + 分块策略说明 bullet
 * 4. 全部走 stat / strong 标签保持屏幕阅读器可达
 * 5. 关闭按钮 + ESC 自动关闭走 Sheet 默认行为
 *
 * @author lvdaxianerplus
 */
import type { KnowledgeDocument } from "../../api/documents";

/**
 * 分块配置侧栏 props 集合。
 *
 * @author lvdaxianerplus
 */
export interface ChunkConfigDrawerProps {
  /** 当前选中文档；为 null 时不渲染 */
  selectedDocument: KnowledgeDocument | null;
  /** 知识库总 Chunk 数（用于汇总展示） */
  totalChunks: number;
  /** 知识库总文档数（用于汇总展示） */
  totalDocuments: number;
  /** 关闭回调 */
  onClose: () => void;
}

/**
 * 分块配置侧栏：展示当前文档的分块策略元信息。
 *
 * @param props.selectedDocument 当前选中文档
 * @param props.totalChunks 知识库总 Chunk 数
 * @param props.totalDocuments 知识库总文档数
 * @param props.onClose 关闭回调
 * @author lvdaxianerplus
 */
export function ChunkConfigDrawer({
  selectedDocument,
  totalChunks,
  totalDocuments,
  onClose,
}: ChunkConfigDrawerProps) {
  // 没有选中文档时不渲染（父组件条件渲染之外的保险）
  if (!selectedDocument) {
    return null;
  }
  return (
    <aside
      aria-label={`${selectedDocument.document_name} 分块策略`}
      // 右侧抽屉：固定定位 + 桌面 520px
      className="fixed inset-y-0 right-0 z-40 flex w-full flex-col border-l border-slate-200 bg-white shadow-2xl shadow-slate-900/20 ring-1 ring-slate-900/5 sm:right-0 sm:w-[min(520px,calc(100vw-24px))]"
      role="dialog"
    >
      {/* 顶部：标题 + 文档名 + 关闭按钮 */}
      <div className="flex items-start justify-between gap-4 border-b border-slate-200 p-5">
        <div>
          <span className="text-xs font-semibold uppercase tracking-wider text-emerald-600">分块策略</span>
          <strong className="mt-1 block text-base font-semibold text-slate-900">
            {selectedDocument.document_name}
          </strong>
          <small className="text-xs text-slate-500">当前文档的分块配置</small>
        </div>
        <button
          aria-label="关闭分块策略"
          className="h-8 rounded-md border border-slate-200 bg-white px-3 text-sm text-slate-700 transition-colors hover:border-slate-300 hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500"
          type="button"
          onClick={onClose}
        >
          关闭
        </button>
      </div>
      <div className="min-h-0 flex-1 space-y-3 overflow-auto p-5">
        {/* 上半：2x2 网格展示分块核心参数 */}
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
            <span className="text-xs text-slate-500">策略</span>
            <strong className="mt-1 block text-sm font-semibold text-slate-900">按 Markdown 标题切分</strong>
          </div>
          <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
            <span className="text-xs text-slate-500">窗口</span>
            <strong className="mt-1 block text-sm font-semibold text-slate-900">1200 字符</strong>
          </div>
          <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
            <span className="text-xs text-slate-500">重叠</span>
            <strong className="mt-1 block text-sm font-semibold text-slate-900">120 字符</strong>
          </div>
          <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
            <span className="text-xs text-slate-500">当前文档</span>
            <strong className="mt-1 block text-sm font-semibold text-slate-900">
              {selectedDocument.chunk_count} chunks
            </strong>
          </div>
        </div>
        {/* 下半：知识库规模汇总 */}
        <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
          <span className="text-xs text-slate-500">知识库规模</span>
          <strong className="mt-1 block text-sm font-semibold text-slate-900">
            {totalDocuments} 文档 / {totalChunks} chunks
          </strong>
        </div>
        {/* 底部：分块策略说明 bullet 列表 */}
        <ul className="space-y-2 rounded-lg border border-slate-200 bg-white p-4 text-sm text-slate-600">
          <li className="flex gap-2">
            <span aria-hidden="true" className="text-emerald-500">•</span>
            Markdown 标题会作为 chunk 标题保留，长正文使用滑动窗口切分。
          </li>
          <li className="flex gap-2">
            <span aria-hidden="true" className="text-emerald-500">•</span>
            纯文本没有标题时会按正文窗口切分。
          </li>
          <li className="flex gap-2">
            <span aria-hidden="true" className="text-emerald-500">•</span>
            每次文档 upsert 会替换该文档旧 chunk，并同步写入 ES/Milvus。
          </li>
        </ul>
      </div>
    </aside>
  );
}
