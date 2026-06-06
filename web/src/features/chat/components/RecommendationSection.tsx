import { BookOpen, Compass } from "lucide-react";

import type { AgentEvent } from "../../../api/sessions";

const TOPIC_KIND = "topic";
const DEFAULT_TOPIC_TITLE = "继续探索相关主题";
const DEFAULT_DOCUMENT_TITLE = "相关资料";
const TOPIC_PATH_SEPARATOR = " / ";

/**
 * 单张推荐卡片的数据视图。
 *
 * @author lvdaxianerplus
 * @date 2026-06-06
 */
interface RecommendationCard {
  kind?: "document" | "topic";
  metadata?: Record<string, unknown>;
  description?: string;
  reason?: string;
  topic_path?: string[];
  follow_up_question?: string | null;
}

/**
 * 从事件流中抽取最新的推荐结果。
 *
 * @param events - 聊天消息事件流
 * @returns 推荐卡片列表
 * @author lvdaxianerplus
 * @date 2026-06-06
 */
function getRecommendationCards(events: AgentEvent[] | undefined): RecommendationCard[] {
  const completed = [...(events ?? [])]
    .reverse()
    .find((event) => event.event === "recommendation.completed" && Array.isArray(event.payload.recommendations));
  return Array.isArray(completed?.payload.recommendations)
    ? completed.payload.recommendations.map((item) => item as RecommendationCard)
    : [];
}

/**
 * 取推荐卡片标题。
 *
 * @param item - 推荐卡片数据
 * @returns 用户可见标题
 * @author lvdaxianerplus
 * @date 2026-06-06
 */
function getRecommendationTitle(item: RecommendationCard): string {
  return item.kind === TOPIC_KIND ? getTopicTitle(item) : getDocumentTitle(item);
}

/**
 * 取主题推荐卡片标题。
 *
 * @param item - 推荐卡片数据
 * @returns 主题推荐标题
 * @author lvdaxianerplus
 * @date 2026-06-06
 */
function getTopicTitle(item: RecommendationCard): string {
  return item.follow_up_question
    || item.description
    || String(item.metadata?.topic ?? DEFAULT_TOPIC_TITLE);
}

/**
 * 取文档推荐卡片标题。
 *
 * @param item - 推荐卡片数据
 * @returns 文档推荐标题
 * @author lvdaxianerplus
 * @date 2026-06-06
 */
function getDocumentTitle(item: RecommendationCard): string {
  return String(item.metadata?.document_name ?? "")
    || item.description
    || String(item.metadata?.id ?? DEFAULT_DOCUMENT_TITLE);
}

/**
 * 聊天消息下方的智能推荐区。
 *
 * @param props - events 为消息事件流
 * @returns 推荐区 UI；无推荐时不渲染
 * @author lvdaxianerplus
 * @date 2026-06-06
 */
export function RecommendationSection({ events }: { events: AgentEvent[] | undefined }) {
  const recommendations = getRecommendationCards(events);
  const documentCards = recommendations.filter((item) => item.kind !== TOPIC_KIND);
  const topicCards = recommendations.filter((item) => item.kind === TOPIC_KIND);
  return recommendations.length > 0 ? (
    <section className="rounded-xl border border-emerald-100 bg-emerald-50/45 p-3 shadow-xs">
      <div className="mb-2 flex items-center gap-2">
        <span className="grid size-6 place-items-center rounded-lg bg-white text-emerald-700 shadow-xs">
          <Compass aria-hidden="true" className="size-3.5" />
        </span>
        <h3 className="text-sm font-semibold text-slate-900">你可能还想看</h3>
      </div>
      {documentCards.length > 0 ? (
        <RecommendationCardList title="文档推荐" cards={documentCards} icon="document" />
      ) : null}
      {topicCards.length > 0 ? (
        <RecommendationCardList title="主题导航" cards={topicCards} icon="topic" />
      ) : null}
    </section>
  ) : undefined;
}

/**
 * 同类推荐卡片列表。
 *
 * @param props - title 为分组标题，cards 为卡片集合，icon 为图标类型
 * @returns 推荐卡片列表 UI
 * @author lvdaxianerplus
 * @date 2026-06-06
 */
function RecommendationCardList({
  title,
  cards,
  icon,
}: {
  title: string;
  cards: RecommendationCard[];
  icon: "document" | "topic";
}) {
  return (
    <div className="mt-2 grid gap-2">
      <p className="text-xs font-medium text-slate-500">{title}</p>
      <div className="grid gap-2">
        {cards.map((item, index) => (
          <article
            key={`${title}-${getRecommendationTitle(item)}-${index}`}
            className="rounded-lg border border-white/80 bg-white px-3 py-2 shadow-xs"
          >
            <div className="flex items-start gap-2">
              <span className="mt-0.5 grid size-6 shrink-0 place-items-center rounded-md bg-slate-50 text-slate-500">
                {icon === "document" ? (
                  <BookOpen aria-hidden="true" className="size-3.5" />
                ) : (
                  <Compass aria-hidden="true" className="size-3.5" />
                )}
              </span>
              <div className="min-w-0">
                <h4 className="break-words text-sm font-medium text-slate-900">
                  {getRecommendationTitle(item)}
                </h4>
                {item.reason ? <p className="mt-0.5 text-xs text-slate-500">{item.reason}</p> : null}
                {Array.isArray(item.topic_path) && item.topic_path.length > 0 ? (
                  <p className="mt-1 text-[11px] text-slate-400">{item.topic_path.join(TOPIC_PATH_SEPARATOR)}</p>
                ) : null}
              </div>
            </div>
          </article>
        ))}
      </div>
    </div>
  );
}
