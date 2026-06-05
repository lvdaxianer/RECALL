import { useEffect, useState } from "react";

import { listKnowledgeBases } from "../api/kb";
import type { KnowledgeBase } from "../api/types";

export type LoadStatus = "idle" | "loading" | "success" | "empty" | "error" | "retrying";

export function useKnowledgeBases(ownerId?: string) {
  const [items, setItems] = useState<KnowledgeBase[]>([]);
  const [status, setStatus] = useState<LoadStatus>("idle");

  async function load(nextStatus: LoadStatus = "loading") {
    setStatus(nextStatus);
    try {
      const data = await listKnowledgeBases(ownerId);
      setItems(data);
      setStatus(data.length > 0 ? "success" : "empty");
    } catch {
      setStatus("error");
    }
  }

  useEffect(() => {
    void load("loading");
  }, [ownerId]);

  return {
    items,
    status,
    isLoading: status === "loading" || status === "retrying",
    isError: status === "error",
    refetch: () => load("retrying"),
  };
}
