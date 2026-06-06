/**
 * Recall · 通用状态徽章（KB 状态枚举版）
 *
 * 与 `recall/StatusBadge`（变体驱动）不同，本组件只接受 KB 状态字符串，
 * 内部走策略映射（status → Badge variant + 中文 label）。
 *
 * @author lvdaxianerplus
 */
import { Badge } from "../ui/badge";
import { KB_STATUS_LABELS, KB_STATUS_TO_BADGE } from "../../features/chat/runtime/chatConstants";

/**
 * StatusBadge props 集合。
 *
 * @author lvdaxianerplus
 */
export interface StatusBadgeProps {
  /** KB 状态字符串（"published" / "active" / "draft" 等） */
  status: string;
}

/**
 * 把 status 字符串映射为 Badge variant：复用 chat runtime 下的策略映射。
 *
 * @param status KB 状态
 * @returns Badge variant
 * @author lvdaxianerplus
 */
function getStatusVariant(status: string): "default" | "secondary" | "destructive" | "outline" {
  // KB_STATUS_TO_BADGE 已经是 shadcn Badge variant 的子集，可直接断言
  return (KB_STATUS_TO_BADGE[status] as "default" | "secondary" | "destructive" | "outline") ?? "outline";
}

/**
 * KB 状态徽章组件。
 *
 * @param props.status KB 状态字符串
 * @author lvdaxianerplus
 */
export function StatusBadge({ status }: StatusBadgeProps) {
  // 1. 取中文 label：未匹配时回退到原字符串
  const label = KB_STATUS_LABELS[status] ?? status;
  // 2. 取 Badge variant
  const variant = getStatusVariant(status);

  return (
    <Badge variant={variant}>
      <span>{label}</span>
      {/* 当 label 与 status 不一致时，把原状态用 sr-only 暴露给屏幕阅读器 */}
      {label !== status ? <span className="sr-only">{status}</span> : null}
    </Badge>
  );
}
