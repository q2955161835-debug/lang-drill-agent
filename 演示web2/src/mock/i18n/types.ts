// 国际化（i18n）类型定义。
// UiLocale 只覆盖应用壳、按钮、设置、状态、错误和帮助文案；
// 不影响模型回复语言、题目语言、用户自定义指令或学习资料。

/** 支持的界面语言。 */
export type UiLocale = "zh-CN" | "en-US" | "ja-JP";

/** 默认界面语言。 */
export const DEFAULT_UI_LOCALE: UiLocale = "zh-CN";

/** 支持的界面语言列表，按展示顺序排列。 */
export const UI_LOCALES: readonly UiLocale[] = ["zh-CN", "en-US", "ja-JP"];

/** 语言展示名称。 */
export const UI_LOCALE_LABELS: Record<UiLocale, string> = {
  "zh-CN": "简体中文",
  "en-US": "English",
  "ja-JP": "日本語",
};

/** 命名参数映射。 */
export type MessageParams = Record<string, string | number>;

/** 消息目录：键到字符串或带命名参数的模板函数。 */
export type MessageCatalog = Record<string, string>;

/** 本地存储键。 */
export const UI_LOCALE_STORAGE_KEY = "langdrill.uiLocale";
