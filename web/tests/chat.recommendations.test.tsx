import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ChatMessage, type ChatMessageViewModel } from "../src/features/chat/components/ChatMessage";

/**
 * 构造用于推荐区测试的助手消息。
 *
 * @param trace - 后端事件流
 * @returns 助手消息视图模型
 * @author lvdaxianerplus
 * @date 2026-06-06
 */
function assistantMessage(trace: ChatMessageViewModel["trace"]): ChatMessageViewModel {
  return {
    id: "assistant-1",
    role: "assistant",
    content: "适配器模式用于把不兼容接口转换成客户端期望的接口。",
    status: "success",
    trace,
    requestId: "req-1",
  };
}

describe("chat recommendations", () => {
  it("renders total duration and stage durations from answer completed events", () => {
    render(
      <ChatMessage
        message={{
          ...assistantMessage([
            {
              event_id: "evt-answer",
              event: "answer.completed",
              user_id: "default",
              session_id: null,
              run_id: null,
              request_id: "req-1",
              sequence: 1,
              created_at: "",
              payload: {
                duration_ms: 5180,
                answer_cache_hit: false,
                stage_durations_ms: {
                  retrieval: 180,
                  answer_generation: 5000,
                },
                results: [],
              },
            },
          ]),
          durationMs: 9999,
        }}
        onFeedback={vi.fn()}
        onOpenEvidence={vi.fn()}
      />,
    );

    expect(screen.getByText("总耗时 5.18s")).toBeInTheDocument();
    expect(screen.getByText("检索 180ms")).toBeInTheDocument();
    expect(screen.getByText("回答生成 5.00s")).toBeInTheDocument();
  });

  it("renders cache hit timing in a glanceable way", () => {
    render(
      <ChatMessage
        message={assistantMessage([
          {
            event_id: "evt-answer",
            event: "answer.completed",
            user_id: "default",
            session_id: null,
            run_id: null,
            request_id: "req-1",
            sequence: 1,
            created_at: "",
            payload: {
              duration_ms: 4,
              answer_cache_hit: true,
              stage_durations_ms: {
                answer_cache: 4,
              },
              results: [],
            },
          },
        ])}
        onFeedback={vi.fn()}
        onOpenEvidence={vi.fn()}
      />,
    );

    expect(screen.getByText("总耗时 4ms")).toBeInTheDocument();
    expect(screen.getByText("命中缓存 4ms")).toBeInTheDocument();
  });

  it("renders document cards and topic navigation cards together", () => {
    render(
      <ChatMessage
        message={assistantMessage([
          {
            event_id: "evt-rec",
            event: "recommendation.completed",
            user_id: "default",
            session_id: null,
            run_id: null,
            request_id: "req-1",
            sequence: 1,
            created_at: "",
            payload: {
              recommendations: [
                {
                  kind: "document",
                  metadata: { id: "doc-1", document_name: "Java 设计模式.md" },
                  description: "Java 设计模式.md",
                  score: 0.9,
                  reason: "同类主题资料",
                  topic_path: ["Java", "设计模式", "结构型模式"],
                },
                {
                  kind: "topic",
                  metadata: { id: "topic-structural" },
                  description: "继续了解结构型模式的整体脉络",
                  score: 0.66,
                  reason: "上位主题可帮助建立整体框架",
                  topic_path: ["Java", "设计模式", "结构型模式"],
                  follow_up_question: "继续了解结构型模式的整体脉络",
                },
              ],
            },
          },
        ])}
        onFeedback={vi.fn()}
        onOpenEvidence={vi.fn()}
      />,
    );

    expect(screen.getByText("你可能还想看")).toBeInTheDocument();
    expect(screen.getByText("文档推荐")).toBeInTheDocument();
    expect(screen.getByText("主题导航")).toBeInTheDocument();
    expect(screen.getByText("Java 设计模式.md")).toBeInTheDocument();
    expect(screen.getByText("继续了解结构型模式的整体脉络")).toBeInTheDocument();
  });

  it("renders late recommendation events after answer content is already visible", () => {
    const { rerender } = render(
      <ChatMessage
        message={assistantMessage([
          {
            event_id: "evt-answer",
            event: "answer.completed",
            user_id: "default",
            session_id: null,
            run_id: null,
            request_id: "req-1",
            sequence: 1,
            created_at: "",
            payload: { results: [] },
          },
        ])}
        onFeedback={vi.fn()}
        onOpenEvidence={vi.fn()}
      />,
    );

    expect(screen.getByText(/适配器模式用于/)).toBeInTheDocument();
    expect(screen.queryByText("你可能还想看")).not.toBeInTheDocument();

    rerender(
      <ChatMessage
        message={assistantMessage([
          {
            event_id: "evt-answer",
            event: "answer.completed",
            user_id: "default",
            session_id: null,
            run_id: null,
            request_id: "req-1",
            sequence: 1,
            created_at: "",
            payload: { results: [] },
          },
          {
            event_id: "evt-rec",
            event: "recommendation.completed",
            user_id: "default",
            session_id: null,
            run_id: null,
            request_id: "req-1",
            sequence: 2,
            created_at: "",
            payload: {
              recommendations: [
                {
                  kind: "topic",
                  metadata: { id: "topic-structural" },
                  description: "继续了解结构型模式",
                  score: 0.66,
                  reason: "上位主题可帮助建立整体框架",
                  topic_path: ["Java", "设计模式", "结构型模式"],
                  follow_up_question: "继续了解结构型模式",
                },
              ],
            },
          },
        ])}
        onFeedback={vi.fn()}
        onOpenEvidence={vi.fn()}
      />,
    );

    expect(screen.getByText(/适配器模式用于/)).toBeInTheDocument();
    expect(screen.getByText("你可能还想看")).toBeInTheDocument();
    expect(screen.getByText("继续了解结构型模式")).toBeInTheDocument();
  });
});
