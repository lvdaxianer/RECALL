import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { EmptyState } from "../src/components/common/EmptyState";
import { ErrorState } from "../src/components/common/ErrorState";
import { LoadingState } from "../src/components/common/LoadingState";
import { StatusBadge } from "../src/components/common/StatusBadge";
import { AppShell } from "../src/components/layout/AppShell";

describe("common states", () => {
  it("renders a simple white-theme loading state", () => {
    render(<LoadingState label="加载知识库中" />);
    expect(screen.getByText("加载知识库中")).toBeInTheDocument();
  });

  it("renders app shell title and content", () => {
    render(
      <AppShell title="知识库检索控制台">
        <div>content</div>
      </AppShell>,
    );

    expect(screen.getByText("知识库检索控制台")).toBeInTheDocument();
    expect(screen.getByText("content")).toBeInTheDocument();
  });

  it("renders empty and error states with retry", () => {
    const onRetry = vi.fn();

    render(
      <>
        <EmptyState title="暂无知识库" description="先创建一个知识库" />
        <ErrorState title="加载失败" onRetry={onRetry} />
        <StatusBadge status="active" />
      </>,
    );

    expect(screen.getByText("暂无知识库")).toBeInTheDocument();
    expect(screen.getByText("加载失败")).toBeInTheDocument();
    expect(screen.getByText("active")).toBeInTheDocument();
  });
});
