import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { DocumentIngestPage } from "../src/features/documents/DocumentIngestPage";

describe("DocumentIngestPage", () => {
  it("exposes one page heading and document intake metrics", () => {
    render(<DocumentIngestPage />);

    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(screen.getByRole("heading", { level: 1, name: "文档录入" })).toBeInTheDocument();
    expect(screen.getByText("Markdown only")).toBeInTheDocument();
    expect(screen.getByText("ES / Milvus")).toBeInTheDocument();
    expect(screen.getByText("draft to release")).toBeInTheDocument();
  });

  // v1.4: 文档解析状态已从本页移除（用户改去 KB 详情看）。
  // 改为验证"录入规则"里指引文案，引导到 KB 详情查看进度。
  it("directs users to the KB detail page for document parse status", () => {
    render(<DocumentIngestPage />);

    expect(screen.getByText("录入规则")).toBeInTheDocument();
    expect(screen.getByText(/知识库.*文档列表/)).toBeInTheDocument();
    expect(screen.queryByText("文档解析状态")).not.toBeInTheDocument();
  });
});
