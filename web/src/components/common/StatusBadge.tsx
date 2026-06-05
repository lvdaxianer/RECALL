interface StatusBadgeProps {
  status: string;
}

const STATUS_LABELS: Record<string, string> = {
  active: "兼容可用",
  deleted: "已删除",
  draft: "草稿",
  changed: "有未发布变更",
  publishing: "发布中",
  published: "已发布",
  publish_failed: "发布失败",
  archived: "已归档",
};

export function StatusBadge({ status }: StatusBadgeProps) {
  const label = STATUS_LABELS[status] ?? status;
  return (
    <span className={`status-badge status-badge--${status}`}>
      <span>{label}</span>
      {label !== status ? <span className="sr-only">{status}</span> : null}
    </span>
  );
}
