import { useState } from "react";

import { createKnowledgeBase, deleteKnowledgeBase, getKnowledgeBaseSettings, publishKnowledgeBase, updateKnowledgeBaseSettings } from "../../api/kb";
import type { KnowledgeBase, KnowledgeBaseSettings } from "../../api/types";
import { EmptyState } from "../../components/common/EmptyState";
import { ErrorState } from "../../components/common/ErrorState";
import { LoadingState } from "../../components/common/LoadingState";
import { SectionCard } from "../../components/common/SectionCard";
import { StatusBadge } from "../../components/common/StatusBadge";
import { useKnowledgeBases } from "../../hooks/useKnowledgeBases";
import { KnowledgeBaseDetailPage } from "./KnowledgeBaseDetailPage";

export function KnowledgeBaseListPage() {
  const { items, isLoading, isError, status, refetch } = useKnowledgeBases();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [submitStatus, setSubmitStatus] = useState<"idle" | "loading" | "error">("idle");
  const [publishingId, setPublishingId] = useState<string | null>(null);
  const [publishErrorId, setPublishErrorId] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [deleteErrorId, setDeleteErrorId] = useState<string | null>(null);
  const [deleteMessage, setDeleteMessage] = useState<string | null>(null);
  const [selectedKbId, setSelectedKbId] = useState<string | null>(null);
  const [settingsKb, setSettingsKb] = useState<KnowledgeBase | null>(null);
  const [settings, setSettings] = useState<KnowledgeBaseSettings | null>(null);
  const [settingsStatus, setSettingsStatus] = useState<"idle" | "loading" | "success" | "error">("idle");
  const [settingsSaveStatus, setSettingsSaveStatus] = useState<"idle" | "loading" | "success" | "error">("idle");
  const publishedCount = items.filter((item) => item.status === "published").length;
  const pendingCount = items.filter((item) => !["published", "deleted", "archived"].includes(item.status)).length;

  async function handleCreate() {
    setSubmitStatus("loading");
    try {
      await createKnowledgeBase({ name, description, owner_id: "default" });
      setName("");
      setDescription("");
      setSubmitStatus("idle");
      await refetch();
    } catch {
      setSubmitStatus("error");
    }
  }

  async function handlePublish(kbId: string) {
    setPublishingId(kbId);
    setPublishErrorId(null);
    try {
      await publishKnowledgeBase(kbId, "default");
      await refetch();
    } catch {
      setPublishErrorId(kbId);
    } finally {
      setPublishingId(null);
    }
  }

  async function handleDelete(kbId: string) {
    setDeletingId(kbId);
    setDeleteErrorId(null);
    setDeleteMessage(null);
    try {
      const deleted = await deleteKnowledgeBase(kbId, "default");
      setDeleteMessage(
        `删除完成，已清理 ${deleted.deleted_document_count ?? 0} 个文档 / ${deleted.deleted_chunk_count ?? 0} 个 Chunk`,
      );
      await refetch();
    } catch {
      setDeleteErrorId(kbId);
    } finally {
      setDeletingId(null);
    }
  }

  async function handleOpenSettings(item: KnowledgeBase) {
    setSettingsKb(item);
    setSettings(null);
    setSettingsStatus("loading");
    setSettingsSaveStatus("idle");
    try {
      setSettings(await getKnowledgeBaseSettings(item.id));
      setSettingsStatus("success");
    } catch {
      setSettingsStatus("error");
    }
  }

  async function handleSaveSettings() {
    if (!settingsKb || !settings) {
      return;
    }
    setSettingsSaveStatus("loading");
    try {
      const updated = await updateKnowledgeBaseSettings(settingsKb.id, {
        semantic_chunking_enabled: settings.semantic_chunking_enabled,
        chunk_size: settings.chunk_size,
        overlap: settings.overlap,
        top_k_default: settings.top_k_default,
        max_heading_depth: settings.max_heading_depth,
        llm_planning_timeout_ms: settings.llm_planning_timeout_ms,
      });
      setSettings(updated);
      setSettingsSaveStatus("success");
    } catch {
      setSettingsSaveStatus("error");
    }
  }

  const selectedKb = items.find((item) => item.id === selectedKbId) ?? null;

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
    <div className="page-grid">
      <section className="page-hero">
        <div>
          <span>Knowledge Assets</span>
          <h2>知识资产概览</h2>
          <p>管理知识库、发布状态、文档证据和可检索范围。</p>
        </div>
        <div className="summary-strip" aria-label="知识库概览">
          <div>
            <span>总量</span>
            <strong>{items.length} 个知识库</strong>
          </div>
          <div>
            <span>发布库</span>
            <strong>{publishedCount} 个已发布</strong>
          </div>
          <div>
            <span>待处理</span>
            <strong>{pendingCount} 个待发版</strong>
          </div>
        </div>
      </section>
      <SectionCard title="知识库">
        <div className="kb-command-bar">
          <div className="form-inline">
            <label className="form-field">
              <span>知识库名称</span>
              <input placeholder="例如：产品知识库" value={name} onChange={(event) => setName(event.target.value)} />
            </label>
            <label className="form-field">
              <span>描述</span>
              <input placeholder="这批内容覆盖什么问题域" value={description} onChange={(event) => setDescription(event.target.value)} />
            </label>
          </div>
          <div className="toolbar">
            <button className="button" type="button" onClick={handleCreate} disabled={!name || submitStatus === "loading"}>
              {submitStatus === "loading" ? "创建中" : "创建知识库"}
            </button>
            <button className="button button--secondary" type="button" onClick={refetch}>
              刷新
            </button>
          </div>
        </div>
        {isLoading ? <LoadingState label="加载知识库中" /> : null}
        {isError ? <ErrorState title="加载失败" onRetry={refetch} /> : null}
        {submitStatus === "error" ? <ErrorState title="创建失败" onRetry={handleCreate} /> : null}
        {deleteMessage ? <div className="state-surface">{deleteMessage}</div> : null}
        {status === "empty" ? <EmptyState title="暂无知识库" description="创建后即可上传 Markdown 文档。" /> : null}
        {items.length > 0 ? (
          <div className="kb-card-grid">
            {items.map((item) => (
              <article className="kb-card" key={item.id}>
                <div className="kb-card__header">
                  <strong>{item.name}</strong>
                  <div className="kb-card__header-actions">
                    <button
                      aria-label={`设置 ${item.name}`}
                      className="icon-button"
                      type="button"
                      onClick={() => handleOpenSettings(item)}
                    >
                      ⚙
                    </button>
                    <div className="kb-card__status">
                      <span>发版状态</span>
                      <StatusBadge status={item.status} />
                    </div>
                  </div>
                </div>
                <p>{item.description || "无描述"}</p>
                <div className="kb-card__meta">
                  <span>Chat scope: {item.status === "published" ? "enabled" : "pending publish"}</span>
                </div>
                <div className="kb-card__actions">
                  <button
                    aria-label={`查看文档 ${item.name}`}
                    className="button button--secondary"
                    type="button"
                    onClick={() => setSelectedKbId(item.id)}
                  >
                    查看文档
                  </button>
                  {item.status !== "published" && item.status !== "deleted" && item.status !== "archived" ? (
                    <button
                      aria-label={`发布 ${item.name}`}
                      className="button button--secondary"
                      type="button"
                      disabled={publishingId === item.id}
                      onClick={() => handlePublish(item.id)}
                    >
                      {publishingId === item.id ? "发布中" : publishErrorId === item.id ? "重试发布" : "发布"}
                    </button>
                  ) : null}
                  {item.status !== "deleted" && item.status !== "archived" ? (
                    <button
                      aria-label={`删除知识库 ${item.name}`}
                      className="button button--danger"
                      type="button"
                      disabled={deletingId === item.id}
                      onClick={() => handleDelete(item.id)}
                    >
                      {deletingId === item.id ? "删除中" : deleteErrorId === item.id ? "重试删除" : "删除"}
                    </button>
                  ) : null}
                </div>
              </article>
            ))}
          </div>
        ) : null}
      </SectionCard>
      {settingsKb ? (
        <aside
          aria-label={`${settingsKb.name} 分块设置`}
          aria-modal="true"
          className="settings-dialog"
          role="dialog"
        >
          <div className="settings-dialog__panel">
            <div className="settings-dialog__header">
              <div>
                <span>知识库设置</span>
                <strong>{settingsKb.name} 分块设置</strong>
              </div>
              <button className="icon-button" type="button" onClick={() => setSettingsKb(null)}>
                关闭
              </button>
            </div>
            {settingsStatus === "loading" ? <LoadingState label="加载分块设置中" /> : null}
            {settingsStatus === "error" ? <ErrorState title="分块设置加载失败" onRetry={() => handleOpenSettings(settingsKb)} /> : null}
            {settings ? (
              <div className="kb-settings-panel">
                <label className="check-row">
                  <input
                    aria-label="Semantic chunking"
                    checked={settings.semantic_chunking_enabled}
                    type="checkbox"
                    onChange={(event) => setSettings({ ...settings, semantic_chunking_enabled: event.target.checked })}
                  />
                  <span>启用语义分块规划</span>
                </label>
                <label className="form-field">
                  <span>Chunk size</span>
                  <input
                    aria-label="Chunk size"
                    max={8000}
                    min={200}
                    type="number"
                    value={settings.chunk_size}
                    onChange={(event) => setSettings({ ...settings, chunk_size: Number(event.target.value) })}
                  />
                </label>
                <label className="form-field">
                  <span>Overlap</span>
                  <input
                    aria-label="Overlap"
                    min={0}
                    type="number"
                    value={settings.overlap}
                    onChange={(event) => setSettings({ ...settings, overlap: Number(event.target.value) })}
                  />
                </label>
                <label className="form-field">
                  <span>Default topK</span>
                  <input
                    aria-label="Default topK"
                    max={50}
                    min={1}
                    type="number"
                    value={settings.top_k_default}
                    onChange={(event) => setSettings({ ...settings, top_k_default: Number(event.target.value) })}
                  />
                </label>
                <label className="form-field">
                  <span>Max heading depth</span>
                  <select
                    aria-label="Max heading depth"
                    value={settings.max_heading_depth}
                    onChange={(event) => setSettings({ ...settings, max_heading_depth: Number(event.target.value) })}
                  >
                    <option value={1}>1</option>
                    <option value={2}>2</option>
                    <option value={3}>3</option>
                  </select>
                </label>
                <label className="form-field">
                  <span>LLM planning timeout</span>
                  <input
                    aria-label="LLM planning timeout"
                    max={30000}
                    min={1000}
                    type="number"
                    value={settings.llm_planning_timeout_ms}
                    onChange={(event) => setSettings({ ...settings, llm_planning_timeout_ms: Number(event.target.value) })}
                  />
                </label>
                <button className="button" disabled={settingsSaveStatus === "loading"} type="button" onClick={handleSaveSettings}>
                  {settingsSaveStatus === "loading" ? "保存中" : "保存分块设置"}
                </button>
                {settingsSaveStatus === "success" ? <EmptyState title="分块设置已保存" description="后续文档解析会使用新的知识库设置。" /> : null}
                {settingsSaveStatus === "error" ? <ErrorState title="分块设置保存失败" onRetry={handleSaveSettings} /> : null}
              </div>
            ) : null}
          </div>
        </aside>
      ) : null}
    </div>
  );
}
