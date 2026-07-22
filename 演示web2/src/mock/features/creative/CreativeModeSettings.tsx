import { useCallback, useEffect, useState } from "react";
import { Sparkle } from "@phosphor-icons/react";

import { creativeApi, type CreativeApi, isRuntimeReady } from "./api";
import { PermissionProfilePicker } from "./PermissionProfilePicker";
import { RuntimeRepairPanel } from "./RuntimeRepairPanel";
import type {
  CreativeModeSettingsState,
  CreativeRuntimeStatus,
  PermissionProfile,
} from "./types";

interface Props {
  api?: CreativeApi;
}

export function CreativeModeSettings({ api = creativeApi }: Props) {
  const [settings, setSettings] = useState<CreativeModeSettingsState | null>(null);
  const [runtime, setRuntime] = useState<CreativeRuntimeStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  const refresh = useCallback(async () => {
    try {
      const response = await api.status();
      setSettings(response.settings);
      setRuntime(response.runtime);
    } catch (exc) {
      setMessage(exc instanceof Error ? exc.message : "加载创造模式状态失败");
    }
  }, [api]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const ready = isRuntimeReady(runtime ?? undefined) || false;

  const handleToggle = async (enabled: boolean) => {
    if (!settings || !ready) return;
    setBusy(true);
    setMessage("");
    try {
      const saved = await api.saveSettings({ enabled });
      setSettings(saved);
    } catch (exc) {
      setMessage(exc instanceof Error ? exc.message : "保存设置失败");
    } finally {
      setBusy(false);
    }
  };

  const handleProfileChange = async (profile: PermissionProfile) => {
    if (!settings) return;
    setBusy(true);
    setMessage("");
    try {
      const saved = await api.saveSettings({ permission_profile: profile });
      setSettings(saved);
    } catch (exc) {
      setMessage(exc instanceof Error ? exc.message : "保存档位失败");
    } finally {
      setBusy(false);
    }
  };

  if (!settings || !runtime) {
    return <p className="hint" role="status">{message || "正在加载创造模式设置..."}</p>;
  }

  return (
    <div className="creative-settings">
      <div className="creative-head">
        <Sparkle size={20} weight="fill" />
        <strong>创造模式</strong>
        {runtime.version && <span className="creative-version">v{runtime.version}</span>}
      </div>

      {!ready && (
        <RuntimeRepairPanel runtime={runtime} api={api} onRepaired={() => void refresh()} />
      )}

      <label className={`check-row${!ready ? " is-disabled" : ""}`}>
        <input
          type="checkbox"
          aria-label="启用创造模式"
          checked={settings.enabled}
          disabled={!ready || busy}
          onChange={(event) => void handleToggle(event.target.checked)}
        />
        <span>
          <strong>启用创造模式</strong>
          <small>
            开启后可通过 Pi 运行时执行复杂代码任务，工具调用按所选档位进行策略审批。
          </small>
        </span>
      </label>

      <section className="creative-profile-section" aria-label="权限档位">
        <div className="creative-section-head">
          <strong>权限档位</strong>
          <small>选择工具调用的审批策略</small>
        </div>
        <PermissionProfilePicker
          value={settings.permission_profile}
          disabled={!settings.enabled || busy}
          onChange={(profile) => void handleProfileChange(profile)}
        />
      </section>

      {message && <p className="hint" role="alert">{message}</p>}
    </div>
  );
}
