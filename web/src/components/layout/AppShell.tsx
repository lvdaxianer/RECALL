/**
 * Recall · 应用主壳
 *
 * 由三部分组成：顶栏（标题 + 全局搜索 + SDK 状态徽章） + 侧栏（主导航 / 系统设置） + 内容区。
 *
 * v1.5 设计：
 * - 把设置项都搬到全局侧栏（hash 路由 `#设置/xxx`）
 * - 侧栏用"主导航 / 分隔线 / 系统设置组"组织，不再让 SettingsPage 自己嵌 sidebar
 * - 移动端通过 SidebarProvider 的 sheet 行为自动切到抽屉
 *
 * @author lvdaxianerplus
 */
import type { ComponentType, PropsWithChildren, SVGProps } from "react";
import {
  BookOpen,
  Database,
  FileText,
  Gauge,
  Home,
  Layers,
  Plus,
  Search,
  Settings as SettingsIcon,
  TestTube2,
  Workflow,
} from "lucide-react";

import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
  SidebarInset,
  SidebarProvider,
  SidebarTrigger,
  useSidebar,
} from "@/components/ui/sidebar";

/**
 * AppShell props 集合。
 *
 * @author lvdaxianerplus
 */
interface AppShellProps {
  /** 当前顶级 label（用于侧栏高亮） */
  activeNav?: string;
  /** 当前 sub-route（`#设置/xxx`）—— 用于高亮设置子项 */
  activeSubRoute?: string | null;
  /** 导航回调（父组件接到后改 hash） */
  onNavigate?: (item: string) => void;
  /** 顶栏标题 */
  title: string;
}

/**
 * 侧栏导航条目。
 *
 * @author lvdaxianerplus
 */
interface NavItem {
  /** 顶级 label（同时是 hash 锚点） */
  label: string;
  /** 图标组件 */
  icon: ComponentType<SVGProps<SVGSVGElement>>;
  /** 是否在 hash 里多一段子段（用于 "设置/xxx"） */
  isSetting?: boolean;
}

/**
 * 主导航：与 `app/App.tsx` 的 ROUTES 数组保持 label 一致。
 *
 * @author lvdaxianerplus
 */
const PRIMARY_NAV: NavItem[] = [
  { label: "首页", icon: Home },
  { label: "知识库管理", icon: BookOpen },
  { label: "文档录入", icon: FileText },
  { label: "检索调试", icon: Search },
  { label: "效果评测", icon: TestTube2 },
];

/**
 * 系统设置子项：与 `features/settings/settingsSections.ts` 的 items 保持 label 一致。
 *
 * @author lvdaxianerplus
 */
const SETTINGS_NAV: NavItem[] = [
  { label: "答案缓存", icon: Database, isSetting: true },
  { label: "同义词", icon: Workflow, isSetting: true },
  { label: "重排缓存", icon: Layers, isSetting: true },
  { label: "向量缓存", icon: Gauge, isSetting: true },
  { label: "模型配置", icon: SettingsIcon, isSetting: true },
  { label: "检索策略", icon: Search, isSetting: true },
  { label: "服务健康", icon: TestTube2, isSetting: true },
];

/**
 * AppShell 顶层组件：外层套 SidebarProvider，子层才能使用 useSidebar。
 *
 * @param props.activeNav 当前顶级 label
 * @param props.activeSubRoute 当前 sub-route
 * @param props.onNavigate 导航回调
 * @param props.title 顶栏标题
 * @param props.children 内容区
 * @author lvdaxianerplus
 */
export function AppShell({
  activeNav = "首页",
  activeSubRoute = null,
  onNavigate = () => undefined,
  title,
  children,
}: PropsWithChildren<AppShellProps>) {
  return (
    <SidebarProvider>
      <AppShellContent
        activeNav={activeNav}
        activeSubRoute={activeSubRoute}
        onNavigate={onNavigate}
        title={title}
      >
        {children}
      </AppShellContent>
    </SidebarProvider>
  );
}

/**
 * AppShell 实际渲染内容（拆出来是为了在内部用 useSidebar）。
 *
 * @param props.activeNav 当前顶级 label
 * @param props.activeSubRoute 当前 sub-route
 * @param props.onNavigate 导航回调
 * @param props.title 顶栏标题
 * @param props.children 内容区
 * @author lvdaxianerplus
 */
function AppShellContent({
  activeNav = "首页",
  activeSubRoute = null,
  onNavigate = () => undefined,
  title,
  children,
}: PropsWithChildren<AppShellProps>) {
  // useSidebar 必须在 SidebarProvider 内部
  const { isMobile, setOpenMobile } = useSidebar();

  /**
   * 路由切换：让浏览器自然改 hash（hashchange 监听会自动更新 App state），
   * 移动端则关掉抽屉。
   *
   * @param item 目标 label
   * @author lvdaxianerplus
   */
  function handleNavigate(item: string) {
    onNavigate(item);
    if (isMobile) {
      setOpenMobile(false);
    }
  }

  return (
    <>
      <Sidebar collapsible="offcanvas" className="border-r border-slate-200 bg-white">
        {/* 头部：品牌标识 */}
        <SidebarHeader className="border-b border-slate-200 p-4">
          <div className="flex items-center gap-2.5">
            <span
              aria-hidden="true"
              className="grid size-8 place-items-center rounded-md bg-emerald-600 text-sm font-semibold text-white"
            >
              R
            </span>
            <div className="min-w-0">
              <p className="truncate text-sm font-semibold text-slate-900">Recall</p>
              <p className="truncate text-xs text-slate-500">知识库检索控制台</p>
            </div>
          </div>
        </SidebarHeader>

        <SidebarContent className="p-2">
          {/* 主导航组 */}
          <nav aria-label="主导航" className="space-y-0.5">
            {PRIMARY_NAV.map((item) => {
              const Icon = item.icon;
              // 高亮匹配：当前 active label 与本项 label 一致
              const isActive = item.label === activeNav;
              // 设置子项走 `#设置/xxx`，顶级走 `#xxx`
              const href = item.isSetting ? `#设置/${encodeURIComponent(item.label)}` : `#${item.label}`;
              return (
                <a
                  key={item.label}
                  href={href}
                  aria-current={isActive ? "page" : undefined}
                  className={cn(
                    "flex h-8 items-center gap-2.5 rounded-md px-2.5 text-sm transition-colors",
                    isActive
                      ? "bg-emerald-50 font-medium text-emerald-700"
                      : "text-slate-600 hover:bg-slate-100 hover:text-slate-900",
                  )}
                  onClick={() => handleNavigate(item.label)}
                >
                  <Icon aria-hidden="true" className="size-4 shrink-0" />
                  <span className="truncate">{item.label}</span>
                </a>
              );
            })}
          </nav>
          {/* 分隔线 */}
          <div aria-hidden="true" className="my-3 border-t border-slate-200" />
          {/* 系统设置组 */}
          <nav aria-label="系统设置" className="space-y-0.5">
            <p className="px-2.5 pb-1 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
              系统设置
            </p>
            {SETTINGS_NAV.map((item) => {
              const Icon = item.icon;
              // 设置子项的高亮：仅 subRoute 匹配 label
              const isActive = item.label === activeSubRoute;
              const href = `#设置/${encodeURIComponent(item.label)}`;
              return (
                <a
                  key={item.label}
                  href={href}
                  aria-current={isActive ? "page" : undefined}
                  className={cn(
                    "flex h-8 items-center gap-2.5 rounded-md px-2.5 text-sm transition-colors",
                    isActive
                      ? "bg-emerald-50 font-medium text-emerald-700"
                      : "text-slate-600 hover:bg-slate-100 hover:text-slate-900",
                  )}
                  onClick={() => handleNavigate(item.label)}
                >
                  <Icon aria-hidden="true" className="size-4 shrink-0" />
                  <span className="truncate">{item.label}</span>
                </a>
              );
            })}
          </nav>
        </SidebarContent>

        {/* 底部：新建知识库快捷按钮（点击跳到 KB 列表页） */}
        <SidebarFooter className="border-t border-slate-200 p-3">
          <button
            className="flex h-8 w-full items-center gap-2 rounded-md border border-dashed border-slate-300 px-2.5 text-sm font-medium text-emerald-700 transition-colors hover:border-emerald-500 hover:bg-emerald-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500"
            type="button"
            onClick={() => handleNavigate("知识库管理")}
          >
            <Plus aria-hidden="true" className="size-4" />
            新建知识库
          </button>
        </SidebarFooter>
      </Sidebar>

      {/* 主内容区 */}
      <SidebarInset className="w-0 min-w-0 overflow-x-hidden">
        {/* 顶栏：标题 + 全局搜索 + SDK 状态徽章 */}
        <header className="sticky top-0 z-20 flex h-14 items-center justify-between gap-4 border-b border-slate-200 bg-white/85 px-4 backdrop-blur md:px-6">
          <div className="flex min-w-0 items-center gap-3">
            {/* 移动端显示侧栏切换按钮 */}
            <SidebarTrigger aria-label="切换主导航" className="md:hidden" />
            <h1 className="truncate text-base font-semibold tracking-tight text-slate-900">
              {title}
            </h1>
          </div>
          <div aria-label="全局操作" className="flex min-w-0 items-center gap-2">
            {/* 全局搜索：sm+ 显示 */}
            <label className="relative hidden h-8 sm:flex sm:w-72 sm:items-center">
              <span className="sr-only">全局搜索</span>
              <Search
                aria-hidden="true"
                className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-slate-400"
              />
              <Input
                className="h-8 w-full border-slate-200 bg-slate-50 pl-8 pr-12 text-sm shadow-none transition-colors focus-visible:bg-white"
                placeholder="搜索知识库、文档或会话"
              />
              {/* ⌘K 提示放在输入框右侧 */}
              <kbd className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2">⌘K</kbd>
            </label>
            {/* SDK 状态徽章：仅 lg+ 显示，避免小屏拥挤 */}
            <span className="hidden h-6 items-center gap-1 rounded border border-slate-200 bg-white px-2 text-[11px] font-medium text-slate-500 lg:inline-flex">
              <span aria-hidden="true" className="size-1.5 rounded-full bg-emerald-500" />
              SDK Ready
            </span>
          </div>
        </header>

        <main className="flex-1 bg-slate-50 p-4 md:p-6">{children}</main>
      </SidebarInset>
    </>
  );
}
