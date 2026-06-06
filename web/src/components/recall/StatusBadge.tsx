/**
 * Recall · 状态徽章
 *
 * 用于 KB 索引、文档摄取、任务等所有"状态型"标识。
 * v1.1 设计：22px 高、4px 圆角、6px 圆点 + 文字。颜色按"语义"区分，不与品牌色绑定。
 *
 * @author lvdaxianerplus
 */
import type { ReactNode } from "react";
import { cn } from "../../lib/utils";

/**
 * 状态徽章的视觉变体（用语义词而非颜色命名）。
 *
 * @author lvdaxianerplus
 */
export type StatusBadgeVariant =
  | "ready"
  | "indexing"
  | "paused"
  | "error"
  | "warning"
  | "info"
  | "neutral";

/**
 * StatusBadge props 集合。
 *
 * @author lvdaxianerplus
 */
interface StatusBadgeProps {
  /** 视觉变体（决定配色 + 是否脉冲） */
  variant: StatusBadgeVariant;
  /** 徽章内容（通常是状态文本） */
  children: ReactNode;
  /** 额外的 className（用于局部覆盖样式） */
  className?: string;
}

/**
 * variant → 容器配色 + 边框 / ring 样式映射。
 * 集中维护避免散落硬编码 Tailwind 类。
 *
 * @author lvdaxianerplus
 */
const VARIANT_CLASS: Record<StatusBadgeVariant, string> = {
  // 成功 / 兼容可用
  ready:    "bg-emerald-50 text-emerald-700 ring-1 ring-inset ring-emerald-600/20",
  // 进行中（indexing 配 animate-pulse）
  indexing: "bg-sky-50 text-sky-700 ring-1 ring-inset ring-sky-600/20",
  // 暂停 / 归档
  paused:   "bg-amber-50 text-amber-700 ring-1 ring-inset ring-amber-600/20",
  // 失败
  error:    "bg-red-50 text-red-700 ring-1 ring-inset ring-red-600/20",
  // 警告（与 paused 配色一致但语义不同）
  warning:  "bg-amber-50 text-amber-700 ring-1 ring-inset ring-amber-600/20",
  // 通知
  info:     "bg-sky-50 text-sky-700 ring-1 ring-inset ring-sky-600/20",
  // 中性 / 未知
  neutral:  "bg-slate-100 text-slate-600 ring-1 ring-inset ring-slate-200",
};

/**
 * variant → 小圆点颜色映射（indexing 会额外加 animate-pulse）。
 *
 * @author lvdaxianerplus
 */
const DOT_CLASS: Record<StatusBadgeVariant, string> = {
  ready:    "bg-emerald-500",
  indexing: "bg-sky-500 animate-pulse",
  paused:   "bg-amber-500",
  error:    "bg-red-500",
  warning:  "bg-amber-500",
  info:     "bg-sky-500",
  neutral:  "bg-slate-400",
};

/**
 * 状态徽章组件。
 *
 * @param props.variant 视觉变体
 * @param props.children 徽章内容
 * @param props.className 额外的 className
 * @author lvdaxianerplus
 */
export function StatusBadge({ variant, children, className }: StatusBadgeProps) {
  return (
    <span
      className={cn(
        // 基础：22px 高、内联、圆点 + 文字
        "inline-flex h-[22px] items-center gap-1.5 rounded px-2 text-xs font-medium",
        VARIANT_CLASS[variant],
        className,
      )}
    >
      <span aria-hidden="true" className={cn("size-1.5 shrink-0 rounded-full", DOT_CLASS[variant])} />
      {children}
    </span>
  );
}
