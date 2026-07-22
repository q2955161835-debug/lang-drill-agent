// 国际化 Provider：locale 检测、持久化、翻译函数。
// locale 选择优先级：localStorage 保存值 > 系统精确匹配 > 语言回退 > 默认 zh-CN。

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { CATALOGS } from "./catalog";
import {
  DEFAULT_UI_LOCALE,
  UI_LOCALE_STORAGE_KEY,
  UI_LOCALES,
  type MessageParams,
  type UiLocale,
} from "./types";

/** useI18n 返回的上下文类型。 */
interface I18nContextValue {
  locale: UiLocale;
  setLocale: (locale: UiLocale) => void;
  t: (key: string, params?: MessageParams) => string;
}

const I18nContext = createContext<I18nContextValue | null>(null);

/**
 * 将系统语言映射到支持的 UiLocale。
 * 支持精确匹配和语言前缀回退（如 zh、en、ja）。
 */
function mapSystemLocale(systemLocale: string): UiLocale | null {
  if (!systemLocale) return null;
  const normalized = systemLocale.toLowerCase();
  // 精确匹配
  for (const locale of UI_LOCALES) {
    if (normalized === locale.toLowerCase()) return locale;
  }
  // 语言前缀回退
  if (normalized.startsWith("zh")) return "zh-CN";
  if (normalized.startsWith("en")) return "en-US";
  if (normalized.startsWith("ja")) return "ja-JP";
  return null;
}

/** 从 localStorage 读取保存的 locale。 */
function readSavedLocale(): UiLocale | null {
  try {
    const saved = localStorage.getItem(UI_LOCALE_STORAGE_KEY);
    if (saved && (UI_LOCALES as readonly string[]).includes(saved)) {
      return saved as UiLocale;
    }
  } catch {
    // localStorage 不可用时忽略
  }
  return null;
}

/** 检测初始 locale。 */
export function detectInitialLocale(
  navigatorLanguage: string | undefined,
): UiLocale {
  const saved = readSavedLocale();
  if (saved) return saved;
  const system = mapSystemLocale(navigatorLanguage ?? "");
  if (system) return system;
  return DEFAULT_UI_LOCALE;
}

/** 替换命名参数 {name} 为实际值。 */
function interpolate(template: string, params?: MessageParams): string {
  if (!params) return template;
  return template.replace(/\{(\w+)\}/g, (match, key: string) => {
    const value = params[key];
    return value !== undefined ? String(value) : match;
  });
}

interface I18nProviderProps {
  children: ReactNode;
  /** 测试用：覆盖 navigator.language。 */
  navigatorLanguage?: string;
}

export function I18nProvider({
  children,
  navigatorLanguage,
}: I18nProviderProps) {
  const [locale, setLocaleState] = useState<UiLocale>(() =>
    detectInitialLocale(navigatorLanguage ?? navigator?.language),
  );

  // 设置 document.lang 并持久化
  useEffect(() => {
    if (typeof document !== "undefined") {
      document.documentElement.lang = locale;
    }
  }, [locale]);

  const setLocale = useCallback((next: UiLocale) => {
    setLocaleState(next);
    try {
      localStorage.setItem(UI_LOCALE_STORAGE_KEY, next);
    } catch {
      // localStorage 不可用时忽略
    }
  }, []);

  const t = useCallback(
    (key: string, params?: MessageParams) => {
      const catalog = CATALOGS[locale];
      const template = catalog[key];
      if (template === undefined) {
        // 键缺失时返回键本身，便于开发期发现问题
        return key;
      }
      return interpolate(template, params);
    },
    [locale],
  );

  const value = useMemo<I18nContextValue>(
    () => ({ locale, setLocale, t }),
    [locale, setLocale, t],
  );

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

/** useI18n hook，必须在 I18nProvider 内使用。 */
export function useI18n(): I18nContextValue {
  const context = useContext(I18nContext);
  if (!context) {
    throw new Error("useI18n must be used within an I18nProvider");
  }
  return context;
}
