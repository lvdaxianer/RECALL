/**
 * Recall · KB 列表视图（dense table 风格）
 *
 * 整行可点；hover 出现左侧 2px emerald 色条 + 浅灰底。
 * 错误行内嵌错误条（发布 / 删除），操作区每行 4 个按钮。
 *
 * 设计要点：
 * 1. 用 grid + 固定列宽保证每行严格对齐（避免 table 跨行错位）
 * 2. 整行可点击 + 键盘 Enter/Space 触发同样回调（role="button" + tabIndex=0）
 * 3. TooltipProvider 包整张表，工具提示共享同一 context
 * 4. 错误条按 "publish" / "delete" 分别展示，便于用户区分
 * 5. 操作按钮 stopPropagation 阻止冒泡到 li 的 onClick（否则会跳到详情）
 * 6. 发布/删除按钮按 KB 状态 disabled（已发布/已删除/已归档的不能重复操作）
 * 7. 文档数占位 "—"：后端 KnowledgeBase 类型未返回 document_count，待扩展
 * 8. 状态徽章走策略模式（KB_STATUS_TO_BADGE 映射）替代 if 链
 *
 * @author lvdaxianerplus
 */
import { ExternalLink, Settings, Trash2 } from "lucide-react";

import type { KnowledgeBase } from "../../api/types";
import { StatusBadge } from "../../components/recall/StatusBadge";
import { Button } from "../../components/ui/button";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "../../components/ui/tooltip";
import { cn } from "../../lib/utils";
import { KB_STATUS, KB_STATUS_LABELS, KB_STATUS_TO_BADGE } from "../chat/runtime/chatConstants";

/**
 * KB 列表视图 props 集合。
 *
 * @author lvdaxianerplus
 */
export interface KbListViewProps {
  items: KnowledgeBase[];
  publishingId: string | null;
  publishErrorId: string | null;
  publishErrorMessage: string | null;
  deletingId: string | null;
  deleteErrorId: string | null;
  deleteErrorMessage: string | null;
  onOpenDetail: (id: string) => void;
  onPublish: (id: string) => void;
  onOpenSettings: (item: KnowledgeBase) => void;
  onDelete: (item: KnowledgeBase) => void;
}

/**
 * 知识库状态 → 中文标签。
 *
 * @param status 后端状态字符串
 * @author lvdaxianerplus
 */
function getStatusLabel(status: string): string {
  return KB_STATUS_LABELS[status] ?? status;
}

/**
 * KB 列表视图：dense table 风格。整行可点；hover 出现左侧 2px emerald 色条 + 浅灰底。
 *
 * @author lvdaxianerplus
 */
export function KbListView({
  items,
  publishingId,
  publishErrorId,
  publishErrorMessage,
  deletingId,
  deleteErrorId,
  deleteErrorMessage,
  onOpenDetail,
  onPublish,
  onOpenSettings,
  onDelete,
}: KbListViewProps) {
  return (
    // 整张表用 grid 布局 + 固定列宽，保证行高与列宽完全对齐
    <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-xs">
      <div
        className="grid items-center gap-3 border-b border-slate-200 bg-slate-50/60 px-4 py-2.5 text-[11px] font-semibold uppercase tracking-wider text-slate-500"
        style={{ gridTemplateColumns: "minmax(0,1.6fr) minmax(0,2fr) 100px 56px 140px" }}
      >
        {/* 表头列：名称 / 描述 / 状态 / 文档 / 操作 */}
        <span>名称</span>
        <span>描述</span>
        <span>状态</span>
        <span>文档</span>
        <span className="text-right">操作</span>
      </div>
      <ul className="divide-y divide-slate-100">
        {items.map((item) => {
          // 1. 是否该行处于错误态（用于展示错误条）
          const isPublishError = publishErrorId === item.id;
          const isDeleteError = deleteErrorId === item.id;
          return (
            // 2. 整行可点击 + 键盘可达（Enter / Space 触发同样回调）
            <li
              className="group relative grid cursor-pointer items-center gap-3 px-4 py-2.5 transition-colors hover:bg-slate-50 focus-within:bg-slate-50 focus-visible:outline-none"
              key={item.id}
              onClick={() => onOpenDetail(item.id)}
              onKeyDown={(event) => {
                // 阻止 Enter / Space 的默认滚动行为
                if (event.key !== "Enter" && event.key !== " ") {
                  return;
                }
                event.preventDefault();
                onOpenDetail(item.id);
              }}
              role="button"
              tabIndex={0}
              style={{ gridTemplateColumns: "minmax(0,1.6fr) minmax(0,2fr) 100px 56px 140px" }}
            >
              {/* TooltipProvider 包整行，让 hover 文字可在子组件里共享 context */}
              <TooltipProvider>
              <span
                aria-hidden="true"
                className="pointer-events-none absolute inset-y-2 left-0 w-0.5 rounded-full bg-emerald-500 opacity-0 transition-opacity group-hover:opacity-100 group-focus-within:opacity-100"
              />
              <span className="truncate pl-1.5 text-sm font-medium text-slate-900 group-hover:text-emerald-700">
                {item.name}
              </span>
              <span className="truncate text-xs text-slate-500">{item.description || "—"}</span>
              <StatusBadge variant={KB_STATUS_TO_BADGE[item.status] ?? "neutral"}>
                {getStatusLabel(item.status)}
              </StatusBadge>
              {/* 文档数：后端 KnowledgeBase 类型未返回 document_count 字段；保留占位以便将来接入 */}
              <span className="font-mono text-xs text-slate-400" title="文档数待后端 KnowledgeBase 契约扩展">
                —
              </span>
              <div
                className="flex items-center justify-end gap-1"
                onClick={(event) => event.stopPropagation()}
              >
                <Button
                  aria-label={`查看文档 ${item.name}`}
                  className="h-7 px-2 text-xs"
                  size="sm"
                  type="button"
                  variant="secondary"
                  onClick={() => onOpenDetail(item.id)}
                >
                  <ExternalLink aria-hidden="true" className="h-3.5 w-3.5" />
                  查看文档
                </Button>
                {item.status !== KB_STATUS.PUBLISHED &&
                item.status !== KB_STATUS.DELETED &&
                item.status !== KB_STATUS.ARCHIVED ? (
                  <Button
                    aria-label={`发布 ${item.name}`}
                    className="h-7 px-2 text-xs hover:bg-emerald-50 hover:text-emerald-700"
                    size="sm"
                    type="button"
                    variant="ghost"
                    disabled={publishingId === item.id}
                    onClick={() => onPublish(item.id)}
                  >
                    {publishingId === item.id ? "发布中" : "发布"}
                  </Button>
                ) : null}
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Button
                      aria-label={`设置 ${item.name} 知识库`}
                      className="hover:bg-slate-100"
                      size="icon-sm"
                      type="button"
                      variant="ghost"
                      onClick={() => onOpenSettings(item)}
                    >
                      <Settings aria-hidden="true" className="h-4 w-4" />
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent>设置分块参数</TooltipContent>
                </Tooltip>
                {item.status !== KB_STATUS.DELETED && item.status !== KB_STATUS.ARCHIVED ? (
                  <Button
                    aria-label={`删除知识库 ${item.name}`}
                    className="text-red-600 hover:bg-red-50 hover:text-red-700"
                    disabled={deletingId === item.id}
                    size="icon-sm"
                    type="button"
                    variant="ghost"
                    onClick={() => onDelete(item)}
                  >
                    <Trash2 aria-hidden="true" className="h-4 w-4" />
                  </Button>
                ) : null}
              </div>
              {isPublishError || isDeleteError ? (
                <span className="col-span-full mt-1 block text-[11px] text-red-600" role="alert">
                  {isPublishError
                    ? `发布失败：${publishErrorMessage ?? "请稍后重试"}`
                    : `删除失败：${deleteErrorMessage ?? "请稍后重试"}`}
                </span>
              ) : null}
              </TooltipProvider>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
