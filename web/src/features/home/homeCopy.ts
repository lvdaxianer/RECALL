/**
 * Recall · 首页文案与展示数据
 *
 * 集中维护首页展示用的所有 copy + 展示数据，避免 HomePage.tsx 体积膨胀。
 *
 * @author lvdaxianerplus
 */

/**
 * 首页核心概念条目。
 *
 * @author lvdaxianerplus
 */
export const CORE_CONCEPTS = [
  {
    name: "rewrite query",
    detail: "把用户原始问题改写成更适合检索的查询表达。",
    role: "降低口语、缺省词和多意图问题带来的召回偏差。",
  },
  {
    name: "query scope",
    detail: "判断问题应该走概览、事实、配置还是故障定位。",
    role: "先确定检索范围和任务类型，避免每次都粗暴全量搜索。",
  },
  {
    name: "route_plan",
    detail: "把判断结果落成 summary-first、local chunk、hybrid 等检索路线。",
    role: "让概览类问题先看摘要，让精确问题直达证据片段。",
  },
  {
    name: "CoT Plan 可审计摘要",
    detail: "只展示可审计的规划摘要，不暴露模型内部隐式思维链。",
    role: "用户能看到系统如何规划检索，但不会泄露不可审计推理细节。",
  },
  {
    name: "cot cache",
    detail: "缓存规划摘要和稳定路由，重复问题不用每次重新规划。",
    role: "相似问题复用稳定决策，减少 LLM 规划耗时和抖动。",
  },
  {
    name: "score trace",
    detail: "记录 BM25、向量分、Rerank 分和命中策略。",
    role: "方便解释为什么这条证据被选中，以及排序为什么靠前。",
  },
] as const;

/**
 * 首页流程步骤条目。
 *
 * @author lvdaxianerplus
 */
export const FLOW_STEPS = [
  {
    title: "Query Scope",
    detail: "用 rewrite query 归一化问题，再判断问题是概览、事实、配置还是故障定位。",
  },
  {
    title: "Summary-first",
    detail: "概览类问题优先命中文档摘要与章节标题，避免把局部 chunk 当成整库结论。",
  },
  {
    title: "Parent / Section Expansion",
    detail: "命中片段后回收父章节与相邻上下文，让答案基于完整语义块，而不是孤立句子。",
  },
  {
    title: "ES + Milvus + Rerank",
    detail: "BM25、向量召回与 Rerank 组合治理候选集，再用知识库过滤保证只检索选中范围。",
  },
  {
    title: "Score Trace",
    detail: "每条结果带 route_plan、score_trace 与 rerank 状态，方便定位为什么命中、为什么排序靠前。",
  },
  {
    title: "流式问答输出",
    detail: "先返回 route_plan 与 score trace，再按 Markdown-aware delta 流式输出答案。",
  },
] as const;

/**
 * 首页缓存层条目。
 *
 * @author lvdaxianerplus
 */
export const CACHE_LAYERS = [
  {
    name: "Query Optimize Cache",
    detail: "缓存 rewrite query、query scope 与 route_plan，相似问题直接复用稳定规划。",
    effect: "减少重复 LLM 规划",
  },
  {
    name: "Embedding Cache",
    detail: "按归一化 query 缓存向量，重复查询不用再次请求 embedding 服务。",
    effect: "减少向量生成耗时",
  },
  {
    name: "Rerank Cache",
    detail: "按 query、候选文档和内容指纹缓存排序结果，并支持 request_id 撤销。",
    effect: "减少外部 Rerank 调用",
  },
] as const;

/**
 * LightRAG-lite 卖点条目。
 *
 * @author lvdaxianerplus
 */
export const LIGHT_RAG_POINTS = [
  {
    name: "实体关系图索引",
    detail: "文档录入时抽取 entities / relations，维护内存轻量图索引。",
  },
  {
    name: "Local / Global 线索",
    detail: "先用实体和关系词命中局部证据，再补充全局主题和摘要线索。",
  },
  {
    name: "轻重链路切换",
    detail: "用 entities / relations 快速命中结构化线索，再决定是否进入 ES、Milvus、Rerank。",
  },
] as const;

/**
 * 准确性卖点。
 *
 * @author lvdaxianerplus
 */
export const ACCURACY_POINTS = [
  "知识库过滤字段贯穿 ES、Milvus、Rerank，避免跨库污染。",
  "summary-first 处理整库概览，parent/section expansion 补齐上下文。",
  "rerank 候选治理与 score trace 让高相关证据稳定排在前面。",
] as const;

/**
 * 速度卖点。
 *
 * @author lvdaxianerplus
 */
export const SPEED_POINTS = [
  "Query Scope 先路由，减少无意义的全量混合检索。",
  "本地高置信标题/文档名命中时跳过外部 Rerank。",
  "SSE 先出 trace，再分段输出答案，等待感更低。",
] as const;

/**
 * 可审计流程图条目。
 *
 * @author lvdaxianerplus
 */
export const AUDIT_FLOW = [
  { label: "用户问题", meta: "input" },
  { label: "rewrite query", meta: "query normalization" },
  { label: "CoT Plan 摘要", meta: "cot_plan 摘要输出" },
  { label: "route_plan", meta: "summary-first / local / hybrid" },
  { label: "多路召回", meta: "ES BM25 + Milvus Vector" },
  { label: "候选治理", meta: "dedupe / parent expansion / rerank" },
  { label: "答案生成", meta: "evidence grounded + SSE" },
] as const;

/**
 * 优化策略矩阵。
 *
 * @author lvdaxianerplus
 */
export const OPTIMIZATION_MATRIX = [
  {
    name: "查询理解",
    items: ["rewrite query", "query scope", "route_plan"],
  },
  {
    name: "证据增强",
    items: ["summary-first", "parent expansion", "section expansion"],
  },
  {
    name: "排序治理",
    items: ["hybrid score", "rerank candidate cap", "score trace"],
  },
  {
    name: "输出体验",
    items: ["cot_plan 摘要输出", "citation-safe results", "Markdown-aware SSE"],
  },
] as const;

/**
 * 优化重点条目。
 *
 * @author lvdaxianerplus
 */
export const OPTIMIZATION_HIGHLIGHTS = [
  {
    title: "查询先规划",
    action: "rewrite query + query scope + route_plan",
    benefit: "少搜错库、少走错链路",
    impact: "把概览、配置、事实、故障类问题分流到不同检索路线。",
  },
  {
    title: "证据先扩展",
    action: "summary-first + parent / section expansion",
    benefit: "少拿孤立 chunk 回答",
    impact: "概览问题先看摘要，命中片段后补齐父章节和相邻上下文。",
  },
  {
    title: "排序先治理",
    action: "hybrid score + rerank candidate cap + score trace",
    benefit: "少让弱相关证据排前面",
    impact: "ES、Milvus、Rerank 共同召回，但候选会去重、限流、解释分数来源。",
  },
  {
    title: "输出先可解释",
    action: "CoT Plan 摘要 + citation-safe results + SSE",
    benefit: "用户知道答案从哪里来",
    impact: "只展示可审计规划摘要、引用来源和 trace，不暴露隐式思维链。",
  },
] as const;
