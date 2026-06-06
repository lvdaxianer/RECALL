import { Card, CardContent } from "@/components/ui/card";

/**
 * 空态面板 props 集合。
 *
 * @author lvdaxianerplus
 */
export interface EmptyStateProps {
  title: string;
  description?: string;
}

/**
 * 空态面板：dashed 卡片 + 居中标题/描述。
 *
 * @param props.title 标题
 * @param props.description 描述（可选）
 * @author lvdaxianerplus
 */
export function EmptyState({ title, description }: EmptyStateProps) {
  return (
    <Card className="border-dashed">
      <CardContent className="flex min-h-36 flex-col items-center justify-center gap-2 p-6 text-center">
        <h2 className="text-sm font-semibold text-foreground">{title}</h2>
        {description ? (
          <p className="max-w-md text-sm text-muted-foreground">{description}</p>
        ) : null}
      </CardContent>
    </Card>
  );
}
