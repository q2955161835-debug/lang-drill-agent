// @vitest-environment jsdom

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import {
  I18nProvider,
  detectInitialLocale,
  useI18n,
} from "./I18nProvider";
import { UI_LOCALE_STORAGE_KEY } from "./types";

/** 测试用 Fixture，显示当前 locale 下的设置按钮文案。 */
function Fixture({ navigatorLanguage }: { navigatorLanguage?: string }) {
  return (
    <I18nProvider navigatorLanguage={navigatorLanguage}>
      <SettingsButton />
    </I18nProvider>
  );
}

function SettingsButton() {
  const { t } = useI18n();
  return <button>{t("app.settings")}</button>;
}

/** 聊天 Fixture，验证切换 locale 不影响模型回复内容。 */
function ChatFixture({ assistantText }: { assistantText: string }) {
  return (
    <I18nProvider>
      <ChatContent assistantText={assistantText} />
    </I18nProvider>
  );
}

function ChatContent({ assistantText }: { assistantText: string }) {
  const { t } = useI18n();
  return (
    <div>
      <p>{assistantText}</p>
      <button>{t("app.settings")}</button>
    </div>
  );
}

afterEach(() => {
  cleanup();
  localStorage.clear();
});

describe("I18nProvider locale detection", () => {
  it("uses a saved locale before the operating-system locale", () => {
    localStorage.setItem(UI_LOCALE_STORAGE_KEY, "ja-JP");
    render(<Fixture navigatorLanguage="en-US" />);
    // ja-JP 的设置按钮文案是「設定」
    expect(screen.getByText("設定")).toBeTruthy();
  });

  it("falls back to system locale when no saved locale exists", () => {
    render(<Fixture navigatorLanguage="en-US" />);
    expect(screen.getByText("Settings")).toBeTruthy();
  });

  it("falls back to zh-CN when system locale is unsupported", () => {
    render(<Fixture navigatorLanguage="fr-FR" />);
    expect(screen.getByText("设置")).toBeTruthy();
  });

  it("maps zh-TW to zh-CN via language prefix fallback", () => {
    render(<Fixture navigatorLanguage="zh-TW" />);
    expect(screen.getByText("设置")).toBeTruthy();
  });
});

describe("I18nProvider content language isolation", () => {
  it("changes only UI copy, not model content", () => {
    render(<ChatFixture assistantText="继续练习日语" />);
    // 模型回复内容不受 locale 影响
    expect(screen.getByText("继续练习日语")).toBeTruthy();
    // jsdom 默认 navigator.language 为 en-US，设置按钮显示英文
    expect(screen.getByText("Settings")).toBeTruthy();
  });
});

describe("detectInitialLocale", () => {
  it("returns saved locale first", () => {
    localStorage.setItem(UI_LOCALE_STORAGE_KEY, "en-US");
    expect(detectInitialLocale("ja-JP")).toBe("en-US");
  });

  it("returns system locale when no saved locale", () => {
    expect(detectInitialLocale("ja-JP")).toBe("ja-JP");
  });

  it("returns default zh-CN for unsupported locale", () => {
    expect(detectInitialLocale("ko-KR")).toBe("zh-CN");
  });

  it("returns default zh-CN for empty input", () => {
    expect(detectInitialLocale(undefined)).toBe("zh-CN");
  });
});
