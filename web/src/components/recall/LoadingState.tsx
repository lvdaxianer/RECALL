import { Skeleton } from "@/components/ui/skeleton";

/**
 * 加载态面板 props 集合。
 *
 * @author lvdaxianerplus
 */
export interface LoadingStateProps {
  title?: string;
  label?: string;
}

/**
 * 加载态面板：显示加载文案 + Skeleton 占位。
 *
 * @param props.title 加载标题（优先级最高）
 * @param props.label 加载标签（向后兼容）
 * @author lvdaxianerplus
 */
export function LoadingState({ title, label }: LoadingStateProps) {
  const loadingText = title ?? label ?? "正在加载";

  return (
    <div aria-live="polite" className="space-y-3" role="status">
      <span className="text-sm text-muted-foreground">{loadingText}</span>
      <Skeleton className="h-24 w-full" />
    </div>
  );
}
