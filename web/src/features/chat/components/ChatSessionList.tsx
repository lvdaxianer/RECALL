/**
 * Recall · 聊天会话列表侧栏
 *
 * 显示会话标题 + 消息数 + 选中态高亮。
 * 顶部"+"按钮触发新建会话；底部展示已发布 KB 数。
 *
 * @author lvdaxianerplus
 * @date 2026-06-06
 */
import { useState, type KeyboardEvent } from "react";
import { Check, Pencil, Plus, X } from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * 单条会话摘要（用于侧栏列表展示）。
 *
 * @author lvdaxianerplus
 * @date 2026-06-06
 */
export interface ChatSessionListItem {
  id: string;
  title: string;
  messages: unknown[];
}

/**
 * 聊天会话列表 props 集合。
 *
 * @author lvdaxianerplus
 * @date 2026-06-06
 */
export interface ChatSessionListProps {
  sessions: ChatSessionListItem[];
  activeSessionId: string;
  publishedKbCount: number;
  onSelectSession: (id: string) => void;
  onCreateSession: () => void;
  onRenameSession?: (id: string, title: string) => void;
}

/**
 * 聊天会话列表侧栏。
 *
 * @param props 列表配置
 * @author lvdaxianerplus
 * @date 2026-06-06
 */
export function ChatSessionList({
  sessions,
  activeSessionId,
  publishedKbCount,
  onSelectSession,
  onCreateSession,
  onRenameSession,
}: ChatSessionListProps) {
  const [editingSessionId, setEditingSessionId] = useState<string | null>(null);
  const [draftTitle, setDraftTitle] = useState("");

  /**
   * 进入会话标题编辑态。
   *
   * @param session - 待编辑会话
   * @author lvdaxianerplus
   * @date 2026-06-06
   */
  function startEditing(session: ChatSessionListItem): void {
    setEditingSessionId(session.id);
    setDraftTitle(session.title);
  }

  /**
   * 取消会话标题编辑。
   *
   * @author lvdaxianerplus
   * @date 2026-06-06
   */
  function cancelEditing(): void {
    setEditingSessionId(null);
    setDraftTitle("");
  }

  /**
   * 提交会话标题编辑。
   *
   * @author lvdaxianerplus
   * @date 2026-06-06
   */
  function submitEditing(): void {
    const title = draftTitle.trim();
    editingSessionId && title ? onRenameSession?.(editingSessionId, title) : undefined;
    cancelEditing();
  }

  /**
   * 处理标题输入框快捷键。
   *
   * @param event - 键盘事件
   * @author lvdaxianerplus
   * @date 2026-06-06
   */
  function handleTitleKeyDown(event: KeyboardEvent<HTMLInputElement>): void {
    const actions: Record<string, () => void> = {
      Enter: submitEditing,
      Escape: cancelEditing,
    };
    actions[event.key]?.();
  }

  return (
    <aside className="flex min-h-0 flex-col border-r border-slate-200 bg-white">
      {/* 顶部：标题 + 新建按钮 */}
      <div className="flex items-center justify-between border-b border-slate-200 px-4 py-3">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-500">会话</h2>
        <button
          aria-label="新建会话"
          className="grid size-6 place-items-center rounded-md text-slate-500 transition-colors hover:bg-emerald-50 hover:text-emerald-700"
          type="button"
          onClick={onCreateSession}
        >
          <Plus aria-hidden="true" className="size-4" />
        </button>
      </div>
      {/* 会话列表：选中项 emerald 高亮 + 边框 */}
      <ul className="flex-1 space-y-0.5 overflow-auto p-2">
        {sessions.map((session) => {
          const isActive = session.id === activeSessionId;
          const isEditing = session.id === editingSessionId;
          return (
            <li key={session.id}>
              <div
                className={cn(
                  // 基础：紧凑、圆角、过渡
                  "group flex w-full flex-col gap-1 rounded-md px-2.5 py-2 text-left transition-all",
                  // 选中：emerald 边框 + 背景 + 阴影
                  // 未选中：透明边框（hover 时显现）
                  isActive
                    ? "border border-emerald-200 bg-emerald-50 shadow-sm"
                    : "border border-transparent hover:border-slate-200 hover:bg-slate-50",
                )}
              >
                {/* 会话标题：单行省略 */}
                {isEditing ? (
                  <div className="flex items-center gap-1">
                    <input
                      aria-label="会话名称"
                      className="min-w-0 flex-1 rounded-md border border-emerald-200 bg-white px-2 py-1 text-sm text-slate-900 outline-none focus:border-emerald-500 focus:ring-2 focus:ring-emerald-500/20"
                      value={draftTitle}
                      onChange={(event) => setDraftTitle(event.target.value)}
                      onKeyDown={handleTitleKeyDown}
                    />
                    <button aria-label="保存会话名称" className="grid size-6 place-items-center rounded-md text-emerald-700 hover:bg-emerald-100" type="button" onClick={submitEditing}>
                      <Check aria-hidden="true" className="size-3.5" />
                    </button>
                    <button aria-label="取消修改会话名称" className="grid size-6 place-items-center rounded-md text-slate-500 hover:bg-slate-100" type="button" onClick={cancelEditing}>
                      <X aria-hidden="true" className="size-3.5" />
                    </button>
                  </div>
                ) : (
                  <div className="flex items-start gap-1">
                    <button
                      aria-current={isActive ? "true" : undefined}
                      className={cn(
                        "min-w-0 flex-1 text-left text-sm font-medium",
                        isActive ? "text-emerald-900" : "text-slate-900 group-hover:text-slate-950",
                      )}
                      type="button"
                      onClick={() => onSelectSession(session.id)}
                    >
                      <span className="line-clamp-1">{session.title}</span>
                    </button>
                    {isActive ? (
                      <button
                        aria-label="修改会话名称"
                        className="grid size-6 shrink-0 place-items-center rounded-md text-slate-400 opacity-100 transition-colors hover:bg-white hover:text-emerald-700"
                        type="button"
                        onClick={() => startEditing(session)}
                      >
                        <Pencil aria-hidden="true" className="size-3.5" />
                      </button>
                    ) : null}
                  </div>
                )}
                {/* 状态点 + 消息数 */}
                <span className="flex items-center gap-1.5 text-[11px] text-slate-500">
                  <span
                    aria-hidden="true"
                    className={cn(
                      "size-1.5 rounded-full",
                      isActive ? "bg-emerald-500" : "bg-slate-300",
                    )}
                  />
                  {session.messages.length} 条消息
                </span>
              </div>
            </li>
          );
        })}
      </ul>
      {/* 底部：KB 可用数提示 */}
      <div className="border-t border-slate-200 p-3">
        <div className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-[11px] text-slate-500">
          {publishedKbCount} 个已发布知识库可用
        </div>
      </div>
    </aside>
  );
}
