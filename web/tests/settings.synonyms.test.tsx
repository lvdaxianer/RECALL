import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { SettingsPage } from "../src/features/settings/SettingsPage";

describe("SettingsPage synonyms", () => {
  it("keeps the answer cache table stable when cache response is empty or malformed", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        if (url === "/api/v1/retrieval/answers/cache") {
          return new Response(JSON.stringify({ data: [] }));
        }
        return new Response(JSON.stringify({ data: [] }));
      }),
    );

    render(<SettingsPage />);

    expect(screen.getByRole("table", { name: "答案缓存" })).toBeInTheDocument();
    expect(await screen.findByText("暂无答案缓存")).toBeInTheDocument();

    vi.unstubAllGlobals();
  });

  it("creates edits disables and deletes synonym groups", async () => {
    let groups: Array<{
      id: string;
      knowledge_base_id: string | null;
      canonical: string;
      terms: string[];
      owner_id: string;
      enabled: boolean;
    }> = [];
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (url === "/api/v1/rag/cache/answers") {
        return new Response(JSON.stringify({ data: { items: [] } }));
      }
      if (url === "/api/v1/kb") {
        return new Response(JSON.stringify({
          data: [{ id: "kb-001", name: "产品知识库", description: "desc", owner_id: "u1", status: "published" }],
        }));
      }
      if (url === "/api/v1/synonyms" && init?.method === "POST") {
        const payload = JSON.parse(String(init.body));
        groups = [{ id: "syn-001", owner_id: "u1", enabled: true, ...payload }];
        return new Response(JSON.stringify({ data: groups[0] }));
      }
      if (url === "/api/v1/synonyms/syn-001" && init?.method === "PATCH") {
        const payload = JSON.parse(String(init.body));
        groups = [{ ...groups[0], ...payload }];
        return new Response(JSON.stringify({ data: groups[0] }));
      }
      if (url === "/api/v1/synonyms/syn-001" && init?.method === "DELETE") {
        groups = [];
        return new Response(JSON.stringify({ data: { id: "syn-001" } }));
      }
      if (url === "/api/v1/synonyms") {
        return new Response(JSON.stringify({ data: groups }));
      }
      return new Response(JSON.stringify({ data: [] }));
    });
    vi.stubGlobal("fetch", fetchMock);

    // v1.5: 设置子菜单搬到 AppShell 侧栏；本页只剩表单。
    // 测试里通过 hash 路由直接跳到同义词 tab（模拟用户点侧栏链接）。
    window.location.hash = "#设置/同义词";
    window.dispatchEvent(new HashChangeEvent("hashchange"));
    render(<SettingsPage />);
    // 此时应渲染同义词面板（标准词 / 同义词输入）
    expect(await screen.findByLabelText("标准词")).toBeInTheDocument();
    expect(screen.getByLabelText("同义词")).toBeInTheDocument();

    fireEvent.change(await screen.findByLabelText("标准词"), { target: { value: "作用" } });
    expect(screen.getByLabelText("同义词")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("同义词"), { target: { value: "干啥用的, 有什么作用" } });
    fireEvent.click(screen.getByRole("button", { name: "创建同义词组" }));

    expect(await screen.findByText("作用")).toBeInTheDocument();
    expect(screen.getByText("干啥用的 / 有什么作用")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("编辑标准词 syn-001"), { target: { value: "用途" } });
    fireEvent.click(screen.getByRole("button", { name: "保存同义词组 syn-001" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/synonyms/syn-001",
      expect.objectContaining({
        method: "PATCH",
        body: expect.stringContaining('"canonical":"用途"'),
      }),
    ));
    expect(await screen.findByText("用途")).toBeInTheDocument();

    fireEvent.click(screen.getByLabelText("禁用同义词组 syn-001"));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/synonyms/syn-001",
      expect.objectContaining({
        method: "PATCH",
        body: expect.stringContaining('"enabled":false'),
      }),
    ));

    fireEvent.click(screen.getByRole("button", { name: "删除同义词组 syn-001" }));
    await waitFor(() => expect(screen.queryByText("用途")).not.toBeInTheDocument());

    vi.unstubAllGlobals();
  });
});
