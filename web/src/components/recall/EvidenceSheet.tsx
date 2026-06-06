/**
 * Recall · 证据与 Trace 弹层（Sheet 版）
 *
 * 引用与 Trace 拆到两个 Tab，避免在窄屏被挤成一列。
 * 与 `EvidencePanel`（行内版）共享 `traceAdapters` 的解析逻辑，避免重复。
 *
 * 设计要点：
 * 1. 自定义 ESC 关闭：先 preventDefault 再回调，避免冒泡到外层 dialog
 * 2. modal={false} 让 Sheet 不抢占焦点，允许用户继续操作背景
 * 3. 引用 Tab 末尾再附 trace 摘要，方便不切 Tab 也能预览阶段
 * 4. Trace Tab 走完整时间线 + 摘要卡片
 * 5. 引用表格 key 用 chunk_id 兜底文档名 + 索引，避免冲突
 * 6. 引用为空时合并单元格展示"暂无引用"
 * 7. 内容滚动用 ScrollArea 限制 70vh，避免抽屉内出现双滚动
 *
 * @author lvdaxianerplus
 */
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { TraceTimeline } from "./TraceTimeline";
// 复用 chat runtime 下的公共 trace/citation 解析器，文档其他副本不应重复实现
import { extractCitations, extractTraceSummaries, formatScore } from "../../features/chat/runtime/traceAdapters";

/**
 * 证据 Sheet props 集合。
 *
 * @author lvdaxianerplus
 */
export interface EvidenceSheetProps {
  /** 是否打开 */
  open: boolean;
  /** 打开状态变化回调 */
  onOpenChange: (open: boolean) => void;
  /** 事件流（兼容 AgentEvent / StreamEvent） */
  events: ReadonlyArray<{ event: string; payload?: Record<string, unknown> }>;
}

/**
 * 证据 Sheet 组件。
 *
 * @param props.open 是否打开
 * @param props.onOpenChange 打开状态变化回调
 * @param props.events 事件流
 * @author lvdaxianerplus
 */
export function EvidenceSheet({ open, onOpenChange, events }: EvidenceSheetProps) {
  // 1. 提前解析两个 Tab 共用的数据，避免渲染期多次重复遍历
  const citations = extractCitations(events);
  const traceItems = extractTraceSummaries(events);

  return (
    <Sheet modal={false} open={open} onOpenChange={onOpenChange}>
      <SheetContent
        className="w-full sm:max-w-2xl"
        // 自定义 ESC 关闭：先阻止默认行为再回调，避免冒泡到外层 dialog
        onEscapeKeyDown={(event) => {
          event.preventDefault();
          onOpenChange(false);
        }}
      >
        <SheetHeader>
          <SheetTitle>证据与 Trace</SheetTitle>
          <SheetDescription>查看回答引用、检索阶段和后端事件摘要。</SheetDescription>
        </SheetHeader>
        <Tabs className="mt-4" defaultValue="citations">
          <TabsList>
            <TabsTrigger value="citations">引用</TabsTrigger>
            <TabsTrigger value="trace">Trace</TabsTrigger>
          </TabsList>
          {/* 引用 Tab：紧凑表格 + 下方 trace 摘要小卡片 */}
          <TabsContent value="citations">
            <ScrollArea className="h-[70vh] pr-3">
              <strong className="mb-3 block text-sm font-semibold">引用来源</strong>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>文档</TableHead>
                    <TableHead>标题</TableHead>
                    <TableHead>片段</TableHead>
                    <TableHead>分数</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {citations.length > 0 ? (
                    // key 用 chunk_id 或文档名兜底，确保多条相同标题也不会冲突
                    citations.map((citation, index) => (
                      <TableRow key={`${citation.chunk_id ?? citation.document_name}-${index}`}>
                        <TableCell className="font-medium">{citation.document_name}</TableCell>
                        <TableCell>{citation.title}</TableCell>
                        <TableCell>{citation.content}</TableCell>
                        <TableCell className="font-mono text-xs">{formatScore(citation.score)}</TableCell>
                      </TableRow>
                    ))
                  ) : (
                    <TableRow>
                      <TableCell className="text-muted-foreground" colSpan={4}>
                        暂无引用
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
              {/* 引用 Tab 末尾：再附上 trace 摘要，方便快速预览阶段 */}
              {traceItems.length > 0 ? (
                <div className="mt-4 space-y-2">
                  {traceItems.map((item, index) => (
                    <div className="rounded-md border border-border p-3" key={`${item.title}-summary-${index}`}>
                      <strong className="block text-sm text-foreground">{item.title}</strong>
                      <span className="block text-sm text-muted-foreground">{item.summary}</span>
                      {item.meta ? <small className="font-mono text-xs text-muted-foreground">{item.meta}</small> : null}
                    </div>
                  ))}
                </div>
              ) : null}
            </ScrollArea>
          </TabsContent>
          {/* Trace Tab：完整时间线 + 摘要卡片 */}
          <TabsContent value="trace">
            <ScrollArea className="h-[70vh] pr-3">
              {traceItems.length > 0 ? (
                <div className="mb-4 space-y-2">
                  {traceItems.map((item, index) => (
                    <div className="rounded-md border border-border p-3" key={`${item.title}-${index}`}>
                      <strong className="block text-sm text-foreground">{item.title}</strong>
                      <span className="block text-sm text-muted-foreground">{item.summary}</span>
                      {item.meta ? <small className="font-mono text-xs text-muted-foreground">{item.meta}</small> : null}
                    </div>
                  ))}
                </div>
              ) : null}
              <TraceTimeline events={events} />
            </ScrollArea>
          </TabsContent>
        </Tabs>
      </SheetContent>
    </Sheet>
  );
}
