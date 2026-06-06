import { useEffect, useState } from "react";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../../components/ui/card";
import { Tabs, TabsContent } from "../../components/ui/tabs";
import { AnswerCachePanel } from "./AnswerCachePanel";
import { SettingsPlaceholder } from "./SettingsPlaceholder";
import { SynonymsPanel } from "./SynonymsPanel";
import {
  ALL_SETTINGS_SECTIONS,
  DEFAULT_SECTION,
  SECTION_IDS,
  type SettingsItem,
  type SettingsSectionId,
} from "./settingsSections";

/**
 * 解码 hash 中的单段，处理 URL 解码异常。
 *
 * @param part 原始字符串
 * @returns 解码后字符串，失败回退原值
 * @author lvdaxianerplus
 */
function decodePart(part: string): string {
  try {
    return decodeURIComponent(part);
  } catch {
    return part;
  }
}

/**
 * 从 window.location.hash 解析当前要展示的设置子项。
 * 支持 #设置/answer-cache 与 #设置/答案缓存 两种形式。
 *
 * @returns 解析出的设置子项 id
 * @author lvdaxianerplus
 */
function sectionIdFromHash(): SettingsSectionId {
  if (typeof window === "undefined") {
    return DEFAULT_SECTION;
  }
  const raw = window.location.hash.replace(/^#/, "").trim();
  const parts = raw.split("/").map((p) => p.trim()).filter(Boolean);
  if (parts.length < 2) {
    return DEFAULT_SECTION;
  }
  if (decodePart(parts[0] ?? "") !== "设置") {
    return DEFAULT_SECTION;
  }
  const candidate = decodePart(parts[1] ?? "");
  if (SECTION_IDS.includes(candidate)) {
    return candidate as SettingsSectionId;
  }
  const byLabel = ALL_SETTINGS_SECTIONS.find((section) => section.label === candidate);
  if (byLabel) {
    return byLabel.id;
  }
  return DEFAULT_SECTION;
}

/**
 * 渲染某个设置项的对应面板。
 *
 * @param section 设置项元信息
 * @author lvdaxianerplus
 */
function renderSectionContent(section: SettingsItem) {
  if (section.id === "answer-cache") {
    return (
      <TabsContent key={section.id} value={section.id}>
        <AnswerCachePanel />
      </TabsContent>
    );
  }
  if (section.id === "synonyms") {
    return (
      <TabsContent key={section.id} value={section.id}>
        <SynonymsPanel />
      </TabsContent>
    );
  }
  return (
    <TabsContent key={section.id} value={section.id}>
      <SettingsPlaceholder section={section} />
    </TabsContent>
  );
}

/**
 * 设置页：v1.5 起，菜单都搬到全局侧栏（AppShell），
 * 本页只剩右侧表单（根据 URL hash #设置/xxx 决定渲染哪个子项）。
 *
 * @param props.subRoute 可选子路由（首次渲染时优先使用）
 * @author lvdaxianerplus
 */
export function SettingsPage({ subRoute = null }: { subRoute?: string | null } = {}) {
  const [activeSection, setActiveSection] = useState<SettingsSectionId>(() => {
    if (subRoute && SECTION_IDS.includes(subRoute)) {
      return subRoute as SettingsSectionId;
    }
    if (typeof window !== "undefined") {
      return sectionIdFromHash();
    }
    return DEFAULT_SECTION;
  });

  useEffect(() => {
    function handleHashChange() {
      setActiveSection(sectionIdFromHash());
    }
    handleHashChange();
    window.addEventListener("hashchange", handleHashChange);
    return () => window.removeEventListener("hashchange", handleHashChange);
  }, []);

  const activeItem = ALL_SETTINGS_SECTIONS.find((section) => section.id === activeSection) ?? ALL_SETTINGS_SECTIONS[0];

  return (
    <section className="space-y-4">
      <Card>
        <CardHeader>
          <CardDescription>系统治理</CardDescription>
          <CardTitle>
            <h2 className="text-xl font-semibold text-slate-900">系统设置 · {activeItem.label}</h2>
          </CardTitle>
          <p className="text-sm text-slate-500">
            {activeItem.summary}
          </p>
        </CardHeader>
      </Card>

      {/*
        路由由侧栏链接 + hash 驱动；不接 onValueChange 防止误改。
        Tabs 只是受控 value 展示。
      */}
      <Tabs
        value={activeSection}
        onValueChange={() => {
          /* intentionally empty */
        }}
      >
        {ALL_SETTINGS_SECTIONS.map((section) => renderSectionContent(section))}
      </Tabs>
    </section>
  );
}
