/**
 * Recall · 聊天输入区
 *
 * 包含：检索条数 / 温度 / 关联上下文 / 输入框 / 发送。
 * v1.3 设计：底部悬浮 elevated card（白底 + 轻 shadow + 上方分隔线）。
 *
 * 选项值集中在 `runtime/chatConstants` 维护：
 * - `TOP_K_OPTIONS` 检索条数
 * - `TEMPERATURE_OPTIONS` 温度
 *
 * @author lvdaxianerplus
 */
import { ComposerPrimitive } from "@assistant-ui/react";
import { Send } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import { TEMPERATURE_OPTIONS, TOP_K_OPTIONS } from "../runtime/chatConstants";

/**
 * 聊天输入区 props 集合（参数较多时使用 props 对象 + 命名调用更可读）。
 *
 * @author lvdaxianerplus
 */
export interface ChatComposerProps {
  /** 输入框草稿 */
  draft: string;
  /** 检索条数（topK） */
  topK: number;
  /** 生成温度 */
  temperature: number;
  /** 是否关联上下文 */
  useContext: boolean;
  /** 是否可发送（业务态：KB 选好 + 草稿非空 + 不在 streaming） */
  canSend: boolean;
  /** 是否在流式生成中 */
  isStreaming: boolean;
  /** 已选 KB 数（仅展示用） */
  selectedKbCount: number;
  onDraftChange: (value: string) => void;
  onTopKChange: (value: number) => void;
  onTemperatureChange: (value: number) => void;
  onUseContextChange: (value: boolean) => void;
  onSend: () => void;
}

/**
 * 输入控件统一的 select 样式（白底 + slate 描边 + emerald 焦点环）。
 *
 * @author lvdaxianerplus
 */
const SELECT_CLASS = cn(
  // 基础：高度 / 圆角 / 边框 / 内边距
  "h-7 rounded-md border border-slate-200 bg-white px-2 text-xs",
  // 状态：hover 边框 / focus 环
  "transition-colors hover:border-slate-300",
  "focus-visible:border-emerald-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500",
);

/**
 * 聊天输入区组件。
 *
 * @param props 聊天输入区配置
 * @author lvdaxianerplus
 */
export function ChatComposer({
  draft,
  topK,
  temperature,
  useContext,
  canSend,
  isStreaming,
  selectedKbCount,
  onDraftChange,
  onTopKChange,
  onTemperatureChange,
  onUseContextChange,
  onSend,
}: ChatComposerProps) {
  return (
    // ComposerPrimitive 桥接 Assistant UI 的提交事件
    <ComposerPrimitive.Root
      className="grid shrink-0 grid-cols-1 gap-3 border-t border-slate-200 bg-white p-4 shadow-[0_-4px_12px_rgba(15,23,42,0.04)]"
      data-assistant-ui-composer="true"
      onSubmit={(event) => {
        // 阻止默认 form 提交，调用方 onSend 走流式检索
        event.preventDefault();
        if (canSend) {
          onSend();
        }
      }}
    >
      {/* 顶部控制条：topK / 温度 / 上下文 / 计数 */}
      <div className="col-span-full flex flex-wrap items-center gap-3">
        <label className="flex items-center gap-1.5 text-xs text-slate-500">
          <span>检索条数</span>
          <select
            aria-label="检索条数"
            className={SELECT_CLASS}
            value={topK}
            onChange={(event) => onTopKChange(Number(event.target.value))}
          >
            {TOP_K_OPTIONS.map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-1.5 text-xs text-slate-500">
          <span>温度</span>
          <select
            aria-label="生成温度"
            className={SELECT_CLASS}
            value={temperature}
            onChange={(event) => onTemperatureChange(Number(event.target.value))}
          >
            {TEMPERATURE_OPTIONS.map((value) => (
              <option key={value} value={value}>
                {value.toFixed(1)}
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-1.5 rounded-md px-1.5 text-xs text-slate-700 transition-colors hover:bg-slate-50">
          <Checkbox
            aria-label="关联上下文"
            checked={useContext}
            onCheckedChange={(checked) => onUseContextChange(checked === true)}
          />
          <span>关联上下文</span>
        </label>
        {/* 已选 KB 数（只读展示） */}
        <span className="ml-auto font-mono text-[11px] text-slate-400">
          已选 {selectedKbCount} 个已发布 KB
        </span>
      </div>
      {/* 输入框 */}
      <label className="col-span-full">
        <span className="sr-only">输入问题</span>
        <Textarea
          aria-label="输入问题"
          className="min-h-24 border-slate-200 bg-white transition-colors focus-visible:border-emerald-500"
          placeholder="输入问题，Shift + Enter 换行..."
          rows={3}
          value={draft}
          onChange={(event) => onDraftChange(event.target.value)}
        />
      </label>
      {/* 底部：发送按钮 */}
      <div className="col-span-full flex items-center justify-end gap-2">
        <Button
          className="shadow-sm transition-all hover:shadow-md"
          disabled={!canSend}
          type="submit"
        >
          <Send aria-hidden="true" className="h-4 w-4" />
          {isStreaming ? "生成中" : "发送"}
        </Button>
      </div>
    </ComposerPrimitive.Root>
  );
}
