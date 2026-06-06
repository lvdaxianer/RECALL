/**
 * Recall · 流式检索结果面板
 *
 * 检索控制台 / 评测页复用的输出展示组件。
 * 支持 streaming / success / error 三种状态徽章、耗时格式化、可选 Skeleton 占位。
 *
 * @author lvdaxianerplus
 */
import { Badge } from "../ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "../ui/card";
import { ScrollArea } from "../ui/scroll-area";
import { Skeleton } from "../ui/skeleton";
import { cn } from "../../lib/utils";

/**
 * 流式检索结果面板 props 集合。
 *
 * @author lvdaxianerplus
 */
export interface RetrievalResultProps {
  /** 累积输出文本 */
  output: string;
  /** 当前状态（streaming / success / error） */
  status: string;
  /** 耗时（毫秒），可选 */
  durationMs?: number;
}

/**
 * status → Badge variant 映射（策略模式替代 if-else 链）。
 *
 * @author lvdaxianerplus
 */
const STATUS_BADGE: Record<string, "destructive" | "secondary" | "outline"> = {
  // 错误：红色
  error: "destructive",
  // 流式中：灰色（次要）+ 暗示等待
  streaming: "secondary",
  // 成功：轮廓 + 文本，无背景色，避免视觉抢镜
  success: "outline",
};

/**
 * 把毫秒格式化为 `s/ms` 字符串。
 *
 * @param durationMs 毫秒数
 * @returns 形如 `1.23s` 或 `120ms`
 * @author lvdaxianerplus
 */
function formatDuration(durationMs: number): string {
  if (durationMs >= 1000) {
    return `${(durationMs / 1000).toFixed(2)}s`;
  }
  return `${Math.max(0, Math.round(durationMs))}ms`;
}

/**
 * 流式检索结果面板。
 *
 * @param props.output 累积输出文本
 * @param props.status 当前状态（streaming / success / error）
 * @param props.durationMs 耗时（毫秒），可选
 * @author lvdaxianerplus
 */
export function RetrievalResult({ output, status, durationMs }: RetrievalResultProps) {
  // 1. 状态分支变量（避免在 JSX 中重复计算）
  const isStreaming = status === "streaming";
  const isError = status === "error";
  // 2. 状态徽章文本：完成时附带耗时，等待时仅状态名
  const statusText = durationMs !== undefined ? `${status} · 耗时 ${formatDuration(durationMs)}` : status;

  return (
    <Card className="rounded-lg">
      <CardHeader className="gap-2">
        <div className="flex items-center justify-between gap-3">
          <CardTitle className="text-base">流式输出</CardTitle>
          <Badge variant={STATUS_BADGE[status] ?? "outline"}>{statusText}</Badge>
        </div>
      </CardHeader>
      <CardContent>
        {/* aria-live="polite" 让屏幕阅读器在内容变化时播报 */}
        <div
          aria-label="流式回答状态"
          aria-live="polite"
          className="grid gap-3"
          role="status"
        >
          {/* 流式但还没输出时显示 Skeleton 占位 */}
          {isStreaming && !output ? <Skeleton className="h-24 w-full" /> : null}
          <ScrollArea className="max-h-[360px] rounded-md border bg-muted/30">
            <pre className={cn("min-h-32 whitespace-pre-wrap p-4 text-sm leading-7 text-foreground")}>
              {/* 空态：streaming 时告知"等待中"，否则静态等待 */}
              {output || (isStreaming ? "正在等待首个回答片段" : "等待检索输出")}
            </pre>
          </ScrollArea>
        </div>
      </CardContent>
    </Card>
  );
}
