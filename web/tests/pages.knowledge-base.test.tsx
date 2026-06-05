import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { KnowledgeBaseDetailPage } from "../src/features/kb/KnowledgeBaseDetailPage";
import { KnowledgeBaseListPage } from "../src/features/kb/KnowledgeBaseListPage";

describe("knowledge base pages", () => {
  it("renders list controls", () => {
    render(<KnowledgeBaseListPage />);

    expect(screen.getByText("知识库")).toBeInTheDocument();
    expect(screen.getByText("创建知识库")).toBeInTheDocument();
    expect(screen.getByText("刷新")).toBeInTheDocument();
  });

  it("shows release status in the knowledge base list", async () => {
    const longKbId = "kb_da1f16b8a81b428aa8d1fcaeb52bfc7f";
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(JSON.stringify({
          data: [
            {
              id: longKbId,
              name: "产品知识库",
              description: "产品资料",
              owner_id: "u1",
              status: "published",
            },
            {
              id: "kb-002",
              name: "研发草稿库",
              description: "内部草稿",
              owner_id: "u1",
              status: "changed",
            },
          ],
        })),
      ),
    );

    render(<KnowledgeBaseListPage />);

    expect(await screen.findByText("产品知识库")).toBeInTheDocument();
    expect(screen.getByText("知识资产概览")).toBeInTheDocument();
    expect(screen.getByText("2 个知识库")).toBeInTheDocument();
    expect(screen.getByText("1 个已发布")).toBeInTheDocument();
    expect(screen.getByText("1 个待发版")).toBeInTheDocument();
    expect(screen.getByText("已发布")).toBeInTheDocument();
    expect(screen.getByText("有未发布变更")).toBeInTheDocument();
    expect(screen.getAllByText("发版状态").length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: "查看文档 产品知识库" })).toBeInTheDocument();
    expect(screen.queryByText("选择知识库查看文档")).not.toBeInTheDocument();
    expect(screen.queryByText(longKbId)).not.toBeInTheDocument();
    vi.unstubAllGlobals();
  });

  it("navigates from compact knowledge base list to a document detail page", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        if (url === "/api/v1/kb") {
          return new Response(JSON.stringify({
            data: [
              { id: "kb-001", name: "产品知识库", description: "产品资料", owner_id: "u1", status: "published" },
            ],
          }));
        }
        if (url === "/api/v1/kb/kb-001/documents") {
          return new Response(JSON.stringify({ data: [] }));
        }
        return new Response(JSON.stringify({ data: [] }));
      }),
    );

    render(<KnowledgeBaseListPage />);
    fireEvent.click(await screen.findByRole("button", { name: "查看文档 产品知识库" }));

    expect(await screen.findByRole("heading", { name: "产品知识库" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "返回知识库列表" })).toBeInTheDocument();
    expect(screen.queryByText("创建知识库")).not.toBeInTheDocument();
    vi.unstubAllGlobals();
  });

  it("opens chunk settings from a knowledge base card dialog", async () => {
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (url === "/api/v1/kb/kb-001/settings" && init?.method === "PATCH") {
        return new Response(JSON.stringify({
          data: {
            knowledge_base_id: "kb-001",
            semantic_chunking_enabled: false,
            chunk_size: 1200,
            overlap: 180,
            top_k_default: 8,
            max_heading_depth: 3,
            llm_planning_timeout_ms: 8000,
            updated_at: "2026-06-05T00:00:00Z",
          },
        }));
      }
      if (url === "/api/v1/kb/kb-001/settings") {
        return new Response(JSON.stringify({
          data: {
            knowledge_base_id: "kb-001",
            semantic_chunking_enabled: false,
            chunk_size: 1000,
            overlap: 150,
            top_k_default: 5,
            max_heading_depth: 3,
            llm_planning_timeout_ms: 8000,
            updated_at: "2026-06-05T00:00:00Z",
          },
        }));
      }
      return new Response(JSON.stringify({
        data: [
          { id: "kb-001", name: "产品知识库", description: "产品资料", owner_id: "u1", status: "published" },
        ],
      }));
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<KnowledgeBaseListPage />);
    fireEvent.click(await screen.findByRole("button", { name: "设置 产品知识库" }));

    expect(await screen.findByRole("dialog", { name: "产品知识库 分块设置" })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Chunk size"), { target: { value: "1200" } });
    fireEvent.change(screen.getByLabelText("Overlap"), { target: { value: "180" } });
    fireEvent.click(screen.getByRole("button", { name: "保存分块设置" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/kb/kb-001/settings",
      expect.objectContaining({ method: "PATCH" }),
    ));
    expect(await screen.findByText("分块设置已保存")).toBeInTheDocument();
    vi.unstubAllGlobals();
  });

  it("renders detail document panels", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        if (url === "/api/v1/kb/kb-001/documents") {
          return new Response(JSON.stringify({
            data: [
              {
                id: "doc-001",
                document_name: "guide.md",
                status: "ready",
                chunk_count: 2,
                content_type: "text/markdown",
                parse_status: "indexed",
                parse_attempts: 1,
                parse_error: null,
                updated_at: "2026-06-04T00:00:00Z",
              },
              {
                id: "doc-002",
                document_name: "broken.md",
                status: "failed",
                chunk_count: 0,
                content_type: "text/markdown",
                parse_status: "failed",
                parse_attempts: 1,
                parse_error: "embedding 400",
              },
            ],
          }));
        }
        if (url === "/api/v1/kb/kb-001/documents/doc-001/chunks") {
          return new Response(JSON.stringify({
            data: [
              { id: "chunk-001", chunk_index: 0, title: "Guide", content: "第一段内容", token_count: 4 },
              { id: "chunk-002", chunk_index: 1, title: "Detail", content: "第二段内容", token_count: 4 },
            ],
          }));
        }
        return new Response(JSON.stringify({ data: [] }));
      }),
    );

    render(<KnowledgeBaseDetailPage kbId="kb-001" />);

    expect(screen.getByDisplayValue("kb-001")).toBeInTheDocument();
    expect(screen.getByText("目标知识库")).toBeInTheDocument();
    expect(screen.getByText("文档列表")).toBeInTheDocument();
    expect(screen.getByText("上传文档")).toBeInTheDocument();
    expect(screen.queryByText("分块策略")).not.toBeInTheDocument();
    expect(screen.queryByText("Chunk 明细")).not.toBeInTheDocument();
    await waitFor(() => expect(screen.getAllByText("guide.md").length).toBeGreaterThan(0));
    expect(screen.getByText("已入库")).toBeInTheDocument();
    expect(screen.getByText("失败")).toBeInTheDocument();
    expect(screen.getByText("embedding 400")).toBeInTheDocument();
    expect(screen.getAllByText("2 chunks").length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole("button", { name: "查看 guide.md 的 Chunk" }));
    expect(screen.getByRole("dialog", { name: "guide.md Chunk 明细" })).toBeInTheDocument();
    expect(await screen.findByText("Chunk #0")).toBeInTheDocument();
    expect(screen.getByText("第一段内容")).toBeInTheDocument();
    expect(screen.getByText("Chunk #1")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "查看 guide.md 的分块配置" }));
    expect(screen.getByText("分块策略")).toBeInTheDocument();
    expect(screen.getByText("按 Markdown 标题切分")).toBeInTheDocument();
    vi.unstubAllGlobals();
  });

  it("shows document chunks in a left drawer with pagination", async () => {
    const chunks = Array.from({ length: 7 }, (_, index) => ({
      id: `chunk-${index + 1}`,
      chunk_index: index,
      title: `Section ${index + 1}`,
      content: `chunk content ${index + 1}`,
      token_count: 12,
    }));
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        if (url === "/api/v1/kb/kb-001/documents") {
          return new Response(JSON.stringify({
            data: [
              {
                id: "doc-001",
                document_name: "guide.md",
                status: "ready",
                chunk_count: 7,
                content_type: "text/markdown",
              },
            ],
          }));
        }
        if (url === "/api/v1/kb/kb-001/documents/doc-001/chunks") {
          return new Response(JSON.stringify({ data: chunks }));
        }
        return new Response(JSON.stringify({ data: [] }));
      }),
    );

    render(<KnowledgeBaseDetailPage kbId="kb-001" />);

    fireEvent.click(await screen.findByRole("button", { name: "查看 guide.md 的 Chunk" }));
    expect(screen.getByRole("dialog", { name: "guide.md Chunk 明细" })).toBeInTheDocument();
    expect(await screen.findByText("Chunk #0")).toBeInTheDocument();
    expect(screen.getByText("Chunk 分页 1 / 2")).toBeInTheDocument();
    expect(screen.queryByText("Chunk #5")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "下一页 Chunk" }));
    expect(screen.getByText("Chunk #5")).toBeInTheDocument();
    expect(screen.queryByText("Chunk #0")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "关闭 Chunk 明细" }));
    expect(screen.queryByRole("dialog", { name: "guide.md Chunk 明细" })).not.toBeInTheDocument();
    vi.unstubAllGlobals();
  });

  it("paginates and filters long document lists", async () => {
    const documents = Array.from({ length: 13 }, (_, index) => ({
      id: `doc-${index + 1}`,
      document_name: `guide-${String(index + 1).padStart(2, "0")}.md`,
      status: "ready",
      chunk_count: index + 1,
      content_type: "text/markdown",
    }));
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        if (url === "/api/v1/kb/kb-001/documents") {
          return new Response(JSON.stringify({ data: documents }));
        }
        return new Response(JSON.stringify({ data: [] }));
      }),
    );

    render(<KnowledgeBaseDetailPage kbId="kb-001" />);

    await waitFor(() => expect(screen.getAllByText("guide-01.md").length).toBeGreaterThan(0));
    expect(screen.getByText("文档分页 1 / 2")).toBeInTheDocument();
    expect(screen.queryByText("guide-11.md")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "下一页文档" }));
    expect(screen.getAllByText("guide-11.md").length).toBeGreaterThan(0);
    expect(screen.queryByText("guide-01.md")).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("搜索文档"), { target: { value: "guide-13" } });
    expect(screen.getAllByText("guide-13.md").length).toBeGreaterThan(0);
    expect(screen.queryByText("guide-12.md")).not.toBeInTheDocument();
    expect(screen.getByText("文档分页 1 / 1")).toBeInTheDocument();
    vi.unstubAllGlobals();
  });

  it("creates a knowledge base through the API", async () => {
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (init?.method === "POST") {
        return new Response(JSON.stringify({
          data: { id: "kb-001", name: "新知识库", description: "desc", owner_id: "u1", status: "active" },
        }));
      }
      return new Response(JSON.stringify({ data: [] }));
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<KnowledgeBaseListPage />);
    fireEvent.change(screen.getByLabelText("知识库名称"), { target: { value: "新知识库" } });
    fireEvent.click(screen.getByText("创建知识库"));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/kb",
      expect.objectContaining({ method: "POST" }),
    ));
    vi.unstubAllGlobals();
  });

  it("publishes a changed knowledge base through the API", async () => {
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (url === "/api/v1/kb/kb-002/publish") {
        return new Response(JSON.stringify({
          data: {
            id: "kb-002",
            name: "研发草稿库",
            description: "内部草稿",
            owner_id: "u1",
            status: "published",
          },
        }));
      }
      return new Response(JSON.stringify({
        data: [
          {
            id: "kb-002",
            name: "研发草稿库",
            description: "内部草稿",
            owner_id: "u1",
            status: "changed",
          },
        ],
      }));
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<KnowledgeBaseListPage />);
    expect(await screen.findByText("研发草稿库")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "发布 研发草稿库" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/kb/kb-002/publish",
      expect.objectContaining({ method: "POST" }),
    ));
    vi.unstubAllGlobals();
  });

  it("deletes a knowledge base through the API and refreshes the list", async () => {
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (url === "/api/v1/kb/kb-002?owner_id=default" && init?.method === "DELETE") {
        return new Response(JSON.stringify({
          data: {
            id: "kb-002",
            name: "研发草稿库",
            description: "内部草稿",
            owner_id: "u1",
            status: "deleted",
            deleted_document_count: 2,
            deleted_chunk_count: 8,
          },
        }));
      }
      return new Response(JSON.stringify({
        data: [
          {
            id: "kb-002",
            name: "研发草稿库",
            description: "内部草稿",
            owner_id: "u1",
            status: "changed",
          },
        ],
      }));
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<KnowledgeBaseListPage />);
    expect(await screen.findByText("研发草稿库")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "删除知识库 研发草稿库" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/kb/kb-002?owner_id=default",
      expect.objectContaining({ method: "DELETE" }),
    ));
    expect(await screen.findByText("删除完成，已清理 2 个文档 / 8 个 Chunk")).toBeInTheDocument();
    vi.unstubAllGlobals();
  });

  it("uploads markdown documents through the API", async () => {
    const fetchMock = vi.fn(async (url: string) => {
      if (url.endsWith("/documents")) {
        return new Response(JSON.stringify({
          data: { id: "doc-001", document_name: "a.md", status: "ready", chunk_count: 1 },
        }));
      }
      return new Response(JSON.stringify({ data: [] }));
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<KnowledgeBaseDetailPage kbId="kb-001" />);
    fireEvent.change(screen.getByLabelText("文档名称"), { target: { value: "a.md" } });
    fireEvent.change(screen.getByLabelText("Markdown 内容"), { target: { value: "# A\n正文" } });
    fireEvent.click(screen.getByText("提交录入"));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/kb/kb-001/documents",
      expect.objectContaining({ method: "POST" }),
    ));
    vi.unstubAllGlobals();
  });

  it("does not render chunk settings inside the document detail page", async () => {
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (url === "/api/v1/kb/kb-001/documents") {
        return new Response(JSON.stringify({ data: [] }));
      }
      return new Response(JSON.stringify({ data: [] }));
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<KnowledgeBaseDetailPage kbId="kb-001" />);

    expect(await screen.findByText("文档列表")).toBeInTheDocument();
    expect(screen.queryByLabelText("Overlap")).not.toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalledWith("/api/v1/kb/kb-001/settings", expect.anything());
    vi.unstubAllGlobals();
  });
});
