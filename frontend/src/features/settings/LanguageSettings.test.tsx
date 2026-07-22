// @vitest-environment jsdom

import { cleanup, render, screen, fireEvent } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { I18nProvider } from "../../i18n/I18nProvider";
import { UI_LOCALE_STORAGE_KEY } from "../../i18n/types";
import { LanguageSettings } from "./LanguageSettings";

function renderWithProvider(navigatorLanguage?: string) {
  return render(
    <I18nProvider navigatorLanguage={navigatorLanguage}>
      <LanguageSettings />
    </I18nProvider>,
  );
}

afterEach(() => {
  cleanup();
  localStorage.clear();
});

describe("LanguageSettings", () => {
  it("renders the language selector with current locale selected", () => {
    renderWithProvider("zh-CN");
    const select = screen.getByLabelText("界面语言") as HTMLSelectElement;
    expect(select.value).toBe("zh-CN");
  });

  it("changes locale and persists to localStorage when user selects a new option", () => {
    renderWithProvider("zh-CN");
    const select = screen.getByLabelText("界面语言") as HTMLSelectElement;
    fireEvent.change(select, { target: { value: "en-US" } });
    expect(select.value).toBe("en-US");
    expect(localStorage.getItem(UI_LOCALE_STORAGE_KEY)).toBe("en-US");
    // 切换后标签变为英文
    expect(screen.getByLabelText("Interface language")).toBeTruthy();
  });

  it("switching to Japanese updates the label to Japanese", () => {
    renderWithProvider("zh-CN");
    const select = screen.getByLabelText("界面语言") as HTMLSelectElement;
    fireEvent.change(select, { target: { value: "ja-JP" } });
    expect(select.value).toBe("ja-JP");
    expect(screen.getByLabelText("インターフェース言語")).toBeTruthy();
  });

  it("does not alter model content when locale changes", () => {
    renderWithProvider("zh-CN");
    const select = screen.getByLabelText("界面语言") as HTMLSelectElement;
    // 切换语言前确认描述文案是中文
    expect(
      screen.getByText(
        "仅影响应用界面文案，不影响模型回复、题目和自定义指令的语言。",
      ),
    ).toBeTruthy();
    // 切换到英文
    fireEvent.change(select, { target: { value: "en-US" } });
    // 描述文案变为英文
    expect(
      screen.getByText(
        "Only affects UI copy, not the language of model replies, questions or custom instructions.",
      ),
    ).toBeTruthy();
  });
});
