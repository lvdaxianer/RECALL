import type { PropsWithChildren } from "react";

interface AppShellProps {
  activeNav?: string;
  onNavigate?: (item: string) => void;
  title: string;
}

const NAV_SECTIONS = [
  {
    title: "概览",
    items: [{ label: "首页", icon: "HM" }],
  },
  {
    title: "知识工作台",
    items: [
      { label: "知识库管理", icon: "KB" },
      { label: "文档录入", icon: "MD" },
    ],
  },
  {
    title: "检索与评测",
    items: [
      { label: "检索调试", icon: "RX" },
      { label: "效果评测", icon: "EV" },
    ],
  },
  {
    title: "系统",
    items: [{ label: "设置", icon: "ST" }],
  },
];

export function AppShell({
  activeNav = "知识库管理",
  onNavigate = () => undefined,
  title,
  children,
}: PropsWithChildren<AppShellProps>) {
  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="app-brand">
          <span className="brand-mark" aria-hidden="true">R</span>
          <div>
            <p>Recall</p>
            <h1>{title}</h1>
            <span className="app-brand__subtitle">Retrieval Operations</span>
          </div>
        </div>
        <div className="app-header__actions" aria-label="全局操作">
          <label className="global-search">
            <span className="sr-only">全局搜索</span>
            <input placeholder="搜索知识库、文档或会话" />
          </label>
          <span className="service-pill service-pill--quiet">Retrieval SDK</span>
          <span className="service-pill service-pill--quiet">ES / Milvus / Rerank</span>
          <span className="service-pill">SSE Ready</span>
        </div>
      </header>
      <div className="app-body">
        <aside className="app-sidebar">
          <nav aria-label="主导航">
            {NAV_SECTIONS.map((section) => (
              <div className="nav-section" key={section.title}>
                <span className="nav-section__title">{section.title}</span>
                {section.items.map((item) => (
                  <button
                    className={item.label === activeNav ? "nav-item nav-item--active" : "nav-item"}
                    key={item.label}
                    type="button"
                    onClick={() => onNavigate(item.label)}
                    aria-current={item.label === activeNav ? "page" : undefined}
                  >
                    <span className="nav-item__icon" aria-hidden="true">{item.icon}</span>
                    <span>{item.label}</span>
                  </button>
                ))}
              </div>
            ))}
          </nav>
          <div className="sidebar-note">
            <span>仅发布库参与问答</span>
            <strong>草稿内容录入后需发版</strong>
            <small>Evidence Rail</small>
          </div>
        </aside>
        <main className="app-main">{children}</main>
      </div>
    </div>
  );
}
