interface StreamingResultPanelProps {
  output: string;
  status: string;
  durationMs?: number;
}

export function StreamingResultPanel({ output, status, durationMs }: StreamingResultPanelProps) {
  return (
    <div className="stream-panel">
      <div className="panel-heading">
        <h3>流式输出</h3>
        <span>{durationMs !== undefined ? `${status} · 耗时 ${formatDuration(durationMs)}` : status}</span>
      </div>
      <pre>{output || "等待检索输出"}</pre>
    </div>
  );
}

function formatDuration(durationMs: number): string {
  if (durationMs >= 1000) {
    return `${(durationMs / 1000).toFixed(2)}s`;
  }
  return `${Math.max(0, Math.round(durationMs))}ms`;
}
