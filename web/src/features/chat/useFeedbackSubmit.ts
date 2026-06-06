import { useCallback, useRef, useState } from "react";

import { sendAnswerFeedback } from "../../api/retrieval";
import { streamAssistantAnswer } from "./streamAssistantAnswer";
import { DEFAULT_USER_ID } from "./runtime/chatConstants";
import { findPreviousUserQuestion, type ChatMessage } from "./runtime/chatModels";
import {
  buildMessageCompleteHandler,
  buildMessageProgressHandler,
} from "./runtime/streamHandlers";

/**
 * 反馈提交 hook 入参。
 *
 * @author lvdaxianerplus
 */
export interface UseFeedbackSubmitParams {
  messages: ChatMessage[];
  selectedKbIds: string[];
  activeSessionId: string;
  topK: number;
  temperature: number;
  useContext: boolean;
  updateMessage: (messageId: string, patch: Partial<ChatMessage>) => void;
  setStreamState: (state: Parameters<typeof streamAssistantAnswer>[0] extends never ? never : import("../../hooks/useRetrievalStream").StreamState) => void;
  /** 反馈落地完成时的副作用（用于清理 pendingFeedback 队列）。 */
  onSettled?: () => void;
}

/**
 * useFeedbackSubmit 返回值。
 *
 * @author lvdaxianerplus
 */
export interface UseFeedbackSubmitResult {
  pendingFeedback: Record<string, "like" | "dislike">;
  handleFeedback: (messageId: string, requestId: string | null | undefined, vote: "like" | "dislike") => Promise<void>;
  /**
   * 在流式回答完成时调用：消费等待中的反馈并提交。
   *
   * @author lvdaxianerplus
   */
  flushPendingFeedback: (messageId: string, requestId: string | null | undefined) => Promise<void>;
}

/**
 * 反馈提交 hook：负责点赞/点踩与点踩后的重新检索。
 *
 * @param params 入参
 * @author lvdaxianerplus
 */
export function useFeedbackSubmit(params: UseFeedbackSubmitParams): UseFeedbackSubmitResult {
  const { messages, selectedKbIds, activeSessionId, topK, temperature, useContext, updateMessage, setStreamState } = params;
  const [pendingFeedback, setPendingFeedback] = useState<Record<string, "like" | "dislike">>({});
  // pendingFeedback 队列由 hook 自己持有；通过 setPendingFeedback 的 ref 让内部回调读到最新值。
  const pendingFeedbackRef = useRef(pendingFeedback);
  pendingFeedbackRef.current = pendingFeedback;

  /**
   * 提交点赞/点踩反馈。dislike 且 rerunOnDislike=true 时会重新跑一次流式。
   *
   * @author lvdaxianerplus
   */
  const submitFeedback = useCallback(
    async (
      messageId: string,
      requestId: string,
      vote: "like" | "dislike",
      options: { rerunOnDislike: boolean },
    ): Promise<void> => {
      try {
        const feedback = await sendAnswerFeedback({
          request_id: requestId,
          vote,
          user_id: DEFAULT_USER_ID,
        });
        if (vote === "dislike" && feedback.deleted !== true) {
          throw new Error("答案缓存未删除");
        }
        updateMessage(messageId, { feedbackStatus: vote === "like" ? "liked" : "disliked" });
        if (vote === "dislike" && options.rerunOnDislike) {
          const message = messages.find((item) => item.id === messageId);
          const question = message?.sourceQuestion ?? findPreviousUserQuestion(messages, messageId);
          const knowledgeBaseIds = message?.knowledgeBaseIds ?? selectedKbIds;
          if (!question || knowledgeBaseIds.length === 0) {
            throw new Error("缺少重新检索上下文");
          }
          updateMessage(messageId, {
            content: "",
            status: "streaming",
            trace: [],
            durationMs: undefined,
            requestId: null,
            showThinking: true,
          });
          await streamAssistantAnswer({
            question,
            assistantMessageId: messageId,
            knowledgeBaseIds,
            topK,
            temperature,
            useContext,
            userId: DEFAULT_USER_ID,
            sessionId: activeSessionId,
            onState: setStreamState,
            onProgress: buildMessageProgressHandler(messageId, (id, patch) => {
              updateMessage(id, patch);
            }),
            onComplete: buildMessageCompleteHandler(messageId, (id, patch) => {
              updateMessage(id, patch);
            }),
          });
        }
      } catch {
        updateMessage(messageId, { feedbackStatus: "error" });
      }
    },
    [messages, selectedKbIds, activeSessionId, topK, temperature, useContext, updateMessage, setStreamState],
  );

  /**
   * 消费等待中的反馈并立即提交。
   *
   * @param messageId 消息 id
   * @param requestId 请求 id（消息已落地时才有）
   * @author lvdaxianerplus
   */
  const flushPendingFeedback = useCallback(
    async (messageId: string, requestId: string | null | undefined) => {
      const vote = pendingFeedbackRef.current[messageId];
      if (!vote || !requestId) {
        return;
      }
      setPendingFeedback((current) => {
        const next = { ...current };
        delete next[messageId];
        return next;
      });
      await submitFeedback(messageId, requestId, vote, { rerunOnDislike: vote === "dislike" });
    },
    [submitFeedback],
  );

  /**
   * 处理点赞/点踩按钮点击。无 requestId 或消息仍在 streaming 时入队等待。
   *
   * @author lvdaxianerplus
   */
  const handleFeedback = useCallback(
    async (messageId: string, requestId: string | null | undefined, vote: "like" | "dislike") => {
      const message = messages.find((item) => item.id === messageId);
      if (!requestId || message?.status === "streaming") {
        setPendingFeedback((current) => ({ ...current, [messageId]: vote }));
        updateMessage(messageId, { feedbackStatus: "queued" });
        return;
      }
      await submitFeedback(messageId, requestId, vote, { rerunOnDislike: true });
    },
    [messages, submitFeedback, updateMessage],
  );

  return { pendingFeedback, handleFeedback, flushPendingFeedback };
}
