import { describe, expect, it, vi } from "vitest";

import { appendStreamEvent, parseSseBlocks, readRetrievalStream } from "../src/hooks/useRetrievalStream";

describe("appendStreamEvent", () => {
  it("keeps streaming deltas and completion state", () => {
    const first = appendStreamEvent(undefined, { event: "answer.delta", payload: { text: "A" } });
    const second = appendStreamEvent(first, { event: "answer.completed", payload: { result_count: 1 } });

    expect(second.status).toBe("success");
    expect(second.output).toBe("A");
    expect(second.events).toHaveLength(2);
  });

  it("keeps progress events in streaming state before answer deltas arrive", () => {
    const state = appendStreamEvent(undefined, {
      event: "retrieval.progress",
      payload: { summary: "正在分析问题类型和检索范围" },
    });

    expect(state.status).toBe("streaming");
    expect(state.output).toBe("");
    expect(state.events).toHaveLength(1);
  });

  it("uses browser wall-clock duration instead of backend cached duration", () => {
    const nowSpy = vi.spyOn(Date, "now").mockReturnValue(1420);

    const state = appendStreamEvent(
      { status: "streaming", output: "A", events: [], startedAt: 1000 },
      { event: "answer.completed", payload: { duration_ms: 999 } },
    );

    expect(state.durationMs).toBe(420);
    nowSpy.mockRestore();
  });

  it("parses SSE text blocks", () => {
    const events = parseSseBlocks(
      'event: answer.delta\ndata: {"payload":{"text":"A"}}\n\n' +
        'event: answer.completed\ndata: {"payload":{"result_count":1}}\n\n',
    );

    expect(events[0].event).toBe("answer.delta");
    expect(events[0].payload.text).toBe("A");
  });

  it("reads retrieval stream through fetch", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response('event: answer.delta\ndata: {"payload":{"text":"A"}}\n\n')),
    );

    const events = await readRetrievalStream({
      input: "检索",
      knowledge_base_ids: ["kb-001"],
      top_k: 5,
      temperature: 0.2,
    });

    expect(events[0].event).toBe("answer.delta");
    expect(fetch).toHaveBeenCalledWith(
      "/api/v1/retrieval/search/stream",
      expect.objectContaining({
        body: expect.stringContaining('"temperature":0.2'),
      }),
    );
    vi.unstubAllGlobals();
  });
});
