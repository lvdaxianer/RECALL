/**
 * Recall · 聊天抽屉内嵌证据侧栏
 *
 * 与 `EvidenceSheet`（Sheet 弹层版）共享 `EvidencePanel` 渲染主体。
 * 顶部展示标题 + 事件数 + 关闭按钮；空态给用户提示如何触发证据展示。
 *
 * @author lvdaxianerplus
 */
import type { AgentEvent } from "../../../api/sessions";
import { EvidencePanel } from "../../../components/recall/EvidencePanel";

/**
 * 聊天抽屉内嵌证据侧栏 props 集合。
 *
 * @author lvdaxianerplus
 */
export interface ChatEvidencePanelProps {
  /** 当前展示的事件流（null = 暂无） */
  events: AgentEvent[] | null;
  /** 是否展开 */
  isOpen: boolean;
  /** 关闭回调 */
  onClose: () => void;
}

/**
 * 聊天抽屉内嵌证据侧栏组件。
 *
 * @param props.events 事件流
 * @param props.isOpen 是否展开
 * @param props.onClose 关闭回调
 * @author lvdaxianerplus
 */
export function ChatEvidencePanel({ events, isOpen, onClose }: ChatEvidencePanelProps) {
  // 未展开时不渲染（父组件已经做了条件渲染，但这里再保险一次）
  if (!isOpen) {
    return null;
  }
  return (
    <aside className="flex min-h-0 flex-col border-l border-slate-200 bg-white">
      {/* 顶部：标题 + 事件数 + 关闭 */}
      <div className="flex h-14 shrink-0 items-center gap-2 border-b border-slate-200 px-5">
        <h2 className="text-sm font-semibold text-slate-900">证据 & Trace</h2>
        {/* 事件数（右对齐） */}
        <span className="ml-auto font-mono text-[11px] text-slate-400">
          {events ? events.length : 0} events
        </span>
        <button
          aria-label="关闭证据面板"
          className="ml-2 grid size-7 place-items-center rounded-md border border-slate-200 bg-white text-slate-500 transition-colors hover:border-slate-300 hover:bg-slate-50 hover:text-slate-900"
          type="button"
          onClick={onClose}
        >
          ×
        </button>
      </div>
      {/* 主体：EvidencePanel 渲染；空态给用户提示 */}
      <div className="flex-1 overflow-auto p-4">
        {events ? (
          <EvidencePanel events={events} />
        ) : (
          <div className="grid h-full place-items-center text-center">
            <div className="space-y-1.5">
              <p className="text-sm font-medium text-slate-700">还没有证据</p>
              <p className="text-xs text-slate-500">
                在助手回答里点「查看证据与 Trace」
                <br />
                即可看到引用与检索阶段。
              </p>
            </div>
          </div>
        )}
      </div>
    </aside>
  );
}
