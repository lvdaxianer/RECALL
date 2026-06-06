import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { EvaluationPage } from "../src/features/evaluation/EvaluationPage";
import { HomePage } from "../src/features/home/HomePage";

describe("home and evaluation pages", () => {
  it("renders the home workspace with one h1, metrics, and dense sections", () => {
    render(<HomePage />);

    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(screen.getByRole("heading", { level: 1, name: "Recall RAG 检索流程" })).toBeInTheDocument();
    expect(screen.getByText("Route Plan")).toBeInTheDocument();
    expect(screen.getByText("先判断再检索")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "可审计 RAG 流程图" })).toBeInTheDocument();
  });

  it("renders evaluation controls with one h1, metrics, and an accessible primary action", () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(JSON.stringify({
          data: [{ id: "kb-001", name: "产品知识库", description: "desc", owner_id: "u1", status: "published" }],
        })),
      ),
    );

    render(<EvaluationPage />);

    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(screen.getByRole("heading", { level: 1, name: "效果评测" })).toBeInTheDocument();
    expect(screen.getByText("score trace")).toBeInTheDocument();
    expect(screen.getByLabelText("评测问题")).toBeInTheDocument();
    expect(screen.getByLabelText("评测知识库")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "开始评测" })).toBeInTheDocument();

    vi.unstubAllGlobals();
  });
});
