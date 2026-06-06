import { useEffect, useState } from "react";

import { getKnowledgeBaseSettings, updateKnowledgeBaseSettings } from "../../api/kb";
import type { KnowledgeBase, KnowledgeBaseSettings } from "../../api/types";
import { EmptyState } from "../../components/common/EmptyState";
import { ErrorState } from "../../components/common/ErrorState";
import { LoadingState } from "../../components/common/LoadingState";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "../../components/ui/sheet";
import { Slider } from "../../components/ui/slider";
import { Switch } from "../../components/ui/switch";

/**
 * KB 分块设置弹层 props。
 *
 * @author lvdaxianerplus
 */
export interface KbSettingsSheetProps {
  /** 目标 KB；为 null 时弹层关闭。 */
  settingsKb: KnowledgeBase | null;
  /** 关闭弹层回调。 */
  onClose: () => void;
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
 * 数字 + 滑块的设置项：左侧 Slider 拖拽，右侧 Input 精确输入。
 *
 * @author lvdaxianerplus
 */
interface SettingsNumberFieldProps {
  id: string;
  label: string;
  min: number;
  max: number;
  step: number;
  value: number;
  onChange: (next: number) => void;
}
function SettingsNumberField({ id, label, min, max, step, value, onChange }: SettingsNumberFieldProps) {
  return (
    <div className="grid gap-1.5">
      <label className="text-sm font-medium text-slate-900" htmlFor={id}>
        {label}
      </label>
      <div className="grid gap-3 sm:grid-cols-[1fr_120px]">
        <Slider
          aria-label={`${label} slider`}
          max={max}
          min={min}
          step={step}
          value={[value]}
          onValueChange={([next]) => onChange(next ?? value)}
        />
        <Input
          aria-label={label}
          id={id}
          max={max}
          min={min}
          type="number"
          value={value}
          onChange={(event) => onChange(Number(event.target.value))}
        />
      </div>
    </div>
  );
}

/**
 * 重新加载 KB 分块设置。供 useEffect / 错误重试共用。
 *
 * @param kbId 目标 KB id
 * @param setStatus 状态 setter
 * @param setError 错误信息 setter
 * @param setSettings 设置 setter
 * @author lvdaxianerplus
 */
async function loadKbSettings(
  kbId: string,
  setStatus: (status: "loading" | "success" | "error") => void,
  setError: (message: string | null) => void,
  setSettings: (settings: KnowledgeBaseSettings) => void,
): Promise<void> {
  setStatus("loading");
  setError(null);
  try {
    setSettings(await getKnowledgeBaseSettings(kbId));
    setStatus("success");
  } catch (err) {
    setStatus("error");
    setError(getErrorMessage(err, "加载分块设置失败"));
  }
}

/**
 * KB 分块设置弹层。
 *
 * @param props.settingsKb 目标 KB
 * @param props.onClose 关闭回调
 * @author lvdaxianerplus
 */
export function KbSettingsSheet({ settingsKb, onClose }: KbSettingsSheetProps) {
  const [settings, setSettings] = useState<KnowledgeBaseSettings | null>(null);
  const [status, setStatus] = useState<"idle" | "loading" | "success" | "error">("idle");
  const [error, setError] = useState<string | null>(null);
  const [saveStatus, setSaveStatus] = useState<"idle" | "loading" | "success" | "error">("idle");
  const [saveError, setSaveError] = useState<string | null>(null);

  // 切换 KB 时重新加载设置；弹层关闭时清理状态。
  useEffect(() => {
    if (!settingsKb) {
      setSettings(null);
      setStatus("idle");
      setError(null);
      setSaveStatus("idle");
      setSaveError(null);
      return;
    }
    if (settings?.knowledge_base_id === settingsKb.id) {
      return;
    }
    void loadKbSettings(settingsKb.id, setStatus, setError, setSettings);
  }, [settingsKb, settings?.knowledge_base_id]);

  /**
   * 提交保存分块设置。
   *
   * @author lvdaxianerplus
   */
  async function handleSave(): Promise<void> {
    if (!settingsKb || !settings) {
      return;
    }
    setSaveStatus("loading");
    setSaveError(null);
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
      setSaveStatus("success");
    } catch (err) {
      setSaveStatus("error");
      setSaveError(getErrorMessage(err, "保存分块设置失败"));
    }
  }

  return (
    // 弹层：右侧 Sheet，宽度 576px（sm:max-w-xl）
    <Sheet
      open={Boolean(settingsKb)}
      onOpenChange={(open) => {
        if (!open) {
          onClose();
        }
      }}
    >
      <SheetContent className="flex flex-col gap-0 overflow-y-auto p-0 sm:max-w-xl" side="right">
        {/* 顶部：标题 + 副标题 */}
        <SheetHeader className="border-b border-slate-200 p-5">
          <SheetDescription>知识库设置</SheetDescription>
          <SheetTitle className="text-base font-semibold text-slate-900">
            {settingsKb ? `${settingsKb.name} · 分块设置` : "配置知识库检索默认参数"}
          </SheetTitle>
        </SheetHeader>
        {/* 主体：状态分派 + 表单 */}
        <div className="min-h-0 flex-1 space-y-4 p-5">
          {/* 加载中状态 */}
          {status === "loading" ? <LoadingState label="加载分块设置中" /> : null}
          {/* 加载失败：提供重试回调 */}
          {status === "error" && settingsKb ? (
            <ErrorState
              description={error ?? undefined}
              title="分块设置加载失败"
              onRetry={() => {
                if (!settingsKb) {
                  return;
                }
                void loadKbSettings(settingsKb.id, setStatus, setError, setSettings);
              }}
            />
          ) : null}
          {/* 加载成功：展示可编辑表单 */}
          {settings ? (
            <div className="grid gap-4">
              {/* 语义分块开关：与其它分块字段解耦，单独 toggle */}
              <label className="flex items-center justify-between gap-4 rounded-lg border border-slate-200 p-3">
                <span className="text-sm font-medium text-slate-900">启用语义分块规划</span>
                <Switch
                  aria-label="Semantic chunking"
                  checked={settings.semantic_chunking_enabled}
                  onCheckedChange={(checked) =>
                    setSettings({ ...settings, semantic_chunking_enabled: checked })
                  }
                />
              </label>
              {/* 数字字段走"Slider + Input"双控件（见 SettingsNumberField） */}
              <SettingsNumberField
                id="kb-chunk-size"
                label="Chunk size"
                max={8000}
                min={200}
                step={100}
                value={settings.chunk_size}
                onChange={(next) => setSettings({ ...settings, chunk_size: next })}
              />
              <SettingsNumberField
                id="kb-overlap"
                label="Overlap"
                max={1000}
                min={0}
                step={10}
                value={settings.overlap}
                onChange={(next) => setSettings({ ...settings, overlap: next })}
              />
              {/* 简单数字字段：topK */}
              <label className="grid gap-1.5">
                <span className="text-sm font-medium text-slate-900">Default topK</span>
                <Input
                  aria-label="Default topK"
                  max={50}
                  min={1}
                  type="number"
                  value={settings.top_k_default}
                  onChange={(event) => setSettings({ ...settings, top_k_default: Number(event.target.value) })}
                />
              </label>
              {/* heading depth 用 select 限定 1-3 档位 */}
              <label className="grid gap-1.5">
                <span className="text-sm font-medium text-slate-900">Max heading depth</span>
                <select
                  aria-label="Max heading depth"
                  className="h-9 rounded-md border border-slate-200 bg-white px-3 text-sm focus-visible:border-emerald-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500"
                  value={settings.max_heading_depth}
                  onChange={(event) =>
                    setSettings({ ...settings, max_heading_depth: Number(event.target.value) })
                  }
                >
                  <option value={1}>1</option>
                  <option value={2}>2</option>
                  <option value={3}>3</option>
                </select>
              </label>
              {/* LLM 规划超时：单位 ms，范围 1000-30000 */}
              <label className="grid gap-1.5">
                <span className="text-sm font-medium text-slate-900">LLM planning timeout</span>
                <Input
                  aria-label="LLM planning timeout"
                  max={30000}
                  min={1000}
                  type="number"
                  value={settings.llm_planning_timeout_ms}
                  onChange={(event) =>
                    setSettings({ ...settings, llm_planning_timeout_ms: Number(event.target.value) })
                  }
                />
              </label>
              {saveStatus === "success" ? (
                <EmptyState title="分块设置已保存" description="后续文档解析会使用新的知识库设置。" />
              ) : null}
              {saveStatus === "error" ? (
                <ErrorState
                  title="分块设置保存失败"
                  description={saveError ?? undefined}
                  onRetry={handleSave}
                />
              ) : null}
            </div>
          ) : null}
        </div>
        <div className="flex items-center justify-end gap-2 border-t border-slate-200 bg-slate-50/40 p-4">
          <Button type="button" variant="outline" onClick={onClose}>
            取消
          </Button>
          <Button disabled={saveStatus === "loading"} type="button" onClick={handleSave}>
            {saveStatus === "loading" ? "保存中" : "保存分块设置"}
          </Button>
        </div>
      </SheetContent>
    </Sheet>
  );
}
