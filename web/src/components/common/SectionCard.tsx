/**
 * Recall · 通用卡片容器
 *
 * 大部分业务页面的基础布局单元：title / description / actions / children。
 *
 * v1.3 设计：
 *   - 白底 + slate-200 描边 + shadow-xs（rest）
 *   - interactive 变体：hover 提升到 shadow-sm + border-slate-300 + -translate-y-0.5
 *   - 取消硬切 header/body 分隔线，靠 16px 留白分层
 *   - 左侧色条（accent）用于强调某个 section
 *
 * @author lvdaxianerplus
 */
import type { PropsWithChildren, ReactNode } from "react";

import { cn } from "../../lib/utils";

/**
 * SectionCard props 集合。
 *
 * @author lvdaxianerplus
 */
interface SectionCardProps {
  /** 卡片外层 className（用于局部覆盖） */
  className?: string;
  /** 卡片 body 区域 className */
  bodyClassName?: string;
  /** 卡片标题 */
  title?: string;
  /** 标题下方的描述文本 */
  description?: string;
  /** 标题右侧操作区（如按钮组） */
  actions?: ReactNode;
  /** 是否可点击（开启 hover 提升 + 焦点环） */
  interactive?: boolean;
  /** 左侧色条（用于强调某个 section） */
  accent?: "emerald" | "indigo" | "amber" | "red" | null;
}

/**
 * accent → 左侧色条 Tailwind 类映射（策略模式避免 if 链）。
 *
 * @author lvdaxianerplus
 */
const ACCENT_BAR: Record<NonNullable<SectionCardProps["accent"]>, string> = {
  emerald: "before:bg-emerald-500",
  indigo: "before:bg-indigo-500",
  amber: "before:bg-amber-500",
  red: "before:bg-red-500",
};

/**
 * 通用 SectionCard 组件。
 *
 * @param props.className 卡片外层 className
 * @param props.bodyClassName body 区域 className
 * @param props.title 卡片标题
 * @param props.description 描述
 * @param props.actions 操作区
 * @param props.interactive 是否可点击
 * @param props.accent 左侧色条
 * @param props.children 卡片内容
 * @author lvdaxianerplus
 */
export function SectionCard({
  className,
  bodyClassName,
  title,
  description,
  actions,
  interactive = false,
  accent = null,
  children,
}: PropsWithChildren<SectionCardProps>) {
  // header 仅在 title 或 actions 至少一个存在时渲染
  const hasHeader = Boolean(title) || Boolean(actions);
  return (
    <section
      className={cn(
        // 基础：白底 + 描边 + 微阴影
        "relative overflow-hidden rounded-xl border border-slate-200 bg-white shadow-xs",
        "transition-all duration-200 ease-out",
        // 可点击变体：增加 hover 提升 + 焦点环
        interactive &&
          "cursor-pointer hover:-translate-y-0.5 hover:border-slate-300 hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 focus-visible:ring-offset-2 active:translate-y-0 active:shadow-sm",
        // accent 变体：在容器左侧加 4px 色条（before 伪元素实现）
        accent && "before:absolute before:inset-y-0 before:left-0 before:w-1",
        accent && ACCENT_BAR[accent],
        className,
      )}
      // interactive 模式下让整张卡片可被键盘聚焦
      tabIndex={interactive ? 0 : undefined}
    >
      {hasHeader ? (
        <header className="flex items-start gap-3 px-5 pt-5">
          <div className="min-w-0 flex-1">
            {title ? (
              <h3 className="truncate text-sm font-semibold tracking-tight text-slate-900">{title}</h3>
            ) : null}
            {description ? (
              <p className="mt-0.5 truncate text-xs text-slate-500">{description}</p>
            ) : null}
          </div>
          {actions ? (
            <div className="flex shrink-0 items-center gap-1.5">{actions}</div>
          ) : null}
        </header>
      ) : null}
      <div className={cn("p-5", bodyClassName)}>{children}</div>
    </section>
  );
}
