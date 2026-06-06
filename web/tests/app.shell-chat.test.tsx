import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, beforeEach, vi } from "vitest";

import { App } from "../src/app/App";

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}

globalThis.ResizeObserver ??= ResizeObserverStub;

function stubKnowledgeBases() {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      if (url === "/api/v1/kb") {
        return new Response(JSON.stringify({
          data: [
            {
              id: "kb-published",
              name: "已发布知识库",
              description: "可用于聊天",
              owner_id: "u1",
              status: "published",
            },
            {
              id: "kb-draft",
              name: "草稿知识库",
              description: "仍在编辑",
              owner_id: "u1",
              status: "draft",
            },
          ],
        }));
      }
      return new Response(
          'event: answer.delta\ndata: {"payload":{"text":"可以这样配置。","chunk_id":"chunk-001","content":"knowledge_base_id 需要同时写入 ES 与 Milvus 过滤字段。"}}\n\n' +
          'event: answer.completed\ndata: {"request_id":"req-chat-001","payload":{"results":[{"chunk_id":"chunk-001","document_name":"guide.md","title":"ES 过滤字段","content":"knowledge_base_id 需要同时写入 ES 与 Milvus 过滤字段。","score":0.92}]}}\n\n',
      );
    }),
  );
}

function makeSession(sessionId: string, title: string) {
  return {
    session_id: sessionId,
    user_id: "default",
    runtime_id: `local:default:${sessionId}`,
    title,
    status: "active",
    metadata: {},
    created_at: "2026-06-04T00:00:00Z",
    updated_at: "2026-06-04T00:00:00Z",
  };
}

function makeRun(runId: string, input: string, answer: string) {
  return {
    run_id: runId,
    user_id: "default",
    session_id: "sess-api",
    request_id: "req-001",
    input,
    status: "completed",
    tools: ["retrieval.search.stream"],
    answer,
    error: null,
    metadata: {},
    created_at: "2026-06-04T00:00:00Z",
    updated_at: "2026-06-04T00:00:00Z",
  };
}

function makeEvent(eventId: string, event: string, payload: Record<string, unknown>) {
  return {
    event_id: eventId,
    event,
    user_id: "default",
    session_id: "sess-api",
    run_id: "run-001",
    request_id: "req-001",
    sequence: eventId === "evt-trace" ? 1 : 2,
    payload,
    created_at: "2026-06-04T00:00:00Z",
  };
}

describe("app shell and chat assistant", () => {
  // v1.4: App 用 hash 路由，测试间清空 hash 让每个用例从默认首页开始。
  beforeEach(() => {
    if (typeof window !== "undefined" && window.history && window.history.replaceState) {
      window.history.replaceState(null, "", window.location.pathname + window.location.search);
    }
  });

  it("closes the mobile sidebar after navigation so main actions remain reachable", async () => {
    const originalInnerWidth = window.innerWidth;
    const originalMatchMedia = window.matchMedia;
    Object.defineProperty(window, "innerWidth", { configurable: true, value: 375 });
    window.matchMedia = vi.fn().mockImplementation((query: string) => ({
      matches: query.includes("767"),
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }));
    stubKnowledgeBases();

    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "切换主导航" }));
    fireEvent.click(screen.getByRole("link", { name: "答案缓存" }));

    expect(await screen.findByRole("button", { name: "打开 Recall 助手" })).toBeInTheDocument();

    Object.defineProperty(window, "innerWidth", { configurable: true, value: originalInnerWidth });
    window.matchMedia = originalMatchMedia;
    vi.unstubAllGlobals();
  });

  it("renders accessible app shell navigation with icon labels", async () => {
    stubKnowledgeBases();

    render(<App />);

    expect(screen.getByRole("navigation", { name: "主导航" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "打开 Recall 助手" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /知识库/ })).toBeInTheDocument();

    vi.unstubAllGlobals();
  });

  it("defaults to a product home page that explains the RAG retrieval flow", () => {
    stubKnowledgeBases();

    render(<App />);

    expect(screen.getByRole("link", { name: "首页" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("heading", { name: "Recall RAG 检索流程" })).toBeInTheDocument();
    expect(screen.getByText("Query Scope")).toBeInTheDocument();
    expect(screen.getByText("Summary-first")).toBeInTheDocument();
    expect(screen.getByText("Parent / Section Expansion")).toBeInTheDocument();
    expect(screen.getByText("ES + Milvus + Rerank")).toBeInTheDocument();
    expect(screen.getByText("为什么更准确")).toBeInTheDocument();
    expect(screen.getByText("为什么更快")).toBeInTheDocument();
    expect(screen.getByText("流式问答输出")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "可审计 RAG 流程图" })).toBeInTheDocument();
    expect(screen.getByText("CoT Plan 摘要")).toBeInTheDocument();
    expect(screen.getByText("优化策略矩阵")).toBeInTheDocument();
    expect(screen.getAllByText("rewrite query").length).toBeGreaterThan(0);
    expect(screen.getAllByText("route_plan").length).toBeGreaterThan(0);
    expect(screen.getAllByText("cot_plan 摘要输出").length).toBeGreaterThan(0);
    expect(screen.getByRole("heading", { name: "我们到底优化了哪里" })).toBeInTheDocument();
    expect(screen.getByText("查询先规划")).toBeInTheDocument();
    expect(screen.getByText("证据先扩展")).toBeInTheDocument();
    expect(screen.getByText("排序先治理")).toBeInTheDocument();
    expect(screen.getByText("输出先可解释")).toBeInTheDocument();
    expect(screen.getByText("少搜错库、少走错链路")).toBeInTheDocument();
    expect(screen.getByText("少拿孤立 chunk 回答")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "先理解几个核心概念" })).toBeInTheDocument();
    expect(screen.getByText("cot cache")).toBeInTheDocument();
    expect(screen.getByText("缓存规划摘要和稳定路由，重复问题不用每次重新规划。")).toBeInTheDocument();
    expect(screen.getByText("把用户原始问题改写成更适合检索的查询表达。")).toBeInTheDocument();
    expect(screen.getByText("判断问题应该走概览、事实、配置还是故障定位。")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "缓存如何让检索更快" })).toBeInTheDocument();
    expect(screen.getByText("Query Optimize Cache")).toBeInTheDocument();
    expect(screen.getByText("Embedding Cache")).toBeInTheDocument();
    expect(screen.getByText("Rerank Cache")).toBeInTheDocument();
    expect(screen.getByText("LightRAG-lite 轻量图检索")).toBeInTheDocument();
    expect(screen.getByText("实体关系图索引")).toBeInTheDocument();
    expect(screen.getByText("用 entities / relations 快速命中结构化线索，再决定是否进入 ES、Milvus、Rerank。")).toBeInTheDocument();

    vi.unstubAllGlobals();
  });

  it("renders header navigation and sidebar knowledge workflows", () => {
    stubKnowledgeBases();

    render(<App />);

    expect(screen.getByRole("banner")).toHaveTextContent("Recall");
    // v1.1 顶栏：合并的 SDK 状态徽章
    expect(screen.getByText("SDK Ready")).toBeInTheDocument();
    // v1.1 侧栏：扁平化导航 + 品牌副标题
    expect(screen.getAllByText("知识库检索控制台").length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: "新建知识库" })).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "主导航" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "首页" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "知识库管理" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "文档录入" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "检索调试" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "效果评测" })).toBeInTheDocument();

    vi.unstubAllGlobals();
  });

  it("switches to document ingest page and uploads into the selected knowledge base", async () => {
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (url === "/api/v1/kb/kb-draft/documents") {
        return new Response(JSON.stringify({
          data: { id: "doc-001", document_name: "guide.md", status: "ready", chunk_count: 1 },
        }));
      }
      if (url === "/api/v1/kb") {
        return new Response(JSON.stringify({
          data: [
            {
              id: "kb-draft",
              name: "草稿知识库",
              description: "可录入",
              owner_id: "u1",
              status: "draft",
            },
          ],
        }));
      }
      return new Response('event: answer.completed\ndata: {"payload":{}}\n\n');
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    fireEvent.click(screen.getByRole("link", { name: "文档录入" }));

    expect(await screen.findByRole("heading", { name: "文档录入" })).toBeInTheDocument();
    expect(screen.getByText("Document Intake")).toBeInTheDocument();
    expect(screen.getByText("Markdown only")).toBeInTheDocument();
    expect(screen.getByText("选择知识库")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("选择知识库"), { target: { value: "kb-draft" } });
    fireEvent.change(screen.getByLabelText("文档名称"), { target: { value: "guide.md" } });
    fireEvent.change(screen.getByLabelText("Markdown 内容"), { target: { value: "# Guide\n正文" } });
    fireEvent.click(screen.getByRole("button", { name: "提交录入" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/kb/kb-draft/documents",
      expect.objectContaining({ method: "POST" }),
    ));
    expect(await screen.findByText("录入完成")).toBeInTheDocument();
    vi.unstubAllGlobals();
  });

  it("switches to the evaluation page with a runnable baseline form", async () => {
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (url === "/api/v1/kb") {
        return new Response(JSON.stringify({
          data: [
            {
              id: "kb-published",
              name: "已发布知识库",
              description: "可用于评测",
              owner_id: "u1",
              status: "published",
            },
            {
              id: "kb-draft",
              name: "草稿知识库",
              description: "不可评测",
              owner_id: "u1",
              status: "draft",
            },
          ],
        }));
      }
      if (url === "/api/v1/retrieval/search" && init?.method === "POST") {
        return new Response(JSON.stringify({
          data: {
            request_id: "req-eval",
            query_scope: "hybrid",
            route_plan: { strategy: "summary-first", steps: ["summary", "evidence"] },
            filters: { knowledge_base_ids: ["kb-published"] },
            results: [
              {
                chunk_id: "chunk-001",
                knowledge_base_id: "kb-published",
                document_name: "guide.md",
                title: "ES 过滤字段",
                content: "可以按 knowledge_base_id 过滤。",
                score: 0.91,
                score_trace: { rerank_score: 0.91, bm25_score: 0.62 },
              },
            ],
            trace: [
              { stage: "query_scope", summary: "识别为混合检索", metrics: { query_scope: "hybrid" } },
            ],
          },
        }));
      }
      return new Response('event: answer.completed\ndata: {"payload":{}}\n\n');
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    fireEvent.click(screen.getByRole("link", { name: "效果评测" }));

    expect(await screen.findByRole("heading", { name: "效果评测" })).toBeInTheDocument();
    expect(screen.getByText("Retrieval Evaluation")).toBeInTheDocument();
    expect(screen.getByText("score trace")).toBeInTheDocument();
    expect(screen.getByText("评测问题")).toBeInTheDocument();
    expect(screen.getByText("评测知识库")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "开始评测" })).toBeDisabled();
    expect(screen.getByText("暂无评测结果")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("评测知识库"), { target: { value: "kb-published" } });
    fireEvent.change(screen.getByLabelText("评测问题"), { target: { value: "ES 过滤字段怎么配置？" } });
    fireEvent.click(screen.getByRole("button", { name: "开始评测" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/retrieval/search",
      expect.objectContaining({ method: "POST" }),
    ));
    expect(await screen.findByText("hybrid")).toBeInTheDocument();
    expect(screen.getByText("1 条命中")).toBeInTheDocument();
    expect(screen.getByText("0.91")).toBeInTheDocument();
    expect(screen.getByText("ES 过滤字段")).toBeInTheDocument();
    expect(screen.getByText("识别为混合检索")).toBeInTheDocument();
    vi.unstubAllGlobals();
  });

  it("opens a conversational chat panel with sessions and published knowledge base selection", async () => {
    stubKnowledgeBases();

    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "打开 Recall 助手" }));

    const dialog = screen.getByRole("dialog", { name: "Recall 助手" });
    expect(dialog).toBeInTheDocument();
    expect(dialog).toHaveAttribute("data-assistant-ui-runtime", "local");
    expect(within(dialog).getByRole("textbox", { name: "输入问题" })).toBeInTheDocument();
    expect(within(dialog).getByText("Recall 助手")).toBeInTheDocument();
    expect(within(dialog).getByText("证据优先")).toBeInTheDocument();
    expect(within(dialog).getByText("会话")).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "新建会话" })).toBeInTheDocument();
    fireEvent.click(await within(dialog).findByRole("button", { name: /知识库范围/ }));
    expect(await within(dialog).findByLabelText("已发布知识库")).toBeEnabled();
    expect(within(dialog).getByLabelText("草稿知识库")).toBeDisabled();
    expect(within(dialog).getByText("草稿知识库不可用于聊天")).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("button", { name: "收起知识库范围" }));

    fireEvent.change(within(dialog).getByLabelText("输入问题"), { target: { value: "ES 如何配置过滤字段？" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "发送" }));

    expect(await within(dialog).findByText("ES 如何配置过滤字段？")).toBeInTheDocument();
    await waitFor(() => expect(within(dialog).getAllByText(/可以这样配置/).length).toBeGreaterThan(0));
    expect(await within(dialog).findByText(/总耗时/)).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("button", { name: "查看证据与 Trace" }));
    // v1.3: 证据面板内联在右栏，不开新 dialog
    expect(await within(dialog).findByText("证据 & Trace")).toBeInTheDocument();
    expect(within(dialog).getByText("guide.md")).toBeInTheDocument();
    expect(within(dialog).getByText("ES 过滤字段")).toBeInTheDocument();
    expect(within(dialog).getByText("0.920")).toBeInTheDocument();
    expect(within(dialog).getAllByText("knowledge_base_id 需要同时写入 ES 与 Milvus 过滤字段。").length).toBeGreaterThan(0);

    vi.unstubAllGlobals();
  });

  it("sends answer feedback from chat assistant messages", async () => {
    let streamCalls = 0;
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (url === "/api/v1/kb") {
        return new Response(JSON.stringify({
          data: [
            {
              id: "kb-published",
              name: "已发布知识库",
              description: "可用于聊天",
              owner_id: "u1",
              status: "published",
            },
          ],
        }));
      }
      if (url === "/api/v1/retrieval/answers/req-chat-001/feedback") {
        return new Response(JSON.stringify({ data: { vote: "dislike", deleted: true } }));
      }
      if (url === "/api/v1/retrieval/search/stream" && init?.method === "POST") {
        streamCalls += 1;
        const requestId = streamCalls === 1 ? "req-chat-001" : "req-chat-002";
        const answer = streamCalls === 1 ? "JMM 缓存答案" : "JMM 重新检索答案";
        return new Response(
          `event: answer.delta\ndata: {"payload":{"text":"${answer}","chunk_id":"chunk-001"}}\n\n` +
            `event: answer.completed\ndata: {"request_id":"${requestId}","payload":{"results":[{"chunk_id":"chunk-001","document_name":"jmm.md","title":"JMM","content":"JMM 访问策略","score":0.92}]}}\n\n`,
        );
      }
      return new Response(
        JSON.stringify({ data: [] }),
      );
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "打开 Recall 助手" }));
    const dialog = screen.getByRole("dialog", { name: "Recall 助手" });
    await within(dialog).findByRole("button", { name: /知识库范围/ });
    fireEvent.change(within(dialog).getByLabelText("输入问题"), { target: { value: "JMM 的访问策略是啥？" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "发送" }));

    expect(await within(dialog).findByText("JMM 缓存答案")).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "点赞这条回答" })).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("button", { name: "点踩并重新检索" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/retrieval/answers/req-chat-001/feedback",
      expect.objectContaining({ method: "POST" }),
    ));
    await waitFor(() => expect(streamCalls).toBe(2));
    expect(await within(dialog).findByText("JMM 重新检索答案")).toBeInTheDocument();
    expect(await within(dialog).findByText("这题不算，我让它重新想一遍")).toBeInTheDocument();
    vi.unstubAllGlobals();
  });

  it("shows retrieval progress before answer text and keeps feedback controls reachable", async () => {
    let releaseStream: (() => void) | undefined;
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (url === "/api/v1/kb") {
        return new Response(JSON.stringify({
          data: [
            {
              id: "kb-published",
              name: "已发布知识库",
              description: "可用于聊天",
              owner_id: "u1",
              status: "published",
            },
          ],
        }));
      }
      if (url === "/api/v1/retrieval/answers/req-streaming/feedback" && init?.method === "POST") {
        return new Response(JSON.stringify({ data: { vote: "like", found: true, trust_score: 1 } }));
      }
      if (url === "/api/v1/retrieval/search/stream") {
        const stream = new ReadableStream({
          start(controller) {
            const encoder = new TextEncoder();
            controller.enqueue(encoder.encode(
              'event: request.created\ndata: {"request_id":"req-streaming","payload":{"input":"Redis 为什么慢？"}}\n\n' +
                'event: retrieval.progress\ndata: {"request_id":"req-streaming","payload":{"stage":"query_scope","summary":"正在分析问题类型和检索范围"}}\n\n',
            ));
            releaseStream = () => {
              controller.enqueue(encoder.encode(
                'event: answer.delta\ndata: {"request_id":"req-streaming","payload":{"text":"Redis 慢查询需要先看 big key。"}}\n\n' +
                  'event: answer.completed\ndata: {"request_id":"req-streaming","payload":{"results":[]}}\n\n',
              ));
              controller.close();
            };
          },
        });
        return new Response(stream);
      }
      return new Response(JSON.stringify({ data: [] }));
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "打开 Recall 助手" }));
    const dialog = screen.getByRole("dialog", { name: "Recall 助手" });
    await within(dialog).findByRole("button", { name: /知识库范围/ });
    fireEvent.change(within(dialog).getByLabelText("输入问题"), { target: { value: "Redis 为什么慢？" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "发送" }));

    expect(await within(dialog).findByText("思考中")).toBeInTheDocument();
    expect(await within(dialog).findByText("正在判断这个问题适合怎么查")).toBeInTheDocument();
    expect(within(dialog).queryByText(/stage:/)).not.toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("button", { name: "点赞这条回答" }));
    expect(await within(dialog).findByText("反馈会在回答完成后提交")).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "点踩并重新检索" })).toBeEnabled();

    releaseStream?.();
    expect(await within(dialog).findByText("Redis 慢查询需要先看 big key。")).toBeInTheDocument();
    const completedThinking = await within(dialog).findByText("已完成思考");
    expect(completedThinking.closest("details")).not.toHaveAttribute("open");
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/retrieval/answers/req-streaming/feedback",
      expect.objectContaining({ method: "POST" }),
    ));
    expect(await within(dialog).findByText("已增加信任权重")).toBeInTheDocument();
    vi.unstubAllGlobals();
  });

  it("shows answer cache management in settings and deletes cache records", async () => {
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (url === "/api/v1/kb") {
        return new Response(JSON.stringify({ data: [] }));
      }
      if (url === "/api/v1/retrieval/answers/cache/cache-001" && init?.method === "DELETE") {
        return new Response(JSON.stringify({ data: { deleted: true } }));
      }
      if (url === "/api/v1/retrieval/answers/cache") {
        return new Response(JSON.stringify({
          data: {
            total: 1,
            items: [
              {
                cache_key: "cache-001",
                normalized_query: "jmm 访问策略是啥",
                knowledge_base_ids: ["kb-published"],
                answer_preview: "JMM 通过主内存和工作内存定义访问规则。",
                citation_count: 2,
                request_id: "req-cache-001",
                trust_score: 3,
                hit_count: 8,
                expires_at: "2026-06-04T08:00:00Z",
                updated_at: "2026-06-04T07:00:00Z",
              },
            ],
          },
        }));
      }
      return new Response('event: answer.completed\ndata: {"payload":{}}\n\n');
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    fireEvent.click(screen.getByRole("link", { name: "答案缓存" }));

    expect(await screen.findByRole("heading", { name: "答案缓存管理" })).toBeInTheDocument();
    // v1.5: 设置子菜单是独立 <a>（hash 路由），role 变成 link
    expect(screen.getByRole("link", { name: "答案缓存" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "重排缓存" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "模型配置" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "答案缓存管理" })).toBeInTheDocument();
    expect(screen.getByText("jmm 访问策略是啥")).toBeInTheDocument();
    expect(screen.getByText("命中 8 次")).toBeInTheDocument();
    expect(screen.getByText("信任 3")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "删除缓存 jmm 访问策略是啥" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/retrieval/answers/cache/cache-001",
      expect.objectContaining({ method: "DELETE" }),
    ));
    expect(await screen.findByText("缓存已删除")).toBeInTheDocument();
    vi.unstubAllGlobals();
  });

  it("keeps unfinished settings sections as blank states", async () => {
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      if (url === "/api/v1/kb") {
        return new Response(JSON.stringify({ data: [] }));
      }
      if (url === "/api/v1/retrieval/answers/cache") {
        return new Response(JSON.stringify({ data: { total: 0, items: [] } }));
      }
      return new Response(JSON.stringify({ data: [] }));
    }));

    render(<App />);
    fireEvent.click(screen.getByRole("link", { name: "答案缓存" }));
    fireEvent.click(await screen.findByRole("link", { name: "模型配置" }));

    expect(screen.getByRole("link", { name: "模型配置" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("heading", { name: "模型配置" })).toBeInTheDocument();
    expect(screen.getByText("该设置模块已预留，后续接入真实配置。")).toBeInTheDocument();
    vi.unstubAllGlobals();
  });

  it("loads chat sessions from the backend and creates a new backend session", async () => {
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (url === "/api/v1/kb") {
        return new Response(JSON.stringify({
          data: [
            {
              id: "kb-published",
              name: "已发布知识库",
              description: "可用于聊天",
              owner_id: "u1",
              status: "published",
            },
          ],
        }));
      }
      if (url === "/api/v1/agent/default/sessions" && init?.method === "POST") {
        return new Response(JSON.stringify({ data: makeSession("sess-new", "新的检索会话") }));
      }
      if (url === "/api/v1/agent/default/sessions") {
        return new Response(JSON.stringify({ data: [makeSession("sess-api", "ES 过滤调试")] }));
      }
      return new Response('event: answer.completed\ndata: {"payload":{}}\n\n');
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "打开 Recall 助手" }));
    const dialog = screen.getByRole("dialog", { name: "Recall 助手" });

    expect(await within(dialog).findByRole("button", { name: /ES 过滤调试/ })).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("button", { name: "新建会话" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/agent/default/sessions",
      expect.objectContaining({ method: "POST" }),
    ));
    expect(await within(dialog).findByRole("button", { name: /新的检索会话/ })).toBeInTheDocument();
    vi.unstubAllGlobals();
  });

  it("renames the active chat session from the sidebar", async () => {
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (url === "/api/v1/kb") {
        return new Response(JSON.stringify({ data: [] }));
      }
      if (url === "/api/v1/agent/default/sessions/sess-api" && init?.method === "PATCH") {
        return new Response(JSON.stringify({ data: makeSession("sess-api", "小程序白屏排查") }));
      }
      if (url === "/api/v1/agent/default/sessions") {
        return new Response(JSON.stringify({ data: [makeSession("sess-api", "新的检索会话")] }));
      }
      if (url === "/api/v1/agent/default/sessions/sess-api/runs") {
        return new Response(JSON.stringify({ data: [] }));
      }
      return new Response(JSON.stringify({ data: [] }));
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "打开 Recall 助手" }));
    const dialog = screen.getByRole("dialog", { name: "Recall 助手" });
    await waitFor(() => expect(fetchMock.mock.calls.some(([url]) => url === "/api/v1/agent/default/sessions")).toBe(true));
    await waitFor(() => expect(fetchMock.mock.calls.some(([url]) => url === "/api/v1/agent/default/sessions/sess-api/runs")).toBe(true));

    fireEvent.click(within(dialog).getByRole("button", { name: "修改会话名称" }));
    fireEvent.change(within(dialog).getByLabelText("会话名称"), { target: { value: "小程序白屏排查" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "保存会话名称" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/agent/default/sessions/sess-api",
      expect.objectContaining({
        method: "PATCH",
        body: JSON.stringify({ title: "小程序白屏排查" }),
      }),
    ));
    expect(await within(dialog).findByText("小程序白屏排查")).toBeInTheDocument();
    vi.unstubAllGlobals();
  });

  it("restores chat messages from backend runs and sends stream with the active session", async () => {
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (url === "/api/v1/kb") {
        return new Response(JSON.stringify({
          data: [
            {
              id: "kb-published",
              name: "已发布知识库",
              description: "可用于聊天",
              owner_id: "u1",
              status: "published",
            },
          ],
        }));
      }
      if (url === "/api/v1/agent/default/sessions") {
        return new Response(JSON.stringify({
          data: [makeSession("sess-api", "ES 过滤调试")],
        }));
      }
      if (url === "/api/v1/agent/default/sessions/sess-api/runs") {
        return new Response(JSON.stringify({
          data: [makeRun("run-001", "历史问题", "历史回答")],
        }));
      }
      if (url === "/api/v1/agent/default/sessions/sess-api/events?run_id=run-001") {
        return new Response(JSON.stringify({
          data: [
            makeEvent("evt-trace", "retrieval.trace", {
              trace: [
                { stage: "query_scope", summary: "识别为本地检索", metrics: { query_scope: "local" } },
              ],
            }),
            makeEvent("evt-delta", "answer.delta", { text: "历史回答", chunk_id: "chunk-001", content: "历史命中正文" }),
          ],
        }));
      }
      return new Response('event: answer.delta\ndata: {"payload":{"text":"新的回答"}}\n\nevent: answer.completed\ndata: {"payload":{}}\n\n');
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "打开 Recall 助手" }));
    const dialog = screen.getByRole("dialog", { name: "Recall 助手" });

    expect(await within(dialog).findByText("历史问题")).toBeInTheDocument();
    expect(within(dialog).getByText("历史回答")).toBeInTheDocument();
    expect(within(dialog).queryByText("已完成思考")).not.toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("button", { name: "查看证据与 Trace" }));
    // v1.3: 证据面板内联在右栏
    expect(await within(dialog).findByText("证据 & Trace")).toBeInTheDocument();
    expect(within(dialog).getByText("查询范围")).toBeInTheDocument();
    expect(within(dialog).getAllByText("识别为本地检索").length).toBeGreaterThan(0);
    expect(within(dialog).getByText("命中片段")).toBeInTheDocument();
    expect(within(dialog).getByText("历史命中正文")).toBeInTheDocument();
    fireEvent.change(within(dialog).getByLabelText("输入问题"), { target: { value: "新问题" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "发送" }));

    await waitFor(() => {
      const streamCall = fetchMock.mock.calls.find(([url]) => url === "/api/v1/retrieval/search/stream");
      expect(streamCall?.[1]?.body).toContain('"session_id":"sess-api"');
      expect(streamCall?.[1]?.body).toContain('"user_id":"default"');
    });
    vi.unstubAllGlobals();
  });

  it("shows backend published-only errors inside the chat conversation", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        if (url === "/api/v1/kb") {
          return new Response(JSON.stringify({
            data: [
              {
                id: "kb-published",
                name: "已发布知识库",
                description: "可用于聊天",
                owner_id: "u1",
                status: "published",
              },
            ],
          }));
        }
        return new Response(JSON.stringify({ detail: { message: "聊天检索只能选择已发布知识库" } }), {
          status: 400,
        });
      }),
    );

    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "打开 Recall 助手" }));
    const dialog = screen.getByRole("dialog", { name: "Recall 助手" });
    await within(dialog).findByRole("button", { name: /知识库范围/ });
    fireEvent.change(within(dialog).getByLabelText("输入问题"), { target: { value: "为什么不能检索？" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "发送" }));

    expect(await within(dialog).findByText("聊天检索只能选择已发布知识库")).toBeInTheDocument();
    vi.unstubAllGlobals();
  });

  it("keeps chat scope compact, renders markdown answers, and moves evidence into a drawer", async () => {
    const fetchMock = vi.fn(async (url: string) => {
      if (url === "/api/v1/kb") {
        return new Response(JSON.stringify({
          data: [
            ...Array.from({ length: 8 }, (_, index) => ({
              id: `kb-published-${index + 1}`,
              name: `已发布知识库 ${index + 1}`,
              description: "可用于聊天",
              owner_id: "u1",
              status: "published",
            })),
            {
              id: "kb-draft",
              name: "草稿知识库",
              description: "仍在编辑",
              owner_id: "u1",
              status: "draft",
            },
          ],
        }));
      }
      const encoder = new TextEncoder();
      return new Response(new ReadableStream({
        start(controller) {
          controller.enqueue(encoder.encode(
            'event: retrieval.trace\ndata: {"payload":{"trace":[{"stage":"query_scope","summary":"识别为知识库问答","metrics":{"query_scope":"knowledge"}}]}}\n\n',
          ));
          setTimeout(() => {
            controller.enqueue(encoder.encode(
              'event: answer.delta\ndata: {"payload":{"text":"# 回答摘要\\n\\n- 使用已发布知识库\\n- 支持 Markdown\\n\\n```txt\\nchunk evidence\\n```","chunk_id":"chunk-001","content":"Markdown 片段命中内容"}}\n\n',
            ));
            controller.enqueue(encoder.encode(
              'event: answer.completed\ndata: {"payload":{"results":[{"chunk_id":"chunk-001","document_name":"guide.md","title":"Markdown 渲染","content":"Markdown 片段命中内容","score":0.88}]}}\n\n',
            ));
            controller.close();
          }, 20);
        },
      }));
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "打开 Recall 助手" }));
    const dialog = screen.getByRole("dialog", { name: "Recall 助手" });

    await waitFor(() => expect(within(dialog).getByRole("button", { name: /知识库范围/ })).toHaveTextContent("已选 1 个"));
    expect(within(dialog).queryByLabelText("已发布知识库 8")).not.toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("button", { name: /知识库范围/ }));
    expect(await within(dialog).findByLabelText("搜索知识库")).toBeInTheDocument();
    expect(within(dialog).getByLabelText("已发布知识库 8")).toBeEnabled();
    expect(within(dialog).getByLabelText("草稿知识库")).toBeDisabled();
    fireEvent.click(within(dialog).getByRole("button", { name: "收起知识库范围" }));

    fireEvent.change(within(dialog).getByLabelText("输入问题"), { target: { value: "请总结" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "发送" }));

    expect(await within(dialog).findByText("思考中")).toBeInTheDocument();
    expect(await within(dialog).findByText("已判断检索方式，准备查找相关资料")).toBeInTheDocument();
    expect(await within(dialog).findByRole("heading", { name: "回答摘要" })).toBeInTheDocument();
    expect(within(dialog).queryByText(/stage:/)).not.toBeInTheDocument();
    expect(within(dialog).getByText("使用已发布知识库")).toBeInTheDocument();
    expect(within(dialog).getByText("chunk evidence")).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "查看证据与 Trace" })).toBeInTheDocument();
    expect(within(dialog).queryByText("引用来源")).not.toBeInTheDocument();

    fireEvent.click(within(dialog).getByRole("button", { name: "查看证据与 Trace" }));
    // v1.3: 证据面板内联在右栏
    expect(await within(dialog).findByText("证据 & Trace")).toBeInTheDocument();
    expect(within(dialog).getByText("guide.md")).toBeInTheDocument();
    expect(within(dialog).getByText("Markdown 渲染")).toBeInTheDocument();
    expect(within(dialog).getByText("0.880")).toBeInTheDocument();
    expect(within(dialog).getAllByText("Markdown 片段命中内容").length).toBeGreaterThan(0);
    expect(within(dialog).getByText("查询范围")).toBeInTheDocument();
    expect(within(dialog).getAllByText("识别为知识库问答").length).toBeGreaterThan(0);
    vi.unstubAllGlobals();
  });

  it("renders assistant markdown with GFM tables, images, emphasis, and dividers", async () => {
    const fetchMock = vi.fn(async (url: string) => {
      if (url === "/api/v1/kb") {
        return new Response(JSON.stringify({
          data: [
            {
              id: "kb-published",
              name: "已发布知识库",
              description: "可用于聊天",
              owner_id: "u1",
              status: "published",
            },
          ],
        }));
      }
      return new Response(
        'event: answer.delta\ndata: {"payload":{"text":"## 知识库概览\\n\\n**核心主题**：RAG 与微调。\\n\\n| 模块 | 说明 |\\n| --- | --- |\\n| RAG | 外部知识检索 |\\n\\n---\\n\\n![架构图](https://example.com/architecture.png)"}}\n\n' +
          'event: answer.completed\ndata: {"payload":{"results":[]}}\n\n',
      );
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "打开 Recall 助手" }));
    const dialog = screen.getByRole("dialog", { name: "Recall 助手" });

    fireEvent.change(await within(dialog).findByLabelText("输入问题"), {
      target: { value: "这个知识库主要包含什么？" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "发送" }));

    expect(await within(dialog).findByRole("heading", { name: "知识库概览" })).toBeInTheDocument();
    expect(within(dialog).getByText("核心主题").tagName).toBe("STRONG");
    expect(within(dialog).getByRole("table")).toBeInTheDocument();
    expect(within(dialog).getByRole("img", { name: "架构图" })).toHaveAttribute(
      "src",
      "https://example.com/architecture.png",
    );
    expect(within(dialog).queryByText("**核心主题**")).not.toBeInTheDocument();
    vi.unstubAllGlobals();
  });

  it("sends topK and optional context history from chat controls", async () => {
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (url === "/api/v1/kb") {
        return new Response(JSON.stringify({
          data: [
            {
              id: "kb-published",
              name: "已发布知识库",
              description: "可用于聊天",
              owner_id: "u1",
              status: "published",
            },
          ],
        }));
      }
      if (url === "/api/v1/retrieval/search/stream" && init?.method === "POST") {
        return new Response(
          'event: answer.delta\ndata: {"request_id":"req-chat","payload":{"text":"回答"}}\n\n' +
            'event: answer.completed\ndata: {"request_id":"req-chat","payload":{"results":[]}}\n\n',
        );
      }
      return new Response(JSON.stringify({ data: [] }));
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "打开 Recall 助手" }));
    const dialog = screen.getByRole("dialog", { name: "Recall 助手" });

    expect(await within(dialog).findByLabelText("关联上下文")).not.toBeChecked();
    expect(await within(dialog).findByLabelText("生成温度")).toHaveValue("0.2");
    fireEvent.change(within(dialog).getByLabelText("输入问题"), { target: { value: "第一问" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "发送" }));
    await within(dialog).findByText("回答");

    fireEvent.change(within(dialog).getByLabelText("检索条数"), { target: { value: "8" } });
    fireEvent.change(within(dialog).getByLabelText("生成温度"), { target: { value: "0.7" } });
    fireEvent.click(within(dialog).getByLabelText("关联上下文"));
    fireEvent.change(within(dialog).getByLabelText("输入问题"), { target: { value: "第二问" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "发送" }));

    await waitFor(() => expect(fetchMock.mock.calls.filter(([url]) => url === "/api/v1/retrieval/search/stream")).toHaveLength(2));
    const streamCalls = fetchMock.mock.calls.filter(([url]) => url === "/api/v1/retrieval/search/stream");
    const secondPayload = JSON.parse(String(streamCalls[1][1]?.body));

    expect(secondPayload.top_k).toBe(8);
    expect(secondPayload.temperature).toBe(0.7);
    expect(secondPayload.use_context).toBe(true);
    expect(secondPayload.history_questions).toEqual(["第一问"]);
    vi.unstubAllGlobals();
  });

  it("enables DeepSearch and shows visible decomposition steps", async () => {
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (url === "/api/v1/kb") {
        return new Response(JSON.stringify({
          data: [
            {
              id: "kb-published",
              name: "已发布知识库",
              description: "可用于聊天",
              owner_id: "u1",
              status: "published",
            },
          ],
        }));
      }
      if (url === "/api/v1/retrieval/search/stream" && init?.method === "POST") {
        return new Response(
          'event: request.created\ndata: {"request_id":"req-deep","payload":{"input":"小程序上线后白屏","summary":"收到问题"}}\n\n' +
            'event: retrieval.progress\ndata: {"request_id":"req-deep","payload":{"stage":"deep_search_planning","summary":"深度检索会拆分问题并多轮检索，可能需要更久"}}\n\n' +
            'event: deep_search.plan\ndata: {"request_id":"req-deep","payload":{"intent":"排查小程序上线后白屏","cot_plan":["识别故障现象","拆分检索方向"],"sub_questions":["是否是构建或发布配置导致白屏？"]}}\n\n' +
            'event: deep_search.step\ndata: {"request_id":"req-deep","payload":{"index":1,"sub_question":"是否是构建或发布配置导致白屏？","hit_count":1,"top_hits":[{"chunk_id":"chunk-build","title":"发布配置","score":0.91}]}}\n\n' +
            'event: answer.delta\ndata: {"request_id":"req-deep","payload":{"text":"检查发布配置。","chunk_id":"chunk-build"}}\n\n' +
            'event: answer.completed\ndata: {"request_id":"req-deep","payload":{"results":[{"chunk_id":"chunk-build","document_name":"release.md","title":"发布配置","content":"检查发布配置","score":0.91}]}}\n\n',
        );
      }
      return new Response(JSON.stringify({ data: [] }));
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "打开 Recall 助手" }));
    const dialog = screen.getByRole("dialog", { name: "Recall 助手" });

    const deepSearchCheckbox = await within(dialog).findByLabelText("DeepSearch 深度检索");
    expect(deepSearchCheckbox).not.toBeChecked();
    fireEvent.click(deepSearchCheckbox);
    expect(within(dialog).getByText("会拆分问题并多轮检索，耗时会更长")).toBeInTheDocument();
    fireEvent.change(within(dialog).getByLabelText("输入问题"), { target: { value: "小程序上线后白屏" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "发送" }));

    expect(await within(dialog).findByText("深度检索会拆分问题并多轮检索，可能需要更久")).toBeInTheDocument();
    expect(await within(dialog).findByText("DeepSearch：排查小程序上线后白屏")).toBeInTheDocument();
    expect(await within(dialog).findByText("子问题 1：是否是构建或发布配置导致白屏？")).toBeInTheDocument();
    expect(await within(dialog).findByText("命中 1 条资料")).toBeInTheDocument();
    expect(await within(dialog).findByText("最高相关：发布配置")).toBeInTheDocument();

    const streamCall = fetchMock.mock.calls.find(([url]) => url === "/api/v1/retrieval/search/stream");
    const payload = JSON.parse(String(streamCall?.[1]?.body));
    expect(payload.deep_search_enabled).toBe(true);
    vi.unstubAllGlobals();
  });
});
