import { useState } from "react";

import { uploadDocument } from "../../api/documents";
import { EmptyState } from "../../components/common/EmptyState";
import { ErrorState } from "../../components/common/ErrorState";
import { LoadingState } from "../../components/common/LoadingState";
import { SectionCard } from "../../components/common/SectionCard";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { Textarea } from "../../components/ui/textarea";
import { DEFAULT_USER_ID } from "../chat/runtime/chatConstants";

/**
 * 文档录入卡片 props。
 *
 * @author lvdaxianerplus
 */
export interface DocumentUploadCardProps {
  kbId: string;
  kbName?: string;
  onUploaded?: () => void | Promise<void>;
}

/**
 * 把任意 error 转成可展示字符串。
 *
 * @param error 异常对象
 * @param fallback 兜底文案
 * @author lvdaxianerplus
 */
function getErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message) {
    return error.message;
  }
  return fallback;
}

/**
 * 知识库文档录入卡片：选 KB（只读回显）→ 写 Markdown → 提交。
 *
 * @param props.kbId 目标 KB id
 * @param props.kbName 目标 KB 名称
 * @param props.onUploaded 录入完成回调
 * @author lvdaxianerplus
 */
export function DocumentUploadCard({ kbId, kbName, onUploaded }: DocumentUploadCardProps) {
  const [name, setName] = useState("");
  const [content, setContent] = useState("");
  const [status, setStatus] = useState<"idle" | "loading" | "success" | "error">("idle");
  const [error, setError] = useState<string | null>(null);

  /**
   * 提交文档上传。
   *
   * @author lvdaxianerplus
   */
  async function handleUpload(): Promise<void> {
    setStatus("loading");
    setError(null);
    try {
      await uploadDocument(kbId, {
        name,
        content,
        content_type: "text/markdown",
        owner_id: DEFAULT_USER_ID,
      });
      setStatus("success");
      setName("");
      setContent("");
      await onUploaded?.();
    } catch (err) {
      setStatus("error");
      setError(getErrorMessage(err, "录入失败，请稍后重试"));
    }
  }

  return (
    <SectionCard title="上传文档">
      {/* 顶部：目标 KB（只读回显，避免误传其他 KB） */}
      <div className="grid gap-1.5">
        <label className="text-sm font-medium text-slate-900" htmlFor="kb-target">
          目标知识库
        </label>
        <Input id="kb-target" readOnly value={kbId} />
      </div>
      {kbName ? <p className="text-sm text-slate-500">{kbName}</p> : null}
      {/* 中部：文档名 + Markdown 内容 */}
      <div className="mt-3 grid gap-1.5">
        <label className="text-sm font-medium text-slate-900" htmlFor="doc-name">
          文档名称
        </label>
        <Input
          id="doc-name"
          placeholder="README.md"
          value={name}
          onChange={(event) => setName(event.target.value)}
        />
      </div>
      <div className="mt-3 grid gap-1.5">
        <label className="text-sm font-medium text-slate-900" htmlFor="doc-content">
          Markdown 内容
        </label>
        <Textarea
          id="doc-content"
          placeholder="# 标题&#10;正文"
          rows={8}
          value={content}
          onChange={(event) => setContent(event.target.value)}
        />
      </div>
      {/* 底部：提交按钮 + 三态反馈 */}
      <Button
        className="mt-3"
        disabled={!name || !content || status === "loading"}
        type="button"
        onClick={handleUpload}
      >
        {status === "loading" ? "录入中" : "提交录入"}
      </Button>
      {status === "loading" ? <LoadingState label="正在写入检索索引" /> : null}
      {status === "error" ? (
        <ErrorState description={error ?? undefined} title="录入失败" onRetry={handleUpload} />
      ) : null}
      {status === "success" ? (
        <EmptyState description="文档已进入知识库和检索索引。" title="录入完成" />
      ) : null}
    </SectionCard>
  );
}
