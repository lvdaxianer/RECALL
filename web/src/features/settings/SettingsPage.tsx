import { useEffect, useState } from "react";

import { listKnowledgeBases } from "../../api/kb";
import { deleteAnswerCache, listAnswerCache, type AnswerCacheRecord } from "../../api/retrieval";
import {
  createSynonymGroup,
  deleteSynonymGroup,
  listSynonymGroups,
  updateSynonymGroup,
  type SynonymGroup,
} from "../../api/synonyms";
import type { KnowledgeBase } from "../../api/types";
import { ErrorState } from "../../components/common/ErrorState";
import { LoadingState } from "../../components/common/LoadingState";

const SETTINGS_SECTIONS = [
  { id: "answer-cache", label: "答案缓存", summary: "管理可复用问答结果、信任权重和缓存失效。" },
  { id: "synonyms", label: "同义词", summary: "维护全局或知识库级 query 同义词，提升缓存和检索命中。" },
  { id: "rerank-cache", label: "重排缓存", summary: "预留重排候选治理与缓存观测能力。" },
  { id: "vector-cache", label: "向量缓存", summary: "预留 embedding 与向量命中缓存配置。" },
  { id: "model-config", label: "模型配置", summary: "预留模型供应商、生成参数与安全阈值配置。" },
  { id: "retrieval-policy", label: "检索策略", summary: "预留 query scope、route plan 与召回策略配置。" },
  { id: "service-health", label: "服务健康", summary: "预留 ES、Milvus、Rerank 与 LLM 健康巡检。" },
] as const;

type SettingsSectionId = (typeof SETTINGS_SECTIONS)[number]["id"];

export function SettingsPage() {
  const [activeSection, setActiveSection] = useState<SettingsSectionId>("answer-cache");
  const [items, setItems] = useState<AnswerCacheRecord[]>([]);
  const [status, setStatus] = useState<"idle" | "loading" | "success" | "error">("idle");
  const [message, setMessage] = useState("");

  useEffect(() => {
    void load();
  }, []);

  async function load() {
    setStatus("loading");
    setMessage("");
    try {
      const response = await listAnswerCache();
      setItems(response.items);
      setStatus("success");
    } catch {
      setStatus("error");
    }
  }

  async function handleDelete(item: AnswerCacheRecord) {
    setMessage("");
    try {
      await deleteAnswerCache(item.cache_key);
      setItems((current) => current.filter((record) => record.cache_key !== item.cache_key));
      setMessage("缓存已删除");
    } catch {
      setMessage("删除失败");
    }
  }

  return (
    <section className="settings-page">
      <div className="settings-page__header">
        <div>
          <span>系统治理</span>
          <h2>系统设置</h2>
          <p>集中管理检索链路的缓存、模型、策略和服务状态，先沉淀可直接运营的答案缓存能力。</p>
        </div>
      </div>

      <div className="settings-layout">
        <nav aria-label="设置菜单" className="settings-subnav">
          {SETTINGS_SECTIONS.map((section) => (
            <button
              key={section.id}
              aria-label={section.label}
              aria-current={activeSection === section.id ? "page" : undefined}
              className="settings-subnav__item"
              type="button"
              onClick={() => setActiveSection(section.id)}
            >
              <strong>{section.label}</strong>
              <span>{section.summary}</span>
            </button>
          ))}
        </nav>

        <div className="settings-content">
          {activeSection === "answer-cache" ? (
            <AnswerCachePanel
              items={items}
              message={message}
              onDelete={handleDelete}
              onReload={load}
              status={status}
            />
          ) : activeSection === "synonyms" ? (
            <SynonymsPanel />
          ) : (
            <SettingsPlaceholder section={SETTINGS_SECTIONS.find((section) => section.id === activeSection)!} />
          )}
        </div>
      </div>
    </section>
  );
}

function SynonymsPanel() {
  const [groups, setGroups] = useState<SynonymGroup[]>([]);
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([]);
  const [status, setStatus] = useState<"idle" | "loading" | "success" | "error">("idle");
  const [scope, setScope] = useState<"global" | "kb">("global");
  const [selectedKbId, setSelectedKbId] = useState("");
  const [canonical, setCanonical] = useState("");
  const [termsText, setTermsText] = useState("");
  const [message, setMessage] = useState("");

  useEffect(() => {
    void loadSynonyms();
    void loadKnowledgeBases();
  }, []);

  async function loadSynonyms() {
    setStatus("loading");
    try {
      setGroups(await listSynonymGroups());
      setStatus("success");
    } catch {
      setStatus("error");
    }
  }

  async function loadKnowledgeBases() {
    try {
      setKnowledgeBases(await listKnowledgeBases());
    } catch {
      setKnowledgeBases([]);
    }
  }

  async function handleCreate() {
    setMessage("");
    const created = await createSynonymGroup({
      canonical,
      terms: parseTerms(termsText),
      knowledge_base_id: scope === "kb" ? selectedKbId : null,
      owner_id: "default",
      enabled: true,
    });
    setGroups((current) => [created, ...current]);
    setCanonical("");
    setTermsText("");
    setMessage("同义词组已创建");
  }

  async function handleSave(group: SynonymGroup, nextCanonical: string, nextTerms: string) {
    const updated = await updateSynonymGroup(group.id, {
      canonical: nextCanonical,
      terms: parseTerms(nextTerms),
      enabled: group.enabled,
    });
    setGroups((current) => current.map((item) => (item.id === updated.id ? updated : item)));
    setMessage("同义词组已保存");
  }

  async function handleToggle(group: SynonymGroup, enabled: boolean) {
    const updated = await updateSynonymGroup(group.id, { enabled });
    setGroups((current) => current.map((item) => (item.id === updated.id ? updated : item)));
  }

  async function handleDelete(group: SynonymGroup) {
    await deleteSynonymGroup(group.id);
    setGroups((current) => current.filter((item) => item.id !== group.id));
    setMessage("同义词组已删除");
  }

  return (
    <section className="settings-synonyms-page">
      <div className="settings-cache-header">
        <div>
          <span>Synonyms</span>
          <h3>同义词维护</h3>
          <p>同义词会进入答案缓存 key 和检索 query，知识库级规则优先于全局规则。</p>
        </div>
        <button className="button button--secondary button--compact" type="button" onClick={() => void loadSynonyms()}>
          刷新
        </button>
      </div>

      <div className="synonym-form">
        <label className="form-field">
          <span>标准词</span>
          <input aria-label="标准词" value={canonical} onChange={(event) => setCanonical(event.target.value)} />
        </label>
        <label className="form-field">
          <span>同义词条</span>
          <textarea
            aria-label="同义词条"
            rows={3}
            value={termsText}
            onChange={(event) => setTermsText(event.target.value)}
          />
        </label>
        <label className="form-field">
          <span>作用范围</span>
          <select aria-label="作用范围" value={scope} onChange={(event) => setScope(event.target.value as "global" | "kb")}>
            <option value="global">全局</option>
            <option value="kb">知识库</option>
          </select>
        </label>
        {scope === "kb" ? (
          <label className="form-field">
            <span>知识库</span>
            <select
              aria-label="同义词知识库"
              value={selectedKbId}
              onChange={(event) => setSelectedKbId(event.target.value)}
            >
              <option value="">请选择知识库</option>
              {knowledgeBases.map((item) => (
                <option key={item.id} value={item.id}>{item.name}</option>
              ))}
            </select>
          </label>
        ) : null}
        <button className="button" type="button" onClick={() => void handleCreate()} disabled={!canonical || !termsText}>
          创建同义词组
        </button>
      </div>

      {status === "loading" ? <LoadingState label="加载同义词中" /> : null}
      {status === "error" ? <ErrorState title="同义词加载失败" onRetry={() => void loadSynonyms()} /> : null}
      {message ? <div className="state-surface">{message}</div> : null}
      {status === "success" && groups.length === 0 ? (
        <div className="state-surface state-surface--center">
          <strong>暂无同义词组</strong>
          <span>创建后会立即用于 query 归一化。</span>
        </div>
      ) : null}
      {groups.length > 0 ? (
        <div className="synonym-list">
          {groups.map((group) => (
            <SynonymGroupRow
              group={group}
              key={group.id}
              onDelete={handleDelete}
              onSave={handleSave}
              onToggle={handleToggle}
            />
          ))}
        </div>
      ) : null}
    </section>
  );
}

function SynonymGroupRow({
  group,
  onDelete,
  onSave,
  onToggle,
}: {
  group: SynonymGroup;
  onDelete: (group: SynonymGroup) => Promise<void>;
  onSave: (group: SynonymGroup, nextCanonical: string, nextTerms: string) => Promise<void>;
  onToggle: (group: SynonymGroup, enabled: boolean) => Promise<void>;
}) {
  const [canonical, setCanonical] = useState(group.canonical);
  const [terms, setTerms] = useState(group.terms.join(", "));

  useEffect(() => {
    setCanonical(group.canonical);
    setTerms(group.terms.join(", "));
  }, [group]);

  return (
    <article className="synonym-card">
      <div>
        <strong>{group.canonical}</strong>
        <span>{group.terms.join(" / ")}</span>
      </div>
      <label className="form-field">
        <span>编辑标准词</span>
        <input
          aria-label={`编辑标准词 ${group.id}`}
          value={canonical}
          onChange={(event) => setCanonical(event.target.value)}
        />
      </label>
      <label className="form-field">
        <span>编辑同义词</span>
        <textarea
          aria-label={`编辑同义词 ${group.id}`}
          rows={2}
          value={terms}
          onChange={(event) => setTerms(event.target.value)}
        />
      </label>
      <div className="synonym-card__actions">
        <label className="check-row">
          <input
            aria-label={`${group.enabled ? "禁用" : "启用"}同义词组 ${group.id}`}
            checked={group.enabled}
            type="checkbox"
            onChange={(event) => void onToggle(group, event.target.checked)}
          />
          <span>{group.enabled ? "启用中" : "已禁用"}</span>
        </label>
        <button className="button button--secondary button--compact" type="button" onClick={() => void onSave(group, canonical, terms)}>
          保存同义词组 {group.id}
        </button>
        <button className="button button--danger button--compact" type="button" onClick={() => void onDelete(group)}>
          删除同义词组 {group.id}
        </button>
      </div>
    </article>
  );
}

function parseTerms(value: string): string[] {
  return value
    .split(/[\n,，]/)
    .map((term) => term.trim())
    .filter(Boolean);
}

function AnswerCachePanel({
  items,
  message,
  onDelete,
  onReload,
  status,
}: {
  items: AnswerCacheRecord[];
  message: string;
  onDelete: (item: AnswerCacheRecord) => Promise<void>;
  onReload: () => Promise<void>;
  status: "idle" | "loading" | "success" | "error";
}) {
  return (
    <section className="settings-cache-page">
      <div className="settings-cache-header">
        <div>
          <span>Answer Cache</span>
          <h3>答案缓存管理</h3>
          <p>查看已沉淀的问答缓存、信任权重和命中次数，必要时手动删除缓存。</p>
        </div>
        <button className="button button--secondary button--compact" type="button" onClick={() => void onReload()}>
          刷新
        </button>
      </div>

      {status === "loading" ? <LoadingState label="加载答案缓存中" /> : null}
      {status === "error" ? <ErrorState title="答案缓存加载失败" onRetry={() => void onReload()} /> : null}
      {message ? <div className="state-surface">{message}</div> : null}
      {status === "success" && items.length === 0 ? (
        <div className="state-surface state-surface--center">
          <strong>暂无答案缓存</strong>
          <span>当聊天问答成功生成后，相同归一化问题会在这里沉淀为可复用缓存。</span>
        </div>
      ) : null}
      {items.length > 0 ? (
        <div className="answer-cache-table-wrap">
          <table className="answer-cache-table">
            <thead>
              <tr>
                <th>归一化问题</th>
                <th>答案预览</th>
                <th>指标</th>
                <th>过期时间</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.cache_key}>
                  <td>
                    <strong>{item.normalized_query}</strong>
                    <small>{item.knowledge_base_ids.length} 个知识库 · {item.citation_count} 条引用</small>
                  </td>
                  <td>{item.answer_preview}</td>
                  <td>
                    <span className="status-badge">命中 {item.hit_count} 次</span>
                    <span className="status-badge status-badge--published">信任 {item.trust_score}</span>
                  </td>
                  <td>{formatDate(item.expires_at)}</td>
                  <td>
                    <button
                      aria-label={`删除缓存 ${item.normalized_query}`}
                      className="button button--danger button--compact"
                      type="button"
                      onClick={() => void onDelete(item)}
                    >
                      删除
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </section>
  );
}

function SettingsPlaceholder({ section }: { section: (typeof SETTINGS_SECTIONS)[number] }) {
  return (
    <section className="settings-placeholder">
      <span>Reserved</span>
      <h3>{section.label}</h3>
      <p>{section.summary}</p>
      <div className="state-surface state-surface--center">
        <strong>该设置模块已预留，后续接入真实配置。</strong>
        <span>当前版本先开放答案缓存管理，避免半成品配置影响线上检索链路。</span>
      </div>
    </section>
  );
}

function formatDate(value: string): string {
  const timestamp = Date.parse(value);
  if (Number.isNaN(timestamp)) {
    return value;
  }
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(timestamp);
}
