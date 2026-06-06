/**
 * Recall · 知识库列表 hook
 *
 * 封装拉取 KB 列表 + 加载状态机。
 * 各业务页面（KB 列表 / 文档录入 / 效果评测 / 聊天抽屉）都通过本 hook 获取 KB。
 *
 * @author lvdaxianerplus
 */
import { useEffect, useState } from "react";

import { listKnowledgeBases } from "../api/kb";
import type { KnowledgeBase } from "../api/types";

/**
 * 加载状态枚举。
 * - `idle`     初始
 * - `loading`  首次加载中
 * - `success`  加载完成且有数据
 * - `empty`    加载完成但 0 条
 * - `error`    加载失败
 * - `retrying` 手动重试中（区别于首次 loading，避免 UI 闪烁）
 *
 * @author lvdaxianerplus
 */
export type LoadStatus = "idle" | "loading" | "success" | "empty" | "error" | "retrying";

/**
 * useKnowledgeBases 返回值。
 *
 * @author lvdaxianerplus
 */
export interface UseKnowledgeBasesResult {
  /** KB 列表 */
  items: KnowledgeBase[];
  /** 当前加载状态 */
  status: LoadStatus;
  /** 是否首次加载中 */
  isLoading: boolean;
  /** 是否处于错误状态 */
  isError: boolean;
  /** 手动触发重试 */
  refetch: () => Promise<void>;
}

/**
 * 知识库列表 hook。
 *
 * @param ownerId 可选的所有者 id 过滤
 * @returns KB 列表 + 状态 + refetch
 * @author lvdaxianerplus
 */
export function useKnowledgeBases(ownerId?: string): UseKnowledgeBasesResult {
  const [items, setItems] = useState<KnowledgeBase[]>([]);
  const [status, setStatus] = useState<LoadStatus>("idle");

  /**
   * 拉取 KB 列表，并把结果写入 state。
   *
   * @param nextStatus 切换到的下一状态
   * @author lvdaxianerplus
   */
  async function load(nextStatus: LoadStatus = "loading"): Promise<void> {
    setStatus(nextStatus);
    try {
      // 1. 调 API
      const data = await listKnowledgeBases(ownerId);
      // 2. 写入 state + 根据长度切到 success / empty
      setItems(data);
      setStatus(data.length > 0 ? "success" : "empty");
    } catch {
      // 静默吞错：UI 通过 isError / status 自行提示
      setStatus("error");
    }
  }

  // 首次进入或 ownerId 变化时重新拉取
  useEffect(() => {
    void load("loading");
  }, [ownerId]);

  return {
    items,
    status,
    // loading + retrying 都算"加载中"（给 UI 一个统一的判断）
    isLoading: status === "loading" || status === "retrying",
    isError: status === "error",
    refetch: () => load("retrying"),
  };
}
