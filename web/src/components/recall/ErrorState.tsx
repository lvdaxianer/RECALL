import { AlertCircle } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";

/**
 * 错误态面板 props 集合。
 *
 * @author lvdaxianerplus
 */
export interface ErrorStateProps {
  title: string;
  description?: string;
  onRetry?: () => void;
}

/**
 * 错误态面板：使用 shadcn Alert 显示错误，可选带重试按钮。
 *
 * @param props.title 错误标题
 * @param props.description 错误描述（可选）
 * @param props.onRetry 重试回调（可选）
 * @author lvdaxianerplus
 */
export function ErrorState({ title, description, onRetry }: ErrorStateProps) {
  return (
    <Alert variant="destructive">
      <AlertCircle className="h-4 w-4" />
      <AlertTitle>{title}</AlertTitle>
      {description ? <AlertDescription>{description}</AlertDescription> : null}
      {onRetry ? (
        <Button className="mt-3" size="sm" type="button" variant="secondary" onClick={onRetry}>
          重试
        </Button>
      ) : null}
    </Alert>
  );
}
