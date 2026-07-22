// 消息目录聚合与编译时键一致性校验。
// 英文和日文目录必须满足与中文源目录相同的 MessageCatalog 类型；
// 如果任一目录缺少或多余键，TypeScript 编译会失败。

import type { MessageCatalog, UiLocale } from "./types";
import { zhCN } from "./locales/zh-CN";
import { enUS } from "./locales/en-US";
import { jaJP } from "./locales/ja-JP";

/** 中文源目录，作为键的事实来源。 */
export const SOURCE_CATALOG: MessageCatalog = zhCN;

/** 编译时校验：英文目录必须与源目录键集完全一致。 */
const _enCheck: MessageCatalog = enUS;
void _enCheck;

/** 编译时校验：日文目录必须与源目录键集完全一致。 */
const _jaCheck: MessageCatalog = jaJP;
void _jaCheck;

/** 按语言聚合的目录映射。 */
export const CATALOGS: Record<UiLocale, MessageCatalog> = {
  "zh-CN": zhCN,
  "en-US": enUS,
  "ja-JP": jaJP,
};

/**
 * 运行时校验：所有目录的键集必须与源目录一致。
 * 在开发期发现键漂移；生产构建时由 TypeScript 类型保证。
 */
export function verifyCatalogKeys(): string[] {
  const sourceKeys = Object.keys(SOURCE_CATALOG).sort();
  const drift: string[] = [];
  for (const locale of ["en-US", "ja-JP"] as const) {
    const catalog = CATALOGS[locale];
    const keys = Object.keys(catalog).sort();
    const missing = sourceKeys.filter((key) => !keys.includes(key));
    const extra = keys.filter((key) => !sourceKeys.includes(key));
    if (missing.length || extra.length) {
      drift.push(
        `${locale}: missing=[${missing.join(",")}] extra=[${extra.join(",")}]`,
      );
    }
  }
  return drift;
}
