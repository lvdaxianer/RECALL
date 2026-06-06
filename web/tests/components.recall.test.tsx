import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { EmptyState } from "../src/components/recall/EmptyState";
import { ErrorState } from "../src/components/recall/ErrorState";
import { EvidenceSheet } from "../src/components/recall/EvidenceSheet";
import { LoadingState } from "../src/components/recall/LoadingState";
import { TraceTimeline } from "../src/components/recall/TraceTimeline";

describe("Recall shared state components", () => {
  it("renders empty state with title and description", () => {
    render(<EmptyState title="暂无文档" description="上传后会显示解析状态" />);
    expect(screen.getByText("暂无文档")).toBeInTheDocument();
    expect(screen.getByText("上传后会显示解析状态")).toBeInTheDocument();
  });

  it("renders retryable error state", async () => {
    const onRetry = vi.fn();
    render(<ErrorState title="加载失败" description="请稍后重试" onRetry={onRetry} />);
    screen.getByRole("button", { name: "重试" }).click();
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("renders accessible loading state", () => {
    render(<LoadingState title="正在加载" />);
    expect(screen.getByRole("status")).toHaveTextContent("正在加载");
  });
});

describe("TraceTimeline", () => {
  it("renders stage duration and event summaries", () => {
    render(
      <TraceTimeline
        events={[
          {
            event: "retrieval.progress",
            payload: { stage: "hybrid_search", summary: "召回 8 个片段", duration_ms: 123.4 },
          },
        ]}
      />,
    );

    expect(screen.getByText("hybrid_search")).toBeInTheDocument();
    expect(screen.getByText("召回 8 个片段")).toBeInTheDocument();
    expect(screen.getByText("123ms")).toBeInTheDocument();
  });
});

describe("EvidenceSheet", () => {
  it("closes with Escape while reviewing evidence", () => {
    const onOpenChange = vi.fn();
    render(
      <EvidenceSheet
        open
        onOpenChange={onOpenChange}
        events={[
          {
            event: "answer.completed",
            payload: {
              results: [
                {
                  chunk_id: "chunk-001",
                  document_name: "guide.md",
                  title: "ES 过滤字段",
                  content: "knowledge_base_id 需要写入过滤字段。",
                  score: 0.92,
                },
              ],
            },
          },
        ]}
      />,
    );

    screen.getByRole("dialog", { name: "证据与 Trace" }).dispatchEvent(
      new KeyboardEvent("keydown", { key: "Escape", bubbles: true }),
    );

    expect(onOpenChange).toHaveBeenCalledWith(false);
  });
});
