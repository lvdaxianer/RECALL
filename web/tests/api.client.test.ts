import { describe, expect, it, vi } from "vitest";

import { requestJson } from "../src/api/client";
import { KnowledgeBaseStatus } from "../src/api/types";

describe("requestJson", () => {
  it("throws a typed error on non-200 responses", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify({ message: "bad" }), { status: 500 })),
    );

    await expect(requestJson("/api/v1/kb", { method: "GET" })).rejects.toThrow("请求失败");

    vi.unstubAllGlobals();
  });

  it("defines stable knowledge base status values", () => {
    expect(KnowledgeBaseStatus.Active).toBe("active");
    expect(KnowledgeBaseStatus.Deleted).toBe("deleted");
  });
});
