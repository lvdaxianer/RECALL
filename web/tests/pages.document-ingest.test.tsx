import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { DocumentIngestPage } from "../src/features/documents/DocumentIngestPage";

describe("DocumentIngestPage", () => {
  it("shows document parse status and failure reason", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        if (url === "/api/v1/kb") {
          return new Response(JSON.stringify({
            data: [
              {
                id: "kb-001",
                name: "产品知识库",
                description: "产品资料",
                owner_id: "u1",
                status: "published",
              },
            ],
          }));
        }
        if (url === "/api/v1/kb/kb-001/documents") {
          return new Response(JSON.stringify({
            data: [
              {
                id: "doc-001",
                knowledge_base_id: "kb-001",
                document_name: "a.md",
                content_type: "text/markdown",
                status: "failed",
                chunk_count: 0,
                parse_status: "failed",
                parse_attempts: 3,
                parse_error: "parse exploded",
              },
            ],
          }));
        }
        return new Response(JSON.stringify({ data: [] }));
      }),
    );

    render(<DocumentIngestPage />);

    expect(await screen.findByText("文档解析状态")).toBeInTheDocument();
    expect(await screen.findByText("a.md")).toBeInTheDocument();
    expect(screen.getByText("失败")).toBeInTheDocument();
    expect(screen.getByText("3/3 次")).toBeInTheDocument();
    expect(screen.getByText("parse exploded")).toBeInTheDocument();

    vi.unstubAllGlobals();
  });
});
