import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { RetrievalConsolePage } from "../src/features/retrieval/RetrievalConsolePage";

describe("retrieval console", () => {
  it("renders knowledge base multiselect and stream controls", () => {
    render(<RetrievalConsolePage />);

    expect(screen.getByText("Retrieval Debugger")).toBeInTheDocument();
    expect(screen.getByText("summary-first")).toBeInTheDocument();
    expect(screen.getByText("query scope")).toBeInTheDocument();
    expect(screen.getByText("检索控制台")).toBeInTheDocument();
    expect(screen.getByText("知识库范围")).toBeInTheDocument();
    expect(screen.getByText("开始流式检索")).toBeInTheDocument();
    expect(screen.getByText("流式输出")).toBeInTheDocument();
    expect(screen.getByText("Trace")).toBeInTheDocument();
  });

  it("calls real stream API when starting retrieval", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        if (url === "/api/v1/kb") {
          return new Response(JSON.stringify({
            data: [
              { id: "kb-001", name: "已发布 KB", description: "desc", owner_id: "u1", status: "published" },
              { id: "kb-002", name: "草稿 KB", description: "desc", owner_id: "u1", status: "draft" },
            ],
          }));
        }
        return new Response('event: answer.delta\ndata: {"payload":{"text":"命中"}}\n\n');
      }),
    );

    render(<RetrievalConsolePage />);
    await screen.findByText("已发布 KB");
    expect(screen.getByLabelText("草稿 KB")).toBeDisabled();
    fireEvent.click(screen.getByLabelText("已发布 KB"));
    fireEvent.change(screen.getByLabelText("问题"), { target: { value: "检索" } });
    fireEvent.click(screen.getByText("开始流式检索"));

    await waitFor(() => expect(screen.getAllByText(/命中/).length).toBeGreaterThan(0));
    vi.unstubAllGlobals();
  });

  it("shows stream errors and retries the last retrieval", async () => {
    let streamAttempts = 0;
    const fetchMock = vi.fn(async (url: string) => {
      if (url === "/api/v1/kb") {
        return new Response(JSON.stringify({
          data: [{ id: "kb-001", name: "已发布 KB", description: "desc", owner_id: "u1", status: "published" }],
        }));
      }
      streamAttempts += 1;
      if (streamAttempts === 1) {
        return new Response(JSON.stringify({ detail: { message: "检索失败" } }), { status: 500 });
      }
      return new Response('event: answer.delta\ndata: {"payload":{"text":"重试命中"}}\n\n');
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<RetrievalConsolePage />);
    await screen.findByText("已发布 KB");
    fireEvent.change(screen.getByLabelText("问题"), { target: { value: "检索" } });
    fireEvent.click(screen.getByText("开始流式检索"));

    expect(await screen.findByText("检索失败")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "重试" }));
    await waitFor(() => expect(screen.getAllByText(/重试命中/).length).toBeGreaterThan(0));
    vi.unstubAllGlobals();
  });

  it("renders trace as compact markdown cards instead of a full JSON dump", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        if (url === "/api/v1/kb") {
          return new Response(JSON.stringify({
            data: [{ id: "kb-001", name: "已发布 KB", description: "desc", owner_id: "u1", status: "published" }],
          }));
        }
        return new Response(
          'event: retrieval.trace\ndata: {"payload":{"trace":[{"stage":"query_scope","summary":"识别为全局检索","metrics":{"route_plan":["summary_retrieval"],"very_long":"不应该完整展示"}}]}}\n\n' +
            'event: answer.completed\ndata: {"payload":{"duration_ms":128}}\n\n',
        );
      }),
    );

    render(<RetrievalConsolePage />);
    await screen.findByText("已发布 KB");
    fireEvent.change(screen.getByLabelText("问题"), { target: { value: "检索" } });
    fireEvent.click(screen.getByText("开始流式检索"));

    expect(await screen.findByText("识别为全局检索")).toBeInTheDocument();
    expect(screen.getByText("query_scope")).toBeInTheDocument();
    expect(screen.getByText("route_plan: summary_retrieval")).toBeInTheDocument();
    expect(screen.queryByText(/very_long/)).not.toBeInTheDocument();
    expect(screen.queryByText(/\"payload\"/)).not.toBeInTheDocument();
    vi.unstubAllGlobals();
  });

  it("renders duration metrics for each trace stage", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        if (url === "/api/v1/kb") {
          return new Response(JSON.stringify({
            data: [{ id: "kb-001", name: "已发布 KB", description: "desc", owner_id: "u1", status: "published" }],
          }));
        }
        return new Response(
          'event: retrieval.trace\ndata: {"payload":{"trace":[{"stage":"retrieval","summary":"检索完成","metrics":{"duration_ms":42,"result_count":3}}]}}\n\n' +
            'event: answer.completed\ndata: {"payload":{"duration_ms":128,"stage_durations_ms":{"retrieval":42,"answer_generation":86}}}\n\n',
        );
      }),
    );

    render(<RetrievalConsolePage />);
    await screen.findByText("已发布 KB");
    fireEvent.change(screen.getByLabelText("问题"), { target: { value: "检索" } });
    fireEvent.click(screen.getByText("开始流式检索"));

    expect(await screen.findByText("duration_ms: 42")).toBeInTheDocument();
    expect(await screen.findByText("retrieval: 42")).toBeInTheDocument();
    expect(screen.getByText("answer_generation: 86")).toBeInTheDocument();
    vi.unstubAllGlobals();
  });
});
