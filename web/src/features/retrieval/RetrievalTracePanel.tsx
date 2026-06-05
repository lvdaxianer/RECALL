interface RetrievalTracePanelProps {
  trace: Array<Record<string, unknown>>;
}

interface TraceCard {
  stage: string;
  summary: string;
  metrics: string[];
}

export function RetrievalTracePanel({ trace }: RetrievalTracePanelProps) {
  const cards = buildTraceCards(trace);
  return (
    <div className="trace-panel">
      <h3>Trace</h3>
      {cards.length > 0 ? (
        <div className="trace-markdown-list">
          {cards.map((item, index) => (
            <article className="trace-markdown-card" key={`${item.stage}-${index}`}>
              <h4>{item.stage}</h4>
              <p>{item.summary}</p>
              {item.metrics.length > 0 ? (
                <ul>
                  {item.metrics.map((metric) => <li key={metric}>{metric}</li>)}
                </ul>
              ) : null}
            </article>
          ))}
        </div>
      ) : <span className="muted-text">暂无 trace</span>}
    </div>
  );
}

function buildTraceCards(trace: Array<Record<string, unknown>>): TraceCard[] {
  return trace.flatMap((event) => {
    const payload = event.payload as { trace?: unknown[]; duration_ms?: unknown; stage_durations_ms?: unknown } | undefined;
    const nestedTrace = Array.isArray(payload?.trace) ? payload.trace : [];
    const traceCards = nestedTrace.map((item) => normalizeTraceItem(item));
    if (event.event === "answer.completed" && payload?.duration_ms !== undefined) {
      traceCards.push({
        stage: "answer.completed",
        summary: "回答生成完成",
        metrics: [
          `duration_ms: ${payload.duration_ms}`,
          ...formatStageDurations(payload.stage_durations_ms),
        ],
      });
    }
    return traceCards;
  });
}

function normalizeTraceItem(item: unknown): TraceCard {
  const trace = item as { stage?: unknown; summary?: unknown; metrics?: Record<string, unknown> };
  return {
    stage: String(trace.stage ?? "trace"),
    summary: String(trace.summary ?? "已记录检索阶段"),
    metrics: formatMetrics(trace.metrics ?? {}),
  };
}

function formatMetrics(metrics: Record<string, unknown>): string[] {
  return ["query_scope", "route_plan", "strategy", "result_count", "duration_ms"]
    .filter((key) => metrics[key] !== undefined)
    .map((key) => `${key}: ${formatMetricValue(metrics[key])}`);
}

function formatStageDurations(value: unknown): string[] {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return [];
  }
  return Object.entries(value as Record<string, unknown>).map(
    ([key, duration]) => `${key}: ${formatMetricValue(duration)}`,
  );
}

function formatMetricValue(value: unknown): string {
  if (Array.isArray(value)) {
    return value.map(String).join(", ");
  }
  if (typeof value === "object" && value !== null) {
    return Object.entries(value as Record<string, unknown>)
      .slice(0, 3)
      .map(([key, nestedValue]) => `${key}=${formatMetricValue(nestedValue)}`)
      .join(", ");
  }
  return String(value);
}
