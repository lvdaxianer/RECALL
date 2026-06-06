/**
 * Recall · 通用多选组件（KB 选择兼容 shim）
 *
 * 历史上多选功能直接写在这个文件里；v1.3 起改名为 `KbSelector`（带搜索 + 摘要展示），
 * 本文件继续作为 `components/common` 下的别名导出，保持外部模块调用稳定。
 *
 * @author lvdaxianerplus
 */
import { KbSelector, type KbSelectorOption } from "../recall/KbSelector";

/**
 * 多选选项（与 `KbSelectorOption` 保持完全一致的类型契约）。
 *
 * @author lvdaxianerplus
 */
export interface MultiselectOption extends KbSelectorOption {}

/**
 * Multiselect props（沿用 `KbSelector` 的命名，但 `value` 取代 `values` 以保持向后兼容）。
 *
 * @author lvdaxianerplus
 */
export interface MultiselectProps {
  /** 标签 */
  label: string;
  /** 选项列表 */
  options: MultiselectOption[];
  /** 已选 value 列表 */
  value: string[];
  /** 选中状态变更回调 */
  onChange: (value: string[]) => void;
}

/**
 * 通用多选组件（透传到 `KbSelector`）。
 *
 * @param props.label 标签
 * @param props.options 选项列表
 * @param props.value 已选 value 列表
 * @param props.onChange 选中状态变更回调
 * @author lvdaxianerplus
 */
export function Multiselect({ label, options, value, onChange }: MultiselectProps) {
  // 直接透传：common 目录保留旧 API 形状，避免外部模块破坏
  return <KbSelector label={label} options={options} values={value} onChange={onChange} />;
}
