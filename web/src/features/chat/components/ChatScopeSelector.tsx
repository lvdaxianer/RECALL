/**
 * Recall · 聊天知识库范围选择器
 *
 * 折叠态显示已选摘要；展开后多选。
 * 仅"已发布"KB 可用于聊天，未发布/已归档 KB 在下拉里 disabled。
 *
 * @author lvdaxianerplus
 */
import { useState } from "react";

import type { KnowledgeBase } from "../../../api/types";
import { KB_STATUS } from "../runtime/chatConstants";

/**
 * 判断 KB 是否可用于聊天（必须已发布）。
 *
 * @param item KB 视图模型
 * @returns 是否可用于聊天
 * @author lvdaxianerplus
 */
function isPublishedKnowledgeBase(item: KnowledgeBase): boolean {
  return item.status === KB_STATUS.PUBLISHED;
}

/**
 * 聊天 KB 范围选择器 props。
 *
 * @author lvdaxianerplus
 */
export interface ChatScopeSelectorProps {
  /** 全部 KB（可能包含未发布） */
  knowledgeBases: KnowledgeBase[];
  /** 已选 KB id 列表 */
  value: string[];
  /** 选中状态变更回调 */
  onChange: (value: string[]) => void;
}

/**
 * 聊天抽屉内的知识库范围选择器。
 *
 * @param props.knowledgeBases 全部 KB
 * @param props.value 已选 id 列表
 * @param props.onChange 选中状态变更回调
 * @author lvdaxianerplus
 */
export function ChatScopeSelector({ knowledgeBases, value, onChange }: ChatScopeSelectorProps) {
  // 1. 折叠 / 展开状态
  const [isExpanded, setIsExpanded] = useState(false);
  // 2. 搜索关键词
  const [query, setQuery] = useState("");
  // 3. 派生数据
  const selectedItems = knowledgeBases.filter((item) => value.includes(item.id));
  const publishedCount = knowledgeBases.filter(isPublishedKnowledgeBase).length;
  const filteredItems = knowledgeBases.filter((item) =>
    item.name.toLowerCase().includes(query.trim().toLowerCase()),
  );
  // 4. 摘要：超过 2 个时只显示前 2 + "等 N 个"
  const selectedSummary = selectedItems.length > 0
    ? selectedItems.slice(0, 2).map((item) => item.name).join("、")
    : "未选择知识库";
  const overflowCount = selectedItems.length - 2;

  /**
   * 切换 KB 选中状态：仅已发布 KB 可选；已选则移除，未选则追加。
   *
   * @param item 目标 KB
   * @author lvdaxianerplus
   */
  function toggle(item: KnowledgeBase): void {
    if (!isPublishedKnowledgeBase(item)) {
      return;
    }
    if (value.includes(item.id)) {
      onChange(value.filter((id) => id !== item.id));
      return;
    }
    onChange([...value, item.id]);
  }

  return (
    <section className="relative">
      {/* 折叠态：摘要 + 展开触发器 */}
      <button
        aria-expanded={isExpanded}
        className="grid w-full min-h-[52px] grid-cols-[1fr_auto] items-center gap-3 rounded-lg border border-slate-200 bg-white px-3 py-2 text-left text-sm text-slate-900 transition-all duration-150 hover:border-slate-300 hover:shadow-sm focus-visible:border-emerald-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500"
        type="button"
        onClick={() => setIsExpanded((current) => !current)}
      >
        <span>
          <strong className="block text-sm font-medium">知识库范围</strong>
          <small className="mt-0.5 block text-xs text-slate-500">
            已选 {selectedItems.length} 个 · 可用 {publishedCount} 个
          </small>
        </span>
        <em className="max-w-[280px] truncate text-xs not-italic text-emerald-700">
          {selectedSummary}
          {overflowCount > 0 ? ` 等 ${selectedItems.length} 个` : ""}
        </em>
      </button>
      {/* 展开态：搜索 + 列表 + 关闭按钮 */}
      {isExpanded ? (
        <div className="absolute left-0 right-0 top-[calc(100%+4px)] z-10 grid gap-2 rounded-lg border border-slate-200 bg-white p-3 shadow-lg shadow-slate-900/10 ring-1 ring-slate-900/5">
          {/* 搜索框 */}
          <div className="grid gap-1.5">
            <span className="text-xs font-medium text-slate-900">搜索知识库</span>
            <input
              aria-label="搜索知识库"
              className="h-8 rounded-md border border-slate-200 bg-white px-2.5 text-sm transition-colors focus-visible:border-emerald-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500"
              placeholder="按名称过滤"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
          </div>
          {/* 列表：按不可用状态灰显已下架 KB */}
          <div className="grid max-h-56 gap-1 overflow-auto pr-0.5">
            {filteredItems.length > 0 ? (
              filteredItems.map((item) => (
                <label
                  className="grid cursor-pointer grid-cols-[auto_1fr] items-start gap-2.5 rounded-md border border-transparent p-2 transition-colors hover:border-slate-200 hover:bg-slate-50"
                  key={item.id}
                >
                  <input
                    aria-label={item.name}
                    checked={value.includes(item.id)}
                    className="mt-1 size-4 accent-emerald-600"
                    disabled={!isPublishedKnowledgeBase(item)}
                    type="checkbox"
                    onChange={() => toggle(item)}
                  />
                  <span>
                    <strong className="block text-sm font-medium text-slate-900">{item.name}</strong>
                    <small className="mt-0.5 block text-xs text-slate-500">
                      {isPublishedKnowledgeBase(item) ? "已发布，可用于聊天" : `${item.name}不可用于聊天`}
                    </small>
                  </span>
                </label>
              ))
            ) : (
              <span className="text-sm text-slate-500">没有匹配的知识库</span>
            )}
          </div>
          <button
            className="h-7 w-fit rounded-md border border-slate-200 bg-white px-2.5 text-xs text-slate-700 transition-colors hover:border-slate-300 hover:bg-slate-50"
            type="button"
            onClick={() => setIsExpanded(false)}
          >
            收起知识库范围
          </button>
        </div>
      ) : null}
    </section>
  );
}
