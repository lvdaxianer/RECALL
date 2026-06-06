/**
 * Recall · 页面页眉
 *
 * 由三段组成：eyebrow（小标签） · 标题 · 描述 · 右侧操作区。
 * v1.2 设计：去掉粗分割线，靠 16px 留白分层；标题 tracking-tight 更克制。
 *
 * @author lvdaxianerplus
 */
import type { ReactNode } from "react";

/**
 * 页面页眉 props 集合。
 *
 * @author lvdaxianerplus
 */
interface PageHeaderProps {
  /** eyebrow 小标签（如 "Retrieval Architecture"） */
  eyebrow: string;
  /** 主标题 */
  title: string;
  /** 描述文本（可省略） */
  description: string;
  /** 右侧操作区（如按钮组） */
  actions?: ReactNode;
}

/**
 * 页面页眉组件。
 *
 * @param props.eyebrow 小标签
 * @param props.title 主标题
 * @param props.description 描述文本
 * @param props.actions 右侧操作区
 * @author lvdaxianerplus
 */
export function PageHeader({ eyebrow, title, description, actions }: PageHeaderProps) {
  return (
    // 在小屏纵向堆叠，md+ 横向排列（标题在左、操作在右）
    <section className="flex flex-col gap-4 rounded-xl border border-slate-200 bg-white px-6 py-5 shadow-xs md:flex-row md:items-start md:justify-between">
      <div className="min-w-0 space-y-1.5">
        {/* eyebrow 用 emerald + uppercase 区分于普通正文 */}
        <span className="text-[11px] font-semibold uppercase tracking-wider text-emerald-600">
          {eyebrow}
        </span>
        <h1 className="text-[22px] font-semibold leading-tight tracking-tight text-slate-900">
          {title}
        </h1>
        <p className="max-w-3xl text-sm leading-relaxed text-slate-500">{description}</p>
      </div>
      {/* 仅当传入 actions 时渲染操作区；用 null 而非空 fragment 节省 DOM 节点 */}
      {actions ? (
        <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>
      ) : null}
    </section>
  );
}
