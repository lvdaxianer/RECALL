/**
 * Recall · 应用根组件
 *
 * 负责：
 * 1. URL hash 路由（#首页、#设置/xxx 等）→ 渲染对应业务页面
 * 2. 监听 `hashchange` 事件，跨组件共享当前 active label / sub route
 * 3. 全局挂载 `ChatAssistant` 抽屉
 *
 * v1.4：label 同时是 URL hash（#首页 等），让浏览器地址栏反映当前页面。
 *
 * @author lvdaxianerplus
 */
import { useEffect, useState } from "react";

import { AppShell } from "../components/layout/AppShell";
import { ChatAssistant } from "../features/chat/ChatAssistant";
import { DocumentIngestPage } from "../features/documents/DocumentIngestPage";
import { EvaluationPage } from "../features/evaluation/EvaluationPage";
import { HomePage } from "../features/home/HomePage";
import { KnowledgeBaseListPage } from "../features/kb/KnowledgeBaseListPage";
import { RetrievalConsolePage } from "../features/retrieval/RetrievalConsolePage";
import { SettingsPage } from "../features/settings/SettingsPage";

/**
 * 单条路由配置。
 *
 * @author lvdaxianerplus
 */
interface RouteConfig {
  /** 路由 label（与 hash 锚点一致） */
  label: string;
  /** 顶栏标题 */
  title: string;
  /** 渲染函数 */
  render: (params: { subRoute: string | null }) => React.ReactNode;
}

/**
 * 路由表：label → 渲染组件。
 *
 * @author lvdaxianerplus
 */
const ROUTES: readonly RouteConfig[] = [
  { label: "首页", title: "Recall 知识库检索控制台", render: () => <HomePage /> },
  { label: "知识库管理", title: "知识库管理 · Recall", render: () => <KnowledgeBaseListPage /> },
  { label: "文档录入", title: "文档录入 · Recall", render: () => <DocumentIngestPage /> },
  { label: "检索调试", title: "检索控制台 · Recall", render: () => <RetrievalConsolePage /> },
  { label: "效果评测", title: "效果评测 · Recall", render: () => <EvaluationPage /> },
  {
    label: "设置",
    title: "系统设置 · Recall",
    // 设置页支持子路由：`#设置/答案缓存` 把 答案缓存 传给 SettingsPage
    render: ({ subRoute }: { subRoute: string | null }) => (
      <SettingsPage subRoute={subRoute} />
    ),
  },
] as const;

/** 默认顶级 label（hash 解析失败时回退到首页） */
const DEFAULT_LABEL: (typeof ROUTES)[number]["label"] = "首页";

/**
 * 设置子项的 label 集合（用于决定走 `#设置/xxx` 还是 `#xxx`）。
 *
 * @author lvdaxianerplus
 */
const SETTINGS_LABELS = new Set<string>([
  "答案缓存", "同义词", "重排缓存", "向量缓存", "模型配置", "检索策略", "服务健康",
]);

/**
 * 解码 hash 单段（处理 URL 编码异常）。
 *
 * @param part 原始字符串
 * @returns 解码后字符串
 * @author lvdaxianerplus
 */
function decodeHashPart(part: string): string {
  try {
    return decodeURIComponent(part);
  } catch {
    return part;
  }
}

/**
 * 从 hash 中解析顶级 label。
 *
 * @param hash window.location.hash
 * @returns 匹配到的顶级 label；未匹配时回退到 DEFAULT_LABEL
 * @author lvdaxianerplus
 */
function labelFromHash(hash: string): string {
  // 只取第一段作为顶级 label（v1.4 引入子路由）
  const raw = hash.replace(/^#/, "").trim();
  const head = raw.split("/")[0]?.trim() ?? "";
  const decoded = decodeHashPart(head);
  return ROUTES.some((route) => route.label === decoded) ? decoded : DEFAULT_LABEL;
}

/**
 * 从 hash 中解析子路由（仅在顶级 label 匹配时返回子段）。
 *
 * @param hash window.location.hash
 * @param topLabel 顶级 label
 * @returns 子段字符串，无则返回 null
 * @author lvdaxianerplus
 */
function subRouteFromHash(hash: string, topLabel: string): string | null {
  if (!topLabel) {
    return null;
  }
  const raw = hash.replace(/^#/, "").trim();
  const parts = raw.split("/").map((part) => part.trim()).filter(Boolean);
  if (parts.length < 2) {
    return null;
  }
  // 仅当第一段匹配顶级 label 时返回子段
  const head = decodeHashPart(parts[0] ?? "");
  if (head !== topLabel) {
    return null;
  }
  return decodeHashPart(parts[1] ?? "");
}

/**
 * 应用根组件。
 *
 * @author lvdaxianerplus
 */
export function App() {
  // 关键：state 总是从 window.location.hash 派生，每次渲染都重算，
  // 这样 hashchange 派发后 React 会用新 hash 重新渲染组件。
  const [hash, setHash] = useState<string>(() => window.location.hash);

  /**
   * 监听 hashchange，更新本地 state。
   *
   * @author lvdaxianerplus
   */
  useEffect(() => {
    function handleHashChange() {
      setHash(window.location.hash);
    }
    window.addEventListener("hashchange", handleHashChange);
    return () => window.removeEventListener("hashchange", handleHashChange);
  }, []);

  /**
   * 路由切换：`<a href="#...">` 会自然改 hash；为了兼容 jsdom 不触发 hashchange，
   * 这里手动 dispatch 一下。
   *
   * @param label 目标顶级 label 或设置子项 label
   * @author lvdaxianerplus
   */
  function handleNavigate(label: string) {
    if (typeof window === "undefined") {
      return;
    }
    // 设置子项走 #设置/<label>，顶级走 #<label>
    const hashValue = SETTINGS_LABELS.has(label)
      ? `设置/${encodeURIComponent(label)}`
      : label;
    const newHash = `#${hashValue}`;
    if (window.location.hash !== newHash) {
      window.location.hash = hashValue;
    }
    // jsdom 不会因 location.hash = 派发 hashchange，手动补一刀
    window.dispatchEvent(new HashChangeEvent("hashchange"));
  }

  // 1. 解析当前 active 顶级 label
  const activeLabel = labelFromHash(hash);
  // 2. 找到对应路由；未匹配时回退到 ROUTES[0]
  const activeRoute =
    ROUTES.find((route) => route.label === activeLabel) ?? ROUTES[0];
  // 3. 设置页支持子路由：#设置/xxx 把 xxx 传给 SettingsPage
  const activeSubRoute =
    activeRoute.label === "设置" ? subRouteFromHash(hash, activeRoute.label) : null;

  return (
    <AppShell
      activeNav={activeRoute.label}
      activeSubRoute={activeSubRoute}
      onNavigate={handleNavigate}
      title={activeRoute.title}
    >
      {activeRoute.render({ subRoute: activeSubRoute })}
      {/* ChatAssistant 全局挂载，自己负责抽屉开/关 */}
      <ChatAssistant />
    </AppShell>
  );
}
