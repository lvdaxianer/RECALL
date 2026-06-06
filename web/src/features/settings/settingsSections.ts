/**
 * Recall · 设置页菜单定义
 *
 * v1.5 起菜单搬至全局侧栏（AppShell），本页只根据 URL hash 决定渲染哪个子项。
 * 把配置集中维护，避免 SETTINGS_NAV (AppShell) 与 SETTINGS_SECTIONS (SettingsPage) 重复。
 *
 * @author lvdaxianerplus
 */
export const SETTINGS_SECTIONS = [
  {
    group: "知识",
    items: [
      { id: "answer-cache", label: "答案缓存", summary: "管理可复用问答结果、信任权重和缓存失效。" },
      { id: "synonyms", label: "同义词", summary: "维护全局或知识库级 query 同义词，提升缓存和检索命中。" },
    ],
  },
  {
    group: "性能",
    items: [
      { id: "rerank-cache", label: "重排缓存", summary: "预留重排候选治理与缓存观测能力。" },
      { id: "vector-cache", label: "向量缓存", summary: "预留 embedding 与向量命中缓存配置。" },
    ],
  },
  {
    group: "系统",
    items: [
      { id: "model-config", label: "模型配置", summary: "预留模型供应商、生成参数与安全阈值配置。" },
      { id: "retrieval-policy", label: "检索策略", summary: "预留 query scope、route plan 与召回策略配置。" },
      { id: "service-health", label: "服务健康", summary: "预留 ES、Milvus、Rerank 与 LLM 健康巡检。" },
    ],
  },
] as const;

/**
 * 展平的设置项集合。
 *
 * @author lvdaxianerplus
 */
export const ALL_SETTINGS_SECTIONS: readonly (typeof SETTINGS_SECTIONS)[number]["items"][number][] =
  SETTINGS_SECTIONS.reduce<
    (typeof SETTINGS_SECTIONS)[number]["items"][number][]
  >((acc, group) => [...acc, ...group.items], []);

/**
 * 单个设置项的 ID 类型。
 *
 * @author lvdaxianerplus
 */
export type SettingsItem = (typeof ALL_SETTINGS_SECTIONS)[number];
export type SettingsSectionId = SettingsItem["id"];

/**
 * 默认展示的设置子项。
 *
 * @author lvdaxianerplus
 */
export const DEFAULT_SECTION: SettingsSectionId = "answer-cache";

/**
 * 所有 section id 的字符串数组，用于 hash 解析。
 *
 * @author lvdaxianerplus
 */
export const SECTION_IDS: readonly string[] = ALL_SETTINGS_SECTIONS.map((section) => section.id);
