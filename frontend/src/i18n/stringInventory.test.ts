// 硬编码 UI 文案清单测试。
// 验证三语 catalog 键一致，且已迁移的高频文案不再以硬编码字面量出现在源码中。
// 允许的硬编码字面量：无障碍数据、标识符、测试夹具、模型/用户内容、CSS 类名、
// 属性键、英文技术词（如 Lang Drill Agent）。

import { describe, expect, it } from "vitest";

import { CATALOGS } from "./catalog";
import { UI_LOCALES } from "./types";

// 使用 Vite 原始导入读取源码，避免依赖 node:fs 类型声明。
const appSourceRaw = import.meta.glob("../App.tsx", { query: "?raw", import: "default", eager: true });
const appSource: string = appSourceRaw["../App.tsx"] as string;

describe("i18n catalog key parity", () => {
  it("every locale exposes the same set of message keys", () => {
    const reference = new Set(Object.keys(CATALOGS[UI_LOCALES[0]]));
    for (const locale of UI_LOCALES) {
      const keys = new Set(Object.keys(CATALOGS[locale]));
      expect(keys).toEqual(reference);
    }
  });

  it("no catalog key maps to an empty string", () => {
    for (const locale of UI_LOCALES) {
      for (const [key, value] of Object.entries(CATALOGS[locale])) {
        expect(value.length, `${locale}.${key} must not be empty`).toBeGreaterThan(0);
      }
    }
  });
});

describe("migrated shell copy uses the catalog", () => {
  // 这些是本轮已迁移到 catalog 的高频文案。
  // 它们不应再以硬编码中文字面量出现在 App.tsx 的 JSX/标题/按钮中。
  it("settings dialog title uses t() instead of a hard-coded literal", () => {
    expect(appSource).toContain('t("settings.title")');
    // 设置弹窗标题旧写法 <h2>设置</h2> 不应再出现
    expect(appSource).not.toContain("<h2>设置</h2>");
  });

  it("settings tab labels use t() instead of hard-coded Chinese literals", () => {
    // settingTabs 数组中不应再出现 label: "模型" 这类硬编码
    expect(appSource).not.toContain('label: "模型"');
    expect(appSource).not.toContain('label: "考试"');
    expect(appSource).not.toContain('label: "创造模式"');
    expect(appSource).not.toContain('label: "语言"');
    expect(appSource).toContain('label: t("settings.tab.model")');
    expect(appSource).toContain('label: t("settings.tab.language")');
  });

  it("new chat draft title uses t() instead of a hard-coded literal", () => {
    expect(appSource).toContain('t("app.newChat")');
    // 旧写法 title: "新聊天" 不应再出现
    expect(appSource).not.toContain('title: "新聊天"');
  });

  it("settings button uses t() for both label and title", () => {
    expect(appSource).toContain('t("app.settings.open")');
    expect(appSource).toContain('t("app.settings")');
  });

  it("save and cancel buttons in settings dialog use t()", () => {
    expect(appSource).toContain('t("app.cancel")');
    expect(appSource).toContain('t("app.save")');
    expect(appSource).toContain('t("settings.savePermissions")');
  });
});
