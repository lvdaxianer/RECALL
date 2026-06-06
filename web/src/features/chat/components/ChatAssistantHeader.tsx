/**
 * Recall · 聊天抽屉顶栏
 *
 * 三段：品牌标（左） + 证据面板开关（中右） + 关闭（右）。
 *
 * @author lvdaxianerplus
 */
import { PanelRightClose, PanelRightOpen, X } from "lucide-react";

/**
 * 聊天抽屉顶栏 props 集合。
 *
 * @author lvdaxianerplus
 */
export interface ChatAssistantHeaderProps {
  /** 证据面板是否展开（决定按钮图标） */
  evidenceOpen: boolean;
  /** 切换证据面板回调 */
  onToggleEvidence: () => void;
  /** 关闭整个抽屉回调 */
  onClose: () => void;
}

/**
 * 聊天抽屉顶栏组件。
 *
 * @param props.evidenceOpen 证据面板是否展开
 * @param props.onToggleEvidence 切换证据面板
 * @param props.onClose 关闭抽屉
 * @author lvdaxianerplus
 */
export function ChatAssistantHeader({ evidenceOpen, onToggleEvidence, onClose }: ChatAssistantHeaderProps) {
  return (
    <header className="flex h-14 shrink-0 items-center gap-3 border-b border-slate-200 bg-white px-5">
      {/* 左侧：品牌标 + 副标题 */}
      <div className="flex items-center gap-2.5">
        <span
          aria-hidden="true"
          className="grid size-7 place-items-center rounded-md bg-emerald-600 text-xs font-bold text-white shadow-sm"
        >
          R
        </span>
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold text-slate-900">Recall 助手</p>
          {/* 副标题：核心卖点（证据优先 + 仅已发布 KB） */}
          <p className="truncate text-[11px] text-slate-500">
            <span>证据优先</span>
            <span aria-hidden="true"> · </span>
            <span>只检索已发布知识库</span>
          </p>
        </div>
      </div>
      {/* 右侧：证据面板开关 + 关闭按钮（用 ml-auto 推到最右） */}
      <div className="ml-auto flex items-center gap-2">
        <button
          aria-label={evidenceOpen ? "隐藏证据面板" : "显示证据面板"}
          className="grid size-8 place-items-center rounded-md border border-slate-200 bg-white text-slate-500 transition-colors hover:border-slate-300 hover:bg-slate-50 hover:text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500"
          type="button"
          onClick={onToggleEvidence}
        >
          {/* 展开时显示 close 图标（"折叠"），未展开时显示 open 图标（"展开"） */}
          {evidenceOpen ? (
            <PanelRightClose aria-hidden="true" className="size-4" />
          ) : (
            <PanelRightOpen aria-hidden="true" className="size-4" />
          )}
        </button>
        <button
          aria-label="关闭 Recall 助手"
          className="grid size-8 place-items-center rounded-md border border-slate-200 bg-white text-slate-500 transition-colors hover:border-slate-300 hover:bg-slate-50 hover:text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500"
          type="button"
          onClick={onClose}
        >
          <X aria-hidden="true" className="size-4" />
        </button>
      </div>
    </header>
  );
}
