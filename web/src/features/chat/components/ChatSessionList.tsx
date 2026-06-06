/**
 * Recall · 聊天会话列表侧栏
 *
 * 显示会话标题 + 消息数 + 选中态高亮。
 * 顶部"+"按钮触发新建会话；底部展示已发布 KB 数。
 *
 * @author lvdaxianerplus
 */
import { Plus } from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * 单条会话摘要（用于侧栏列表展示）。
 *
 * @author lvdaxianerplus
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
 */
export interface ChatSessionListProps {
  sessions: ChatSessionListItem[];
  activeSessionId: string;
  publishedKbCount: number;
  onSelectSession: (id: string) => void;
  onCreateSession: () => void;
}

/**
 * 聊天会话列表侧栏。
 *
 * @param props 列表配置
 * @author lvdaxianerplus
 */
export function ChatSessionList({
  sessions,
  activeSessionId,
  publishedKbCount,
  onSelectSession,
  onCreateSession,
}: ChatSessionListProps) {
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
          return (
            <li key={session.id}>
              <button
                aria-current={isActive ? "true" : undefined}
                className={cn(
                  // 基础：紧凑、圆角、过渡
                  "group flex w-full flex-col gap-0.5 rounded-md px-2.5 py-2 text-left transition-all",
                  // 选中：emerald 边框 + 背景 + 阴影
                  // 未选中：透明边框（hover 时显现）
                  isActive
                    ? "border border-emerald-200 bg-emerald-50 shadow-sm"
                    : "border border-transparent hover:border-slate-200 hover:bg-slate-50",
                )}
                type="button"
                onClick={() => onSelectSession(session.id)}
              >
                {/* 会话标题：单行省略 */}
                <span
                  className={cn(
                    "line-clamp-1 text-sm font-medium",
                    isActive ? "text-emerald-900" : "text-slate-900 group-hover:text-slate-950",
                  )}
                >
                  {session.title}
                </span>
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
              </button>
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
