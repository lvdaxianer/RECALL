/**
 * Recall · 顶部指标条
 *
 * 3~4 个数值卡，用于页面 hero。数字用 JetBrains Mono + tabular-nums，便于等宽对齐。
 * 布局走 auto-fit grid：列数随容器宽度自适应，避免小屏挤压。
 *
 * @author lvdaxianerplus
 */

/**
 * 单个指标条目。
 *
 * @author lvdaxianerplus
 */
interface MetricItem {
  /** 指标标签（"总量"、"命中率"等） */
  label: string;
  /** 指标值（已格式化字符串） */
  value: string;
}

/**
 * 顶部指标条 props 集合。
 *
 * @author lvdaxianerplus
 */
interface MetricStripProps {
  /** 指标条目列表（3-4 条最佳，过多会挤压） */
  items: MetricItem[];
}

/**
 * 顶部指标条组件。
 *
 * @param props.items 指标条目
 * @author lvdaxianerplus
 */
export function MetricStrip({ items }: MetricStripProps) {
  return (
    // 响应式 grid：auto-fit 配 minmax 让列数随容器宽度变化
    <div className="grid gap-3 [grid-template-columns:repeat(auto-fit,minmax(min(220px,100%),1fr))]">
      {items.map((item) => (
        <div
          key={item.label}
          className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm"
        >
          {/* 标签：uppercase + tracking-wider 让 KPI 风格更克制 */}
          <span className="text-xs font-medium uppercase tracking-wider text-slate-500">
            {item.label}
          </span>
          {/* 数值：等宽字体 + tabular-nums 保证多列数字纵向对齐 */}
          <strong className="mt-1 block font-mono text-base font-semibold tabular-nums text-slate-900">
            {item.value}
          </strong>
        </div>
      ))}
    </div>
  );
}
