/**
 * Recall · 首页（RAG 检索流程介绍）
 *
 * 由若干 Section 组成：核心概念 / 缓存加速 / 优化重点 / 流程步骤 / 审计流程 / 优化矩阵。
 * 所有数据都集中在 `homeCopy.ts` 维护；本文件只负责渲染。
 *
 * 设计要点：
 * 1. 数据与渲染分离：homeCopy.ts 提供 readonly 数组 + as const，本文件只 map
 * 2. 通用 Section / SectionHeader 子组件复用留白 + 标题排版
 * 3. 网格列数随容器宽度自适应（auto-fit + minmax）
 * 4. 流程 / 矩阵走等宽数字 + 大标题，确保视觉对齐
 * 5. 所有 Section 均为 landmark，配合 aria-label 提升无障碍
 *
 * @author lvdaxianerplus
 */
import type { ReactNode } from "react";
import { MetricStrip } from "../../components/recall/MetricStrip";
import { PageHeader } from "../../components/recall/PageHeader";
import {
  ACCURACY_POINTS,
  AUDIT_FLOW,
  CACHE_LAYERS,
  CORE_CONCEPTS,
  FLOW_STEPS,
  LIGHT_RAG_POINTS,
  OPTIMIZATION_HIGHLIGHTS,
  OPTIMIZATION_MATRIX,
  SPEED_POINTS,
} from "./homeCopy";

/**
 * 通用 Section 包装 props。
 *
 * @author lvdaxianerplus
 */
interface SectionProps {
  title: string;
  heading: string;
  description?: string;
  children: ReactNode;
}

/**
 * 通用 Section 包装：eyebrow + 标题 + 描述 + 卡片样式。
 * 不传 aria-label 也能挂到 landmarks。
 *
 * @param props.section 标签 / 标题 / 描述
 * @param props.children 卡片内容
 * @author lvdaxianerplus
 */
function Section({ title, heading, description, children }: SectionProps) {
  return (
    <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
      <SectionHeader eyebrow={title} title={heading} description={description} />
      {children}
    </section>
  );
}

/**
 * Section 头部 props。
 *
 * @author lvdaxianerplus
 */
interface SectionHeaderProps {
  eyebrow: string;
  title: string;
  description?: string;
}

/**
 * Section 头部：eyebrow + 标题 + 描述。
 *
 * @param props.eyebrow 小标签
 * @param props.title 标题
 * @param props.description 描述
 * @author lvdaxianerplus
 */
function SectionHeader({ eyebrow, title, description }: SectionHeaderProps) {
  return (
    <div className="mb-4 grid gap-1.5">
      <span className="text-xs font-semibold uppercase tracking-wider text-emerald-600">{eyebrow}</span>
      <h2 className="text-lg font-semibold text-slate-900">{title}</h2>
      {description ? <p className="max-w-3xl text-sm text-slate-500">{description}</p> : null}
    </div>
  );
}

/**
 * Recall RAG 检索流程首页。
 *
 * @author lvdaxianerplus
 */
export function HomePage() {
  return (
    <div className="space-y-4">
      <PageHeader
        eyebrow="Retrieval Architecture"
        title="Recall RAG 检索流程"
        description="Recall 把检索能力抽象为 Retrieval SDK：从问题路由、知识库过滤、摘要优先、章节扩展、混合召回到 Rerank 与流式输出，每一步都有 trace，方便评测、调试和持续优化。"
      />
      <MetricStrip
        items={[
          { label: "Route Plan", value: "先判断再检索" },
          { label: "Evidence First", value: "先证据后回答" },
          { label: "SSE", value: "实时 Trace + 答案" },
        ]}
      />

      <Section
        title="Concepts First"
        heading="先理解几个核心概念"
        description="Recall 的准确率不是靠“搜得更多”，而是先把问题变成可执行计划，再让每个召回和排序动作可解释。"
      >
        <div className="grid gap-3 [grid-template-columns:repeat(auto-fit,minmax(min(220px,100%),1fr))]">
          {CORE_CONCEPTS.map((concept) => (
            <article
              className="flex min-h-40 flex-col gap-2 rounded-lg border border-slate-200 bg-white p-4 shadow-sm"
              key={concept.name}
            >
              <h3 className="font-mono text-sm font-semibold text-slate-900">{concept.name}</h3>
              <p className="text-sm font-medium leading-6 text-slate-900">{concept.detail}</p>
              <small className="mt-auto text-xs leading-5 text-slate-500">{concept.role}</small>
            </article>
          ))}
        </div>
      </Section>

      <Section
        title="Acceleration"
        heading="缓存如何让检索更快"
        description="Recall 不是只缓存最终答案，而是缓存规划、向量和排序三个高成本环节；缓存命中时仍保留 trace，方便知道到底省掉了哪一步。"
      >
        <div className="grid gap-3 [grid-template-columns:repeat(auto-fit,minmax(min(340px,100%),1fr))]">
          <div className="space-y-2" aria-label="缓存加速栈">
            {CACHE_LAYERS.map((layer, index) => (
              <article
                className="grid grid-cols-[auto_1fr_auto] items-center gap-3 rounded-lg border border-slate-200 bg-white p-3"
                key={layer.name}
              >
                <span className="grid size-8 place-items-center rounded-md bg-emerald-50 font-mono text-xs font-semibold text-emerald-700">
                  {String(index + 1).padStart(2, "0")}
                </span>
                <div>
                  <h3 className="text-sm font-semibold text-slate-900">{layer.name}</h3>
                  <p className="text-sm leading-6 text-slate-600">{layer.detail}</p>
                </div>
                <strong className="rounded-md border border-indigo-200 bg-indigo-50 px-2 py-1 text-xs text-indigo-700">
                  {layer.effect}
                </strong>
              </article>
            ))}
          </div>
          <article className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
            <span className="inline-flex rounded-md bg-indigo-50 px-2 py-1 text-xs font-semibold text-indigo-700">
              LightRAG-lite 轻量图检索
            </span>
            <h3 className="mt-3 text-base font-semibold text-slate-900">轻量结构化召回先跑，重链路按需进入</h3>
            <p className="mt-2 text-sm leading-6 text-slate-600">
              当问题命中明确实体、关系或主题时，LightRAG-lite 会先给出结构化候选，
              帮助系统更快锁定文档范围，并降低 ES、Milvus、Rerank 的无效候选压力。
            </p>
            <ul className="mt-3 space-y-2 border-t border-slate-200 pt-3 text-sm">
              {LIGHT_RAG_POINTS.map((point) => (
                <li key={point.name}>
                  <strong className="text-slate-900">{point.name}</strong>
                  <small className="mt-0.5 block text-xs leading-5 text-slate-500">{point.detail}</small>
                </li>
              ))}
            </ul>
          </article>
        </div>
      </Section>

      <Section
        title="Optimization Focus"
        heading="我们到底优化了哪里"
        description="核心不是“多接几个检索引擎”，而是在每个容易出错的环节先做判断、约束和可解释治理。"
      >
        {/* 4 个优化重点卡片：每张含"动作 / 收益 / 影响"三段 */}
        <div className="grid gap-3 [grid-template-columns:repeat(auto-fit,minmax(min(220px,100%),1fr))]">
          {OPTIMIZATION_HIGHLIGHTS.map((item, index) => (
            <article
              className="flex min-h-56 flex-col gap-2 rounded-lg border border-slate-200 bg-white p-4 shadow-sm"
              key={item.title}
            >
              <span className="grid size-8 place-items-center rounded-md bg-emerald-50 font-mono text-xs font-semibold text-emerald-700">
                {String(index + 1).padStart(2, "0")}
              </span>
              <h3 className="text-base font-semibold text-slate-900">{item.title}</h3>
              <strong className="text-sm font-medium text-slate-900">{item.benefit}</strong>
              <p className="text-sm leading-6 text-slate-600">{item.impact}</p>
              <small className="mt-auto rounded-md border border-slate-200 bg-slate-50 p-2 text-xs leading-5 text-slate-500">
                {item.action}
              </small>
            </article>
          ))}
        </div>
      </Section>

      {/* RAG 检索流程步骤（6 步）：横向并列 + 等高卡片 */}
      <div
        aria-label="RAG 检索流程"
        className="grid gap-3 [grid-template-columns:repeat(auto-fit,minmax(min(220px,100%),1fr))]"
      >
        {FLOW_STEPS.map((step, index) => (
          <article
            className="flex min-h-40 flex-col gap-2 rounded-lg border border-slate-200 bg-white p-4 shadow-sm"
            key={step.title}
          >
            <span className="grid size-7 place-items-center rounded-md bg-emerald-50 font-mono text-xs font-semibold text-emerald-700">
              {String(index + 1).padStart(2, "0")}
            </span>
            <h3 className="text-sm font-semibold text-slate-900">{step.title}</h3>
            <p className="text-sm leading-6 text-slate-600">{step.detail}</p>
          </article>
        ))}
      </div>

      {/* 可审计 RAG 流程图：7 步流水线横向展示 + SectionHeader 复用 */}
      <section
        aria-label="可审计 RAG 流程图"
        className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm"
      >
        <SectionHeader
          eyebrow="Audit Flow"
          title="可审计 RAG 流程图"
          description="页面展示的是可记录、可回放的 CoT Plan 摘要与 route_plan，不暴露模型内部隐式思维链。"
        />
        {/* 7 列固定宽度（横向可滚动） */}
        <div className="grid gap-2 overflow-x-auto [grid-template-columns:repeat(7,minmax(120px,1fr))]">
          {AUDIT_FLOW.map((item, index) => (
            <article
              className="flex min-h-28 flex-col gap-1.5 rounded-lg border border-slate-200 bg-white p-3"
              key={item.label}
            >
              <span className="grid size-7 place-items-center rounded-md bg-indigo-50 font-mono text-xs font-semibold text-indigo-700">
                {String(index + 1).padStart(2, "0")}
              </span>
              <strong className="text-sm font-medium text-slate-900">{item.label}</strong>
              <small className="text-xs leading-5 text-slate-500">{item.meta}</small>
            </article>
          ))}
        </div>
      </section>

      {/* 优化策略矩阵：4 个分类，每类列出相关项 */}
      <Section title="Optimization" heading="优化策略矩阵">
        <div className="grid gap-3 [grid-template-columns:repeat(auto-fit,minmax(min(180px,100%),1fr))]">
          {OPTIMIZATION_MATRIX.map((group) => (
            <article
              className="rounded-lg border border-slate-200 bg-slate-50 p-3"
              key={group.name}
            >
              <h3 className="mb-2 text-sm font-semibold text-slate-900">{group.name}</h3>
              <ul className="m-0 list-disc space-y-1 pl-5 text-sm text-slate-600">
                {group.items.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </article>
          ))}
        </div>
      </Section>

      {/* 三栏总结：准确 / 速度 / 可观测 */}
      <div className="grid gap-3 [grid-template-columns:repeat(auto-fit,minmax(min(240px,100%),1fr))]">
        <article className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
          <span className="text-xs font-semibold uppercase tracking-wider text-emerald-600">Precision</span>
          <h3 className="mt-1 text-base font-semibold text-slate-900">为什么更准确</h3>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-slate-600">
            {ACCURACY_POINTS.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </article>
        <article className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
          <span className="text-xs font-semibold uppercase tracking-wider text-emerald-600">Latency</span>
          <h3 className="mt-1 text-base font-semibold text-slate-900">为什么更快</h3>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-slate-600">
            {SPEED_POINTS.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </article>
        <article className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
          <span className="text-xs font-semibold uppercase tracking-wider text-emerald-600">Observability</span>
          <h3 className="mt-1 text-base font-semibold text-slate-900">每次检索都可解释</h3>
          <p className="mt-2 text-sm leading-6 text-slate-600">
            前端检索控制台与聊天抽屉都能查看 Query Scope、candidate scoring、引用来源和 score trace。
          </p>
        </article>
      </div>
    </div>
  );
}
