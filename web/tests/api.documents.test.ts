import { describe, expect, it, vi } from "vitest";

import { listDocuments } from "../src/api/documents";

describe("documents api", () => {
  it("preserves document parse status fields", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(JSON.stringify({
          data: [
            {
              id: "doc-001",
              knowledge_base_id: "kb-001",
              document_name: "broken.md",
              content_type: "text/markdown",
              status: "failed",
              chunk_count: 0,
              parse_status: "failed",
              parse_attempts: 3,
              parse_error: "parse exploded",
              queued_at: "2026-06-05T00:00:00Z",
              processing_started_at: "2026-06-05T00:00:01Z",
              parsed_at: null,
              indexed_at: null,
            },
          ],
        })),
      ),
    );

    const documents = await listDocuments("kb-001");

    expect(documents[0].parse_status).toBe("failed");
    expect(documents[0].parse_attempts).toBe(3);
    expect(documents[0].parse_error).toBe("parse exploded");
    expect(documents[0].chunk_count).toBe(0);

    vi.unstubAllGlobals();
  });
});
