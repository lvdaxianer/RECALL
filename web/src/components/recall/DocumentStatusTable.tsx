/**
 * Recall · 文档解析状态表
 *
 * 紧凑展示 KB 下的文档列表，列出文档名 / 解析状态 / chunk 数 / 操作按钮。
 * 解析状态走 chat runtime 下的 `PARSE_STATUS_TO_BADGE` 策略映射，避免硬编码 if 链。
 *
 * @author lvdaxianerplus
 */
import { FileText, Settings, SplitSquareHorizontal } from "lucide-react";

// 文档 / chunk 数据模型来源（types 走 api/documents）
import type { KnowledgeDocument } from "../../api/documents";
import { cn } from "../../lib/utils";
import {
  PARSE_STATUS,
  PARSE_STATUS_LABELS,
  PARSE_STATUS_TO_BADGE,
  type ParseStatus,
} from "../../features/chat/runtime/chatConstants";
import { Badge } from "../ui/badge";
import { Button } from "../ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "../ui/table";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "../ui/tooltip";

/**
 * 文档状态表 props 集合。
 *
 * @author lvdaxianerplus
 */
export interface DocumentStatusTableProps {
  /** 文档列表 */
  documents: KnowledgeDocument[];
  /** 当前选中文档 id（用于高亮） */
  selectedDocumentId?: string;
  /** 打开 chunk 明细回调 */
  onOpenChunks: (document: KnowledgeDocument) => void;
  /** 打开分块配置回调 */
  onOpenConfig: (document: KnowledgeDocument) => void;
}

/**
 * 把任意字符串归一化为已知 ParseStatus（缺省按 indexed 处理）。
 *
 * @param document 知识库文档
 * @returns 归一化后的解析状态
 * @author lvdaxianerplus
 */
function getParseStatus(document: KnowledgeDocument): ParseStatus {
  // 仅在枚举已知值时返回，否则兜底为 indexed（最常见的"已就绪"状态）
  const status = document.parse_status;
  if (status && status in PARSE_STATUS_LABELS) {
    return status as ParseStatus;
  }
  return PARSE_STATUS.INDEXED;
}

/**
 * 文档解析状态表。
 *
 * @param props.documents 文档列表
 * @param props.selectedDocumentId 当前选中文档 id
 * @param props.onOpenChunks 打开 chunk 列表回调
 * @param props.onOpenConfig 打开分块配置回调
 * @author lvdaxianerplus
 */
export function DocumentStatusTable({
  documents,
  selectedDocumentId,
  onOpenChunks,
  onOpenConfig,
}: DocumentStatusTableProps) {
  return (
    // TooltipProvider 包整张表，让所有行的 Tooltip 共享同一个 context
    <TooltipProvider>
      <Table aria-label="文档解析状态">
        <TableHeader>
          <TableRow>
            <TableHead>文档</TableHead>
            <TableHead>解析状态</TableHead>
            <TableHead>Chunk</TableHead>
            <TableHead className="text-right">操作</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {documents.map((document) => {
            const parseStatus = getParseStatus(document);
            // 高亮当前选中行，便于用户感知当前操作对象
            const isSelected = document.id === selectedDocumentId;

            return (
              <TableRow className={cn(isSelected && "bg-muted/50")} key={document.id}>
                <TableCell className="max-w-[280px] whitespace-normal">
                  <div className="flex min-w-0 items-start gap-2">
                    <FileText aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
                    <div className="min-w-0 space-y-1">
                      <strong className="block break-words text-sm font-medium">
                        {document.document_name}
                      </strong>
                      <span className="block text-xs text-muted-foreground">
                        {document.content_type ?? "text/markdown"} · {document.status}
                      </span>
                      {/* 解析失败时展示错误摘要，红色提示 */}
                      {document.parse_error ? (
                        <span className="block break-words text-xs text-destructive">
                          {document.parse_error}
                        </span>
                      ) : null}
                    </div>
                  </div>
                </TableCell>
                <TableCell>
                  <Badge variant={PARSE_STATUS_TO_BADGE[parseStatus] ?? "outline"}>
                    {PARSE_STATUS_LABELS[parseStatus] ?? parseStatus}
                  </Badge>
                </TableCell>
                <TableCell className="text-muted-foreground">
                  {document.chunk_count} chunks
                </TableCell>
                <TableCell>
                  <div className="flex justify-end gap-2">
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <Button
                          aria-label={`查看 ${document.document_name} 的 Chunk`}
                          size="icon-sm"
                          type="button"
                          variant="ghost"
                          onClick={() => onOpenChunks(document)}
                        >
                          <SplitSquareHorizontal aria-hidden="true" className="h-4 w-4" />
                        </Button>
                      </TooltipTrigger>
                      <TooltipContent>查看 Chunk</TooltipContent>
                    </Tooltip>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <Button
                          aria-label={`查看 ${document.document_name} 的分块配置`}
                          size="icon-sm"
                          type="button"
                          variant="ghost"
                          onClick={() => onOpenConfig(document)}
                        >
                          <Settings aria-hidden="true" className="h-4 w-4" />
                        </Button>
                      </TooltipTrigger>
                      <TooltipContent>查看配置</TooltipContent>
                    </Tooltip>
                  </div>
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </TooltipProvider>
  );
}
