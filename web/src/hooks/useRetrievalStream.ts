export interface StreamEvent {
  event: string;
  request_id?: string | null;
  payload: Record<string, unknown>;
}

export interface StreamState {
  status: "idle" | "streaming" | "success" | "error";
  output: string;
  events: StreamEvent[];
  error?: string;
  startedAt?: number;
  finishedAt?: number;
  durationMs?: number;
}

export interface RetrievalStreamRequest {
  input: string;
  knowledge_base_ids: string[];
  session_id?: string;
  top_k?: number;
  use_context?: boolean;
  history_questions?: string[];
  temperature?: number;
  user_id?: string;
}

const INITIAL_STREAM_STATE: StreamState = {
  status: "idle",
  output: "",
  events: [],
};

export function appendStreamEvent(state: StreamState | undefined, event: StreamEvent): StreamState {
  const current = state ?? INITIAL_STREAM_STATE;
  const events = [...current.events, event];
  const startedAt = current.startedAt ?? Date.now();
  if (event.event === "answer.delta") {
    return {
      ...current,
      status: "streaming",
      output: `${current.output}${String(event.payload.text ?? "")}`,
      events,
      startedAt,
    };
  }
  if (event.event === "retrieval.progress" || event.event === "request.created" || event.event === "retrieval.trace") {
    return {
      ...current,
      status: "streaming",
      events,
      startedAt,
    };
  }
  if (event.event === "answer.completed") {
    const finishedAt = Date.now();
    return {
      ...current,
      status: "success",
      events,
      startedAt,
      finishedAt,
      durationMs: finishedAt - startedAt,
    };
  }
  if (event.event === "request.failed") {
    const finishedAt = Date.now();
    return {
      ...current,
      status: "error",
      error: String(event.payload.message ?? "请求失败"),
      events,
      startedAt,
      finishedAt,
      durationMs: finishedAt - startedAt,
    };
  }
  return { ...current, events, startedAt };
}

export async function readRetrievalStream(
  payload: RetrievalStreamRequest,
  onEvent?: (event: StreamEvent) => void,
): Promise<StreamEvent[]> {
  const response = await fetch("/api/v1/retrieval/search/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(await readErrorMessage(response));
  }
  if (!response.body) {
    return emitEvents(parseSseBlocks(await response.text()), onEvent);
  }
  return readStreamEvents(response.body, onEvent);
}

async function readErrorMessage(response: Response): Promise<string> {
  try {
    const payload = await response.json();
    return String(payload?.detail?.message ?? payload?.message ?? "请求失败");
  } catch {
    return "请求失败";
  }
}

export function parseSseBlocks(text: string): StreamEvent[] {
  return text
    .split("\n\n")
    .map((block) => block.trim())
    .filter(Boolean)
    .map(parseSseBlock);
}

function parseSseBlock(block: string): StreamEvent {
  const lines = block.split("\n");
  const eventLine = lines.find((line) => line.startsWith("event: "));
  const dataLine = lines.find((line) => line.startsWith("data: "));
  const parsed = dataLine ? JSON.parse(dataLine.replace("data: ", "")) : { payload: {} };
  return {
    event: eventLine ? eventLine.replace("event: ", "") : String(parsed.event ?? "message"),
    request_id: parsed.request_id ?? null,
    payload: parsed.payload ?? {},
  };
}

async function readStreamEvents(
  body: ReadableStream<Uint8Array>,
  onEvent?: (event: StreamEvent) => void,
): Promise<StreamEvent[]> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  const events: StreamEvent[] = [];
  let buffer = "";
  let isDone = false;
  while (!isDone) {
    const result = await reader.read();
    isDone = result.done;
    buffer += decoder.decode(result.value ?? new Uint8Array(), { stream: !isDone });
    const parsed = drainCompleteBlocks(buffer);
    buffer = parsed.rest;
    events.push(...emitEvents(parsed.events, onEvent));
  }
  if (buffer.trim()) {
    events.push(...emitEvents(parseSseBlocks(buffer), onEvent));
  }
  return events;
}

function drainCompleteBlocks(buffer: string): { events: StreamEvent[]; rest: string } {
  const parts = buffer.split("\n\n");
  const rest = parts.pop() ?? "";
  return {
    events: parseSseBlocks(parts.join("\n\n")),
    rest,
  };
}

function emitEvents(events: StreamEvent[], onEvent?: (event: StreamEvent) => void): StreamEvent[] {
  events.forEach((event) => onEvent?.(event));
  return events;
}
