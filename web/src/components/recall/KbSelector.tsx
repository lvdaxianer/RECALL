/**
 * Recall · 知识库多选组件
 *
 * 基于 Popover + Command (cmdk) 实现：触发按钮展示已选摘要，下拉面板支持搜索 + 多选。
 * 当前页 KB 范围选择、聊天范围选择都复用本组件。
 *
 * @author lvdaxianerplus
 */
import { Check, ChevronsUpDown } from "lucide-react";

import { cn } from "../../lib/utils";
import { Badge } from "../ui/badge";
import { Button } from "../ui/button";
import { Checkbox } from "../ui/checkbox";
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "../ui/command";
import { Popover, PopoverContent, PopoverTrigger } from "../ui/popover";

/**
 * 单个 KB 选项。
 *
 * @author lvdaxianerplus
 */
export interface KbSelectorOption {
  /** 显示名 */
  label: string;
  /** 唯一 id */
  value: string;
  /** 是否禁用（通常用于未发布 / 已归档 KB） */
  disabled?: boolean;
  /** 禁用原因，悬停/列表里展示给用户 */
  disabledReason?: string;
}

/**
 * KB 多选 props 集合。
 *
 * @author lvdaxianerplus
 */
export interface KbSelectorProps {
  /** 标签 */
  label: string;
  /** 选项列表 */
  options: KbSelectorOption[];
  /** 已选 value 列表 */
  values: string[];
  /** 选中状态变更回调 */
  onChange: (values: string[]) => void;
}

/**
 * 取已选选项的视图模型，按当前 value 顺序保持。
 *
 * @param options 全部选项
 * @param values 已选 value 列表
 * @returns 已选选项视图模型
 * @author lvdaxianerplus
 */
function pickSelected(options: KbSelectorOption[], values: string[]): KbSelectorOption[] {
  return options.filter((option) => values.includes(option.value));
}

/**
 * 切换某个 option 的选中状态：disabled 跳过；已选则移除，未选则追加。
 *
 * @param option 目标 option
 * @param values 当前已选 values
 * @param onChange 变更回调
 * @author lvdaxianerplus
 */
function toggleOption(
  option: KbSelectorOption,
  values: string[],
  onChange: (values: string[]) => void,
): void {
  if (option.disabled) {
    return;
  }
  if (values.includes(option.value)) {
    onChange(values.filter((item) => item !== option.value));
    return;
  }
  onChange([...values, option.value]);
}

/**
 * KB 多选组件。
 *
 * @param props.label 标签
 * @param props.options 选项列表
 * @param props.values 已选 value 列表
 * @param props.onChange 选中状态变更回调
 * @author lvdaxianerplus
 */
export function KbSelector({ label, options, values, onChange }: KbSelectorProps) {
  // 1. 计算已选 + 摘要展示文本
  const selectedOptions = pickSelected(options, values);
  const selectedSummary = selectedOptions.length > 0
    ? selectedOptions.map((option) => option.label).join("、")
    : "选择知识库";

  return (
    <div className="grid gap-2">
      <span className="text-sm font-medium">{label}</span>
      <Popover>
        {/* 触发器：用一个 outline 按钮承载已选摘要 + 折叠图标 */}
        <PopoverTrigger asChild>
          <Button
            aria-label="选择知识库"
            className="justify-between"
            role="combobox"
            type="button"
            variant="outline"
          >
            <span className="truncate">{selectedSummary}</span>
            <ChevronsUpDown aria-hidden="true" className="h-4 w-4 opacity-60" />
          </Button>
        </PopoverTrigger>
        {/* 弹层宽度：固定 360px，移动端自适应视口 */}
        <PopoverContent align="start" className="w-[min(360px,calc(100vw-2rem))] p-0">
          <Command>
            <CommandInput placeholder="搜索知识库" />
            <CommandList>
              <CommandEmpty>暂无可选知识库</CommandEmpty>
              <CommandGroup>
                {options.map((option) => {
                  // 当前是否已选，决定复选框视觉
                  const checked = values.includes(option.value);
                  return (
                    <CommandItem
                      // 透传 disabled 给 cmdk，避免其内部处理"被禁用"项的选中
                      aria-disabled={option.disabled}
                      data-disabled={option.disabled ? "true" : undefined}
                      disabled={option.disabled}
                      key={option.value}
                      value={option.label}
                      onSelect={() => toggleOption(option, values, onChange)}
                    >
                      {/* 复选框只用于视觉，tabIndex=-1 避免抢焦点 */}
                      <Checkbox aria-hidden="true" checked={checked} tabIndex={-1} />
                      <div className="min-w-0 flex-1">
                        <span className="block truncate">{option.label}</span>
                        {/* 禁用原因悬停时可见（cmdk 自身也会展示） */}
                        {option.disabledReason ? (
                          <span className="block truncate text-xs text-muted-foreground">
                            {option.disabledReason}
                          </span>
                        ) : null}
                      </div>
                      {checked ? <Check aria-hidden="true" className="h-4 w-4 text-primary" /> : null}
                    </CommandItem>
                  );
                })}
              </CommandGroup>
            </CommandList>
          </Command>
        </PopoverContent>
      </Popover>
      {/* 底部徽章：当前已选数量 + 提示作用 */}
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant="secondary">已选择 {values.length} 个</Badge>
      </div>
    </div>
  );
}
