// 语言设置组件：允许用户选择界面语言并持久化。
// locale 只影响应用壳、按钮、设置、状态、错误和帮助文案；
// 不影响模型回复语言、题目语言、用户自定义指令或学习资料。

import { useI18n } from "../../i18n/I18nProvider";
import {
  UI_LOCALES,
  UI_LOCALE_LABELS,
  type UiLocale,
} from "../../i18n/types";

export function LanguageSettings() {
  const { locale, setLocale, t } = useI18n();

  const handleChange = (event: React.ChangeEvent<HTMLSelectElement>) => {
    const next = event.target.value as UiLocale;
    if ((UI_LOCALES as readonly string[]).includes(next)) {
      setLocale(next);
    }
  };

  return (
    <div className="language-settings">
      <label className="language-row">
        <span className="language-label">{t("language.label")}</span>
        <select
          aria-label={t("language.label")}
          value={locale}
          onChange={handleChange}
        >
          {UI_LOCALES.map((option) => (
            <option key={option} value={option}>
              {UI_LOCALE_LABELS[option]}
            </option>
          ))}
        </select>
      </label>
      <p className="language-description">{t("language.description")}</p>
    </div>
  );
}
