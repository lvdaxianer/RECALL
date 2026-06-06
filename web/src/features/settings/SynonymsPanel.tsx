/**
 * Recall · 同义词维护面板
 *
 * 包含三块：创建表单（标准词 / 同义词 / 作用范围）+ 同义词组列表。
 * 列表项支持内联编辑（标准词 / 同义词）+ 启用开关 + 保存 / 删除。
 *
 * 设计要点：
 * 1. parseTerms 把"中英文逗号 + 换行"统一切成 string[]
 * 2. 作用范围（global / kb）影响后端写入；kb 模式额外需要选 KB
 * 3. 列表项内部维护 canonical / terms 局部 state，useEffect 同步远端变化
 * 4. toggle 状态 PATCH 立即生效（不带 message 提示）
 * 5. 所有错误用 message Alert 统一展示
 *
 * 子组件：SynonymGroupRow（内联编辑行）
 *
 * @author lvdaxianerplus
 */
import { useEffect, useState } from "react";

import {
  createSynonymGroup,
  deleteSynonymGroup,
  listSynonymGroups,
  updateSynonymGroup,
  type SynonymGroup,
} from "../../api/synonyms";
import { listKnowledgeBases } from "../../api/kb";
import type { KnowledgeBase } from "../../api/types";
import { ErrorState } from "../../components/common/ErrorState";
import { LoadingState } from "../../components/common/LoadingState";
import { Alert, AlertDescription } from "../../components/ui/alert";
import { Button } from "../../components/ui/button";
import { Card, CardContent, CardDescription, CardHeader } from "../../components/ui/card";
import { Input } from "../../components/ui/input";
import { Switch } from "../../components/ui/switch";
import { Textarea } from "../../components/ui/textarea";
import { DEFAULT_USER_ID } from "../chat/runtime/chatConstants";

/**
 * 同义词作用域。
 *
 * @author lvdaxianerplus
 */
type SynonymScope = "global" | "kb";

/**
 * 把 textarea 文本解析为同义词数组。支持中英文逗号与换行分隔。
 *
 * @param value 原始 textarea 文本
 * @returns 清洗后的同义词数组
 * @author lvdaxianerplus
 */
function parseTerms(value: string): string[] {
  return value
    .split(/[\n,，]/)
    .map((term) => term.trim())
    .filter(Boolean);
}

/**
 * 单个同义词组编辑行。
 *
 * @author lvdaxianerplus
 */
interface SynonymGroupRowProps {
  group: SynonymGroup;
  onDelete: (group: SynonymGroup) => Promise<void>;
  onSave: (group: SynonymGroup, nextCanonical: string, nextTerms: string) => Promise<void>;
  onToggle: (group: SynonymGroup, enabled: boolean) => Promise<void>;
}
function SynonymGroupRow({ group, onDelete, onSave, onToggle }: SynonymGroupRowProps) {
  const [canonical, setCanonical] = useState(group.canonical);
  const [terms, setTerms] = useState(group.terms.join(", "));

  useEffect(() => {
    setCanonical(group.canonical);
    setTerms(group.terms.join(", "));
  }, [group]);

  return (
    <Card>
      <CardContent className="grid gap-4 pt-6">
        <div>
          <strong className="block text-sm font-semibold text-slate-900">{group.canonical}</strong>
          <span className="text-sm text-slate-500">{group.terms.join(" / ")}</span>
        </div>
        <div className="grid gap-1.5">
          <label className="text-sm font-medium text-slate-900">编辑标准词</label>
          <Input
            aria-label={`编辑标准词 ${group.id}`}
            value={canonical}
            onChange={(event) => setCanonical(event.target.value)}
          />
        </div>
        <div className="grid gap-1.5">
          <label className="text-sm font-medium text-slate-900">编辑同义词</label>
          <Textarea
            aria-label={`编辑同义词 ${group.id}`}
            rows={2}
            value={terms}
            onChange={(event) => setTerms(event.target.value)}
          />
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <label className="inline-flex items-center gap-2 text-sm">
            <Switch
              aria-label={`${group.enabled ? "禁用" : "启用"}同义词组 ${group.id}`}
              checked={group.enabled}
              onCheckedChange={(checked) => void onToggle(group, checked === true)}
            />
            <span>{group.enabled ? "启用中" : "已禁用"}</span>
          </label>
          <Button type="button" variant="secondary" onClick={() => void onSave(group, canonical, terms)}>
            保存同义词组 {group.id}
          </Button>
          <Button type="button" variant="destructive" onClick={() => void onDelete(group)}>
            删除同义词组 {group.id}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

/**
 * 同义词维护面板。
 *
 * @author lvdaxianerplus
 */
export function SynonymsPanel() {
  const [groups, setGroups] = useState<SynonymGroup[]>([]);
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([]);
  const [status, setStatus] = useState<"idle" | "loading" | "success" | "error">("idle");
  const [scope, setScope] = useState<SynonymScope>("global");
  const [selectedKbId, setSelectedKbId] = useState("");
  const [canonical, setCanonical] = useState("");
  const [termsText, setTermsText] = useState("");
  const [message, setMessage] = useState("");

  useEffect(() => {
    void loadSynonyms();
    void loadKnowledgeBases();
  }, []);

  /**
   * 加载同义词组。
   *
   * @author lvdaxianerplus
   */
  async function loadSynonyms(): Promise<void> {
    setStatus("loading");
    try {
      setGroups(await listSynonymGroups());
      setStatus("success");
    } catch {
      setStatus("error");
      setMessage("同义词加载失败");
    }
  }

  /**
   * 加载可选 KB。
   *
   * @author lvdaxianerplus
   */
  async function loadKnowledgeBases(): Promise<void> {
    try {
      setKnowledgeBases(await listKnowledgeBases());
    } catch {
      setKnowledgeBases([]);
    }
  }

  /**
   * 创建同义词组。
   *
   * @author lvdaxianerplus
   */
  async function handleCreate(): Promise<void> {
    setMessage("");
    try {
      const created = await createSynonymGroup({
        canonical,
        terms: parseTerms(termsText),
        knowledge_base_id: scope === "kb" ? selectedKbId : null,
        owner_id: DEFAULT_USER_ID,
        enabled: true,
      });
      setGroups((current) => [created, ...current]);
      setCanonical("");
      setTermsText("");
      setMessage("同义词组已创建");
    } catch {
      setMessage("同义词组创建失败");
    }
  }

  /**
   * 保存同义词组。
   *
   * @author lvdaxianerplus
   */
  async function handleSave(group: SynonymGroup, nextCanonical: string, nextTerms: string): Promise<void> {
    setMessage("");
    try {
      const updated = await updateSynonymGroup(group.id, {
        canonical: nextCanonical,
        terms: parseTerms(nextTerms),
        enabled: group.enabled,
      });
      setGroups((current) => current.map((item) => (item.id === updated.id ? updated : item)));
      setMessage("同义词组已保存");
    } catch {
      setMessage("同义词组保存失败");
    }
  }

  /**
   * 切换同义词组启用状态。
   *
   * @author lvdaxianerplus
   */
  async function handleToggle(group: SynonymGroup, enabled: boolean): Promise<void> {
    setMessage("");
    try {
      const updated = await updateSynonymGroup(group.id, { enabled });
      setGroups((current) => current.map((item) => (item.id === updated.id ? updated : item)));
    } catch {
      setMessage("同义词组状态切换失败");
    }
  }

  /**
   * 删除同义词组。
   *
   * @author lvdaxianerplus
   */
  async function handleDelete(group: SynonymGroup): Promise<void> {
    setMessage("");
    try {
      await deleteSynonymGroup(group.id);
      setGroups((current) => current.filter((item) => item.id !== group.id));
      setMessage("同义词组已删除");
    } catch {
      setMessage("同义词组删除失败");
    }
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-3 border-b border-slate-200">
        <div>
          <CardDescription>Synonyms</CardDescription>
          <h3 className="text-lg font-semibold text-slate-900">同义词维护</h3>
          <p className="mt-2 text-sm text-slate-500">
            同义词会进入答案缓存 key 和检索 query，知识库级规则优先于全局规则。
          </p>
        </div>
        <Button type="button" variant="secondary" onClick={() => void loadSynonyms()}>
          刷新
        </Button>
      </CardHeader>
      <CardContent className="space-y-4 pt-6">
        <div className="grid gap-4 md:grid-cols-2">
          <div className="grid gap-1.5">
            <label className="text-sm font-medium text-slate-900" htmlFor="syn-canonical">标准词</label>
            <Input id="syn-canonical" aria-label="标准词" value={canonical} onChange={(event) => setCanonical(event.target.value)} />
          </div>
          <div className="grid gap-1.5 md:col-span-2">
            <label className="text-sm font-medium text-slate-900" htmlFor="syn-terms">同义词</label>
            <Textarea
              id="syn-terms"
              aria-label="同义词"
              rows={3}
              value={termsText}
              onChange={(event) => setTermsText(event.target.value)}
            />
          </div>
          <div className="grid gap-1.5">
            <label className="text-sm font-medium text-slate-900" htmlFor="syn-scope">作用范围</label>
            <select
              id="syn-scope"
              aria-label="作用范围"
              className="h-9 rounded-md border border-slate-200 bg-white px-3 text-sm transition-colors focus-visible:border-emerald-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500"
              value={scope}
              onChange={(event) => setScope(event.target.value as SynonymScope)}
            >
              <option value="global">全局</option>
              <option value="kb">知识库</option>
            </select>
          </div>
          {scope === "kb" ? (
            <div className="grid gap-1.5">
              <label className="text-sm font-medium text-slate-900" htmlFor="syn-kb">知识库</label>
              <select
                id="syn-kb"
                aria-label="同义词知识库"
                className="h-9 rounded-md border border-slate-200 bg-white px-3 text-sm transition-colors focus-visible:border-emerald-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500"
                value={selectedKbId}
                onChange={(event) => setSelectedKbId(event.target.value)}
              >
                <option value="">请选择知识库</option>
                {knowledgeBases.map((item) => (
                  <option key={item.id} value={item.id}>{item.name}</option>
                ))}
              </select>
            </div>
          ) : null}
          <div className="flex items-end">
            <Button type="button" onClick={() => void handleCreate()} disabled={!canonical || !termsText}>
              创建同义词组
            </Button>
          </div>
        </div>
        {status === "loading" ? <LoadingState label="加载同义词中" /> : null}
        {status === "error" ? <ErrorState title="同义词加载失败" onRetry={() => void loadSynonyms()} /> : null}
        {message ? (
          <Alert>
            <AlertDescription>{message}</AlertDescription>
          </Alert>
        ) : null}
        {status === "success" && groups.length === 0 ? (
          <Alert>
            <AlertDescription>暂无同义词组。创建后会立即用于 query 归一化。</AlertDescription>
          </Alert>
        ) : null}
        {groups.length > 0 ? (
          <div className="space-y-3">
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
      </CardContent>
    </Card>
  );
}
