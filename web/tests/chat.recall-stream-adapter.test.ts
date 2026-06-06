import { describe, expect, it } from "vitest";

import { applyRecallStreamEvent, createRecallRunState } from "../src/features/chat/runtime/recallStreamAdapter";

describe("recall stream adapter", () => {
  it("maps answer deltas into streamed assistant text", () => {
    const state = createRecallRunState("question");
    const next = applyRecallStreamEvent(state, {
      event: "answer.delta",
      request_id: "req-1",
      payload: { text: "负载均衡" },
    });

    expect(next.requestId).toBe("req-1");
    expect(next.content).toBe("负载均衡");
    expect(next.status).toBe("streaming");
  });

  it("maps completion results into citations and success", () => {
    const state = applyRecallStreamEvent(createRecallRunState("question"), {
      event: "answer.delta",
      request_id: "req-1",
      payload: { text: "回答" },
    });

    const next = applyRecallStreamEvent(state, {
      event: "answer.completed",
      request_id: "req-1",
      payload: { results: [{ chunk_id: "c1", document_name: "doc.md", title: "标题", content: "片段", score: 1 }] },
    });

    expect(next.status).toBe("success");
    expect(next.citations).toHaveLength(1);
    expect(next.trace).toHaveLength(2);
  });
});
