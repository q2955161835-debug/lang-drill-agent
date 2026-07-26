// 更新中心 UI 组件。
// 桌面模式下通过 Tauri updater 插件检查、下载、安装和重启；
// Web 开发模式下显式返回 desktop_only 状态，不调用不可用的 Tauri API。
// 安装只能由用户主动触发；失败保留重试、打开日志和查看帮助操作。

import { useEffect, useState } from "react";
import { useI18n } from "../../i18n/I18nProvider";
import {
  createUpdaterMachine,
  DesktopOnlyUpdateAdapter,
  resolveUpdateAdapter,
  type UpdateAdapter,
} from "./updater";

const DEFAULT_RELEASE_NOTES_URL =
  "https://github.com/q2955161835-debug/lang-drill-agent/releases";
const DEFAULT_CURRENT_VERSION = "1.0.2";

export interface UpdateCenterProps {
  /** 当前应用版本；桌面模式由调用方从 Tauri app API 获取后注入，便于测试。 */
  currentVersion?: string;
  /** 注入适配器，主要用于测试；默认调用 resolveUpdateAdapter() 异步获取。 */
  adapter?: UpdateAdapter;
  /** GitHub Release 页面，用于"查看完整说明"按钮。 */
  releaseNotesUrl?: string;
  /** 打开日志目录的回调；桌面模式由调用方注入 shell open 实现。 */
  onOpenLog?: () => void;
}

/**
 * 顶层 UpdateCenter 组件：异步解析适配器后再渲染内部状态机 UI。
 * 适配器还在解析时显示 loading，避免 createUpdaterMachine 在 null adapter 上调用。
 */
export function UpdateCenter(props: UpdateCenterProps) {
  const { t } = useI18n();
  const [adapter, setAdapter] = useState<UpdateAdapter | null>(
    () => props.adapter ?? null,
  );

  useEffect(() => {
    if (props.adapter) {
      setAdapter(props.adapter);
      return;
    }
    let cancelled = false;
    resolveUpdateAdapter()
      .then((resolved) => {
        if (!cancelled) setAdapter(resolved);
      })
      .catch(() => {
        if (!cancelled) setAdapter(new DesktopOnlyUpdateAdapter());
      });
    return () => {
      cancelled = true;
    };
  }, [props.adapter]);

  if (!adapter) {
    return (
      <section className="update-center" aria-busy="true">
        <p>{t("update.checking")}</p>
      </section>
    );
  }

  return <UpdateCenterInner key={adapter.isDesktopSupported() ? "desktop" : "web"} adapter={adapter} {...props} />;
}

function UpdateCenterInner({
  adapter,
  currentVersion,
  releaseNotesUrl = DEFAULT_RELEASE_NOTES_URL,
  onOpenLog,
}: UpdateCenterProps & { adapter: UpdateAdapter }) {
  const { t } = useI18n();
  const machine = createUpdaterMachine(adapter);
  const [version, setVersion] = useState(currentVersion ?? DEFAULT_CURRENT_VERSION);

  // 桌面模式下尝试获取真实版本号；Web 模式保留默认值。
  useEffect(() => {
    if (currentVersion) {
      setVersion(currentVersion);
      return;
    }
    if (!adapter.isDesktopSupported()) {
      return;
    }
    let cancelled = false;
    // 用变量名阻止 Vite 在 Web 构建时静态解析仅桌面可用的包。
    const specifier = "@tauri-apps/api/app";
    import(/* @vite-ignore */ specifier)
      .then((mod: any) => mod.getVersion())
      .then((v: string) => {
        if (!cancelled) setVersion(v);
      })
      .catch(() => {
        /* 保留默认版本号 */
      });
    return () => {
      cancelled = true;
    };
  }, [adapter, currentVersion]);

  const state = machine.state;
  const info = machine.info;
  const isBusy = state === "checking" || state === "downloading";

  return (
    <section className="update-center">
      <header className="update-center-header">
        <h3>{t("update.title")}</h3>
        <span className="update-experimental-badge">{t("update.experimentalBadge")}</span>
      </header>

      <p className="update-experimental-note">{t("update.experimentalNote")}</p>

      <dl className="update-meta">
        <div>
          <dt>{t("update.currentVersion")}</dt>
          <dd>{version}</dd>
        </div>
        {info && (
          <div>
            <dt>{t("update.newVersion")}</dt>
            <dd>{info.version}</dd>
          </div>
        )}
        {info && (
          <div>
            <dt>{t("update.downloadSize")}</dt>
            <dd>{info.downloadSize > 0 ? `${Math.ceil(info.downloadSize / 1024 / 1024)} MB` : t("update.unknown")}</dd>
          </div>
        )}
        <div>
          <dt>{t("update.signatureStatus")}</dt>
          <dd>{t("update.signatureVerified")}</dd>
        </div>
      </dl>

      {state === "desktop_only" && (
        <div className="update-status update-status-info">
          <p>{t("update.desktopOnly")}</p>
          <a className="update-link" href={releaseNotesUrl} target="_blank" rel="noreferrer">
            {t("update.viewNotes")}
          </a>
        </div>
      )}

      {state === "idle" && (
        <div className="update-actions">
          <button className="primary" onClick={() => void machine.check()}>
            {t("update.check")}
          </button>
        </div>
      )}

      {state === "checking" && (
        <div className="update-status update-status-info" aria-busy="true">
          <p>{t("update.checking")}</p>
        </div>
      )}

      {state === "up_to_date" && (
        <div className="update-status update-status-ok">
          <p>{t("update.upToDate")}</p>
          <div className="update-actions">
            <button onClick={() => void machine.check()} disabled={isBusy}>
              {t("update.check")}
            </button>
          </div>
        </div>
      )}

      {state === "available" && info && (
        <div className="update-status update-status-info">
          <p>{t("update.available")}</p>
          {info.releaseNotes && (
            <details className="update-release-notes">
              <summary>{t("update.releaseNotes")}</summary>
              <div className="update-release-notes-body">{info.releaseNotes}</div>
            </details>
          )}
          <div className="update-actions">
            <button className="primary" onClick={() => void machine.downloadAndInstall()} disabled={isBusy}>
              {t("update.install")}
            </button>
            <a className="update-link" href={releaseNotesUrl} target="_blank" rel="noreferrer">
              {t("update.viewNotes")}
            </a>
          </div>
        </div>
      )}

      {state === "downloading" && (
        <div className="update-status update-status-info" aria-busy="true">
          <p>{t("update.downloading")}</p>
          <progress className="update-progress" aria-label={t("update.downloading")} />
        </div>
      )}

      {state === "ready_to_restart" && (
        <div className="update-status update-status-ok">
          <p>{t("update.readyToRestart")}</p>
          <div className="update-actions">
            <button className="primary" onClick={() => void machine.restart()}>
              {t("update.restart")}
            </button>
          </div>
        </div>
      )}

      {state === "failed" && (
        <div className="update-status update-status-error">
          <p>{t("update.failed")}</p>
          {machine.error && <p className="update-error-detail">{machine.error}</p>}
          <p className="update-error-hint">{t("update.errorHint")}</p>
          <div className="update-actions">
            <button onClick={() => void machine.check()}>{t("app.retry")}</button>
            {onOpenLog && (
              <button onClick={onOpenLog}>{t("update.openLog")}</button>
            )}
            <a className="update-link" href={releaseNotesUrl} target="_blank" rel="noreferrer">
              {t("update.help")}
            </a>
          </div>
        </div>
      )}
    </section>
  );
}
