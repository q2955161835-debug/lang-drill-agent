// 更新中心状态机与适配器。
// Web 开发模式返回 desktop_only 状态，不调用不可用的 Tauri API；
// 桌面模式通过 Tauri updater 插件检查、下载、安装和重启。

import { useCallback, useState } from "react";

export type UpdateState =
  | "idle"
  | "checking"
  | "available"
  | "downloading"
  | "ready_to_restart"
  | "up_to_date"
  | "failed"
  | "desktop_only";

export interface UpdateInfo {
  version: string;
  currentVersion: string;
  releaseNotes: string;
  downloadSize: number;
  isPrerelease: boolean;
}

export interface CheckResult {
  available: boolean;
  info?: UpdateInfo;
}

export interface UpdateAdapter {
  isDesktopSupported: () => boolean;
  check: () => Promise<CheckResult>;
  downloadAndInstall: () => Promise<void>;
  restart: () => Promise<void>;
}

export interface UpdaterMachine {
  state: UpdateState;
  info: UpdateInfo | null;
  error: string | null;
  check: () => Promise<void>;
  downloadAndInstall: () => Promise<void>;
  restart: () => Promise<void>;
}

export function createUpdaterMachine(adapter: UpdateAdapter): UpdaterMachine {
  const [state, setState] = useState<UpdateState>("idle");
  const [info, setInfo] = useState<UpdateInfo | null>(null);
  const [error, setError] = useState<string | null>(null);

  const check = useCallback(async () => {
    if (!adapter.isDesktopSupported()) {
      setState("desktop_only");
      return;
    }
    setState("checking");
    setError(null);
    try {
      const result = await adapter.check();
      if (result.available && result.info) {
        setInfo(result.info);
        setState("available");
      } else {
        setState("up_to_date");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setState("failed");
    }
  }, [adapter]);

  const downloadAndInstall = useCallback(async () => {
    setState("downloading");
    setError(null);
    try {
      await adapter.downloadAndInstall();
      setState("ready_to_restart");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setState("failed");
    }
  }, [adapter]);

  const restart = useCallback(async () => {
    try {
      await adapter.restart();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setState("failed");
    }
  }, [adapter]);

  return { state, info, error, check, downloadAndInstall, restart };
}

/**
 * Web 开发模式适配器：不调用任何 Tauri API，check() 直接进入 desktop_only 状态。
 */
export class DesktopOnlyUpdateAdapter implements UpdateAdapter {
  isDesktopSupported(): boolean {
    return false;
  }
  async check(): Promise<CheckResult> {
    return { available: false };
  }
  async downloadAndInstall(): Promise<void> {
    throw new Error("updates are only available in the desktop edition");
  }
  async restart(): Promise<void> {
    throw new Error("restart is only available in the desktop edition");
  }
}

/**
 * 检测当前是否运行在 Tauri 桌面环境。
 * 通过判断 window 上是否存在 __TAURI_INTERNALS__ 决定。
 */
export function isTauriDesktop(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

/**
 * 创建桌面更新适配器。
 * 仅在 Tauri 环境下可用，动态导入 @tauri-apps/plugin-updater 避免非桌面环境打包失败。
 * 签名验证由 Tauri updater 插件基于 latest.json 公钥自动完成。
 */
export async function createDesktopUpdateAdapter(): Promise<UpdateAdapter> {
  // 使用变量名阻止 Vite 在 Web 构建时静态解析这些仅桌面模式可用的包。
  // 这些包只在 Tauri 桌面环境运行时动态加载。
  const updaterSpecifier = "@tauri-apps/plugin-updater";
  const processSpecifier = "@tauri-apps/plugin-process";
  const updaterModule: any = await import(/* @vite-ignore */ updaterSpecifier);
  const processModule: any = await import(/* @vite-ignore */ processSpecifier);

  return {
    isDesktopSupported: () => true,
    async check(): Promise<CheckResult> {
      const update = await updaterModule.check();
      if (!update) {
        return { available: false };
      }
      return {
        available: true,
        info: {
          version: update.version,
          currentVersion: update.currentVersion ?? "",
          releaseNotes: update.body ?? "",
          downloadSize: 0,
          isPrerelease: true,
        },
      };
    },
    async downloadAndInstall(): Promise<void> {
      const update = await updaterModule.check();
      if (!update) {
        throw new Error("no update available to install");
      }
      await update.downloadAndInstall();
    },
    async restart(): Promise<void> {
      await processModule.relaunch();
    },
  };
}

/**
 * 根据运行环境自动选择适配器。
 * Web 模式返回 DesktopOnlyUpdateAdapter，桌面模式返回 createDesktopUpdateAdapter()。
 */
export async function resolveUpdateAdapter(): Promise<UpdateAdapter> {
  if (isTauriDesktop()) {
    try {
      return await createDesktopUpdateAdapter();
    } catch {
      return new DesktopOnlyUpdateAdapter();
    }
  }
  return new DesktopOnlyUpdateAdapter();
}
