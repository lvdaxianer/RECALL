/**
 * Recall · 知识库列表页
 *
 * 视图编排：
 * 1. 顶部：PageHeader + 3 个指标卡
 * 2. 创建表单 SectionCard（名称 / 描述 / 提交）
 * 3. 列表 SectionCard（KbListView：行 + 操作 + 错误条）
 * 4. 弹层：KbSettingsSheet（分块设置） + DeleteConfirmDialog（删除确认）
 * 5. 选中 KB 后切到 KnowledgeBaseDetailPage
 *
 * 子组件：KbListView / KbSettingsSheet / KnowledgeBaseDetailPage / DeleteConfirmDialog
 *
 * 设计要点：
 * - 全部错误通过 setXxxError 暴露到 UI，catch 内静默但留下错误消息
 * - handleSaveSettings / handlePublish / handleDelete 都用 finally 清理 loading id
 * - 错误用 publishErrorId / deleteErrorId 标记"哪一行出错"，KbListView 渲染错误条
 *
 * @author lvdaxianerplus
 */
import { useState } from "react";
import { RefreshCw } from "lucide-react";

import { createKnowledgeBase, deleteKnowledgeBase, publishKnowledgeBase } from "../../api/kb";
import type { KnowledgeBase } from "../../api/types";
import { EmptyState } from "../../components/common/EmptyState";
import { ErrorState } from "../../components/common/ErrorState";
import { LoadingState } from "../../components/common/LoadingState";
import { SectionCard } from "../../components/common/SectionCard";
import { MetricStrip } from "../../components/recall/MetricStrip";
import { PageHeader } from "../../components/recall/PageHeader";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { useKnowledgeBases } from "../../hooks/useKnowledgeBases";
import {
  DEFAULT_USER_ID,
  KB_STATUS,
} from "../chat/runtime/chatConstants";
import { KbListView } from "./KbListView";
import { KbSettingsSheet } from "./KbSettingsSheet";
import { KnowledgeBaseDetailPage } from "./KnowledgeBaseDetailPage";

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
 * 删除确认弹层。
 *
 * @author lvdaxianerplus
 */
interface DeleteConfirmDialogProps {
  target: KnowledgeBase | null;
  deleting: boolean;
  onCancel: () => void;
  onConfirm: (item: KnowledgeBase) => void;
}
function DeleteConfirmDialog({ target, deleting, onCancel, onConfirm }: DeleteConfirmDialogProps) {
  if (!target) {
    return null;
  }
  return (
    <div
      aria-label="删除知识库"
      className="fixed inset-0 z-50 grid place-items-center bg-slate-900/40 p-4"
      role="dialog"
    >
      <div className="w-full max-w-md rounded-xl border border-slate-200 bg-white p-5 shadow-xl">
        <h2 className="text-base font-semibold text-slate-900">删除知识库</h2>
        <p className="mt-3 text-sm text-slate-600">
          确认删除「<strong className="font-semibold text-slate-900">{target.name}</strong>」？
          相关文档和 Chunk 会同步清理，且
          <strong className="font-semibold text-red-700">不可恢复</strong>。
        </p>
        <div className="mt-5 flex items-center justify-end gap-2">
          <Button type="button" variant="outline" onClick={onCancel}>
            取消
          </Button>
          <Button
            aria-label={`确认删除 ${target.name}`}
            disabled={deleting}
            type="button"
            variant="destructive"
            onClick={() => onConfirm(target)}
          >
            {deleting ? "删除中" : "确认删除"}
          </Button>
        </div>
      </div>
    </div>
  );
}

/**
 * 知识库列表页：创建、发布、删除、设置分块。
 *
 * @author lvdaxianerplus
 */
export function KnowledgeBaseListPage() {
  const { items, isLoading, isError, status, refetch } = useKnowledgeBases();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [submitStatus, setSubmitStatus] = useState<"idle" | "loading" | "error">("idle");
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [publishingId, setPublishingId] = useState<string | null>(null);
  const [publishErrorId, setPublishErrorId] = useState<string | null>(null);
  const [publishErrorMessage, setPublishErrorMessage] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [deleteErrorId, setDeleteErrorId] = useState<string | null>(null);
  const [deleteErrorMessage, setDeleteErrorMessage] = useState<string | null>(null);
  const [deleteMessage, setDeleteMessage] = useState<string | null>(null);
  const [selectedKbId, setSelectedKbId] = useState<string | null>(null);
  const [settingsKb, setSettingsKb] = useState<KnowledgeBase | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<KnowledgeBase | null>(null);
  const publishedCount = items.filter((item) => item.status === KB_STATUS.PUBLISHED).length;
  const pendingCount = items.filter(
    (item) => !(KB_STATUS.PUBLISHED === item.status || KB_STATUS.DELETED === item.status || KB_STATUS.ARCHIVED === item.status),
  ).length;
  const selectedKb = items.find((item) => item.id === selectedKbId) ?? null;

  /**
   * 创建知识库。失败时把错误信息写入 submitError 供 UI 展示。
   *
   * @author lvdaxianerplus
   */
  async function handleCreate(): Promise<void> {
    setSubmitStatus("loading");
    setSubmitError(null);
    try {
      await createKnowledgeBase({ name, description, owner_id: DEFAULT_USER_ID });
      setName("");
      setDescription("");
      setSubmitStatus("idle");
      await refetch();
    } catch (error) {
      setSubmitStatus("error");
      setSubmitError(getErrorMessage(error, "创建失败，请稍后重试"));
    }
  }

  /**
   * 发布知识库。失败时记录目标 KB id 与错误信息。
   *
   * @author lvdaxianerplus
   */
  async function handlePublish(kbId: string): Promise<void> {
    setPublishingId(kbId);
    setPublishErrorId(null);
    setPublishErrorMessage(null);
    try {
      await publishKnowledgeBase(kbId, DEFAULT_USER_ID);
      await refetch();
    } catch (error) {
      setPublishErrorId(kbId);
      setPublishErrorMessage(getErrorMessage(error, "发布失败，请稍后重试"));
    } finally {
      setPublishingId(null);
    }
  }

  /**
   * 删除知识库。成功时展示已清理的文档/Chunk 数量，失败时记录错误。
   *
   * @author lvdaxianerplus
   */
  async function handleDelete(kbId: string): Promise<void> {
    setDeletingId(kbId);
    setDeleteErrorId(null);
    setDeleteErrorMessage(null);
    setDeleteMessage(null);
    try {
      const deleted = await deleteKnowledgeBase(kbId, DEFAULT_USER_ID);
      setDeleteMessage(
        `删除完成，已清理 ${deleted.deleted_document_count ?? 0} 个文档 / ${deleted.deleted_chunk_count ?? 0} 个 Chunk`,
      );
      await refetch();
    } catch (error) {
      setDeleteErrorId(kbId);
      setDeleteErrorMessage(getErrorMessage(error, "删除失败，请稍后重试"));
    } finally {
      setDeletingId(null);
    }
  }

  if (selectedKb) {
    return (
      <KnowledgeBaseDetailPage
        kbId={selectedKb.id}
        kbName={selectedKb.name}
        onBack={() => setSelectedKbId(null)}
        onUploaded={refetch}
      />
    );
  }

  return (
    <div className="space-y-4">
      <PageHeader
        eyebrow="Knowledge Assets"
        title="知识资产概览"
        description="管理知识库、发布状态、文档证据和可检索范围。"
      />
      <MetricStrip
        items={[
          { label: "总量", value: `${items.length} 个知识库` },
          { label: "发布库", value: `${publishedCount} 个已发布` },
          { label: "待处理", value: `${pendingCount} 个待发版` },
        ]}
      />
      <SectionCard>
        <div className="grid gap-4 lg:grid-cols-[1fr_auto] lg:items-end">
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="grid gap-1.5">
              <span className="text-sm font-medium text-slate-900">知识库名称</span>
              <Input placeholder="例如：产品知识库" value={name} onChange={(event) => setName(event.target.value)} />
            </label>
            <label className="grid gap-1.5">
              <span className="text-sm font-medium text-slate-900">描述</span>
              <Input
                placeholder="这批内容覆盖什么问题域"
                value={description}
                onChange={(event) => setDescription(event.target.value)}
              />
            </label>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button type="button" onClick={handleCreate} disabled={!name || submitStatus === "loading"}>
              {submitStatus === "loading" ? "创建中" : "创建知识库"}
            </Button>
            <Button type="button" variant="secondary" onClick={refetch}>
              <RefreshCw aria-hidden="true" className="h-4 w-4" />
              刷新
            </Button>
          </div>
        </div>
        {isLoading ? <LoadingState label="加载知识库中" /> : null}
        {isError ? <ErrorState title="加载失败" onRetry={refetch} /> : null}
        {submitStatus === "error" ? (
          <ErrorState title="创建失败" description={submitError ?? undefined} onRetry={handleCreate} />
        ) : null}
        {deleteMessage ? (
          <div className="flex items-center gap-2.5 rounded-lg border border-slate-200 bg-slate-50 p-4 text-sm text-slate-600">
            {deleteMessage}
          </div>
        ) : null}
      </SectionCard>
      <SectionCard title="知识库" description={`共 ${items.length} 个`}>
        {status === "empty" ? <EmptyState title="暂无知识库" description="创建后即可上传 Markdown 文档。" /> : null}
        {items.length > 0 ? (
          <KbListView
            items={items}
            publishingId={publishingId}
            publishErrorId={publishErrorId}
            publishErrorMessage={publishErrorMessage}
            deletingId={deletingId}
            deleteErrorId={deleteErrorId}
            deleteErrorMessage={deleteErrorMessage}
            onOpenDetail={setSelectedKbId}
            onPublish={handlePublish}
            onOpenSettings={setSettingsKb}
            onDelete={setDeleteTarget}
          />
        ) : null}
      </SectionCard>
      <KbSettingsSheet settingsKb={settingsKb} onClose={() => setSettingsKb(null)} />
      <DeleteConfirmDialog
        deleting={deletingId === deleteTarget?.id}
        target={deleteTarget}
        onCancel={() => setDeleteTarget(null)}
        onConfirm={(item) => {
          setDeleteTarget(null);
          void handleDelete(item.id);
        }}
      />
    </div>
  );
}
