import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import packageJson from "../package.json";
import { Button } from "../src/components/ui/button";
import { Card } from "../src/components/ui/card";
import { Dialog } from "../src/components/ui/dialog";
import { SectionCard } from "../src/components/common/SectionCard";
import { cn } from "../src/lib/utils";

describe("design system dependency contract", () => {
  it("uses the approved UI and styling libraries", () => {
    expect(packageJson.dependencies).toHaveProperty("tailwindcss");
    expect(packageJson.dependencies).toHaveProperty("lucide-react");
    expect(packageJson.dependencies).toHaveProperty("@assistant-ui/react");
    expect(packageJson.dependencies).toHaveProperty("class-variance-authority");
    expect(packageJson.dependencies).toHaveProperty("clsx");
    expect(packageJson.dependencies).toHaveProperty("tailwind-merge");
  });
});

describe("className merge utility", () => {
  it("merges Tailwind class names with later conflict winners", () => {
    expect(cn("px-2 text-slate-500", "px-4", false, "text-slate-900")).toBe("px-4 text-slate-900");
  });
});

describe("shadcn component smoke imports", () => {
  it("exports the first required primitives", () => {
    expect(Button).toBeTypeOf("function");
    expect(Card).toBeTypeOf("function");
    expect(Dialog).toBeTypeOf("function");
    expect(SectionCard).toBeTypeOf("function");
  });
});

describe("global CSS guardrails", () => {
  it("does not define banned handwritten component selectors", () => {
    const css = readFileSync(resolve(__dirname, "../src/styles/global.css"), "utf8");
    const banned = [".button", ".section-card", ".kb-card", ".settings-dialog", ".status-badge"];

    for (const selector of banned) {
      expect(css).not.toContain(selector);
    }
  });

  it("locks the v1.1 emerald design tokens and slate surface palette", () => {
    const theme = readFileSync(resolve(__dirname, "../src/styles/theme.css"), "utf8");
    const globalCss = readFileSync(resolve(__dirname, "../src/styles/global.css"), "utf8");
    const sectionCardSource = readFileSync(resolve(__dirname, "../src/components/common/SectionCard.tsx"), "utf8");

    // 旧木色已退役，绝不允许回归
    const banned = [
      "#8a5a36",
      "#f4ede3",
      "#6f7b4d",
      "#efe1d2",
      "rgba(47, 36, 27",
    ];
    for (const fragment of banned) {
      expect(theme, `theme.css should not regress to wood/brown: ${fragment}`).not.toContain(fragment);
      expect(globalCss, `global.css should not regress to wood/brown: ${fragment}`).not.toContain(fragment);
    }

    // 新 token 必须存在
    expect(theme).toContain("--color-bg:              #F7F8FA;");
    expect(theme).toContain("--color-primary:         #059669;");
    expect(theme).toContain("--color-accent:          #4F46E5;");
    expect(theme).toContain("--color-border:          #E4E7EC;");

    // shadcn 变量已经切到 emerald（global.css :root）—— 必须是 hex，浏览器才能解析
    expect(globalCss).toContain("--primary: #059669;");
    expect(globalCss).toContain("--ring: #059669;");
    expect(globalCss).toContain("--sidebar-primary: #059669;");
    expect(globalCss).toContain("--border: #E4E7EC;");
    // v1.4: --accent 改为 emerald soft，避免 shadcn 控件用 indigo 出现紫
    expect(globalCss).toContain("--accent: #ECFDF5;");
    expect(globalCss).toContain("--accent-foreground: #047857;");

    // SectionCard 必须走新设计：白底 + slate 描边 + 轻阴影
    expect(sectionCardSource).toContain("border-slate-200");
    expect(sectionCardSource).toContain("bg-white");
    expect(sectionCardSource).toContain("shadow-sm");
  });
});
