import { useState } from "react";
import { ArrowClockwise, FileText, Warning } from "@phosphor-icons/react";

import type { CreativeApi } from "./api";
import type { CreativeRuntimeStatus } from "./types";

interface Props {
  runtime: CreativeRuntimeStatus;
  api: CreativeApi;
  onRepaired?: () => void;
}

export function RuntimeRepairPanel({ runtime, api, onRepaired }: Props) {
  const [busy, setBusy] = useState(false);
  const [detail, setDetail] = useState("");
  const [error, setError] = useState("");

  const handleRepair = async () => {
    setBusy(true);
    setError("");
    setDetail("");
    try {
      const result = await api.repairRuntime();
      if (result.ok) {
        setDetail(result.detail || "修复已完成，请刷新状态。");
        onRepaired?.();
      } else {
        setDetail(result.detail || "修复未成功，请查看日志。");
      }
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "修复请求失败");
    } finally {
      setBusy(false);
    }
  };

  const handleOpenLog = async () => {
    try {
      await api.openRuntimeLog();
    } catch {
      // ignore — path is still displayed below
    }
  };

  return (
    <section className="creative-repair-panel" aria-label="Pi 运行时修复">
      <div className="creative-repair-head">
        <Warning size={20} weight="bold" />
        <strong>Pi 运行时未就绪</strong>
      </div>
      <div className="creative-repair-grid">
        {runtime.failure_code && (
          <div className="creative-repair-field">
            <span className="creative-repair-label">失败码</span>
            <code>{runtime.failure_code}</code>
          </div>
        )}
        {runtime.version && (
          <div className="creative-repair-field">
            <span className="creative-repair-label">已安装版本</span>
            <code>{runtime.version}</code>
          </div>
        )}
        {runtime.attempted_steps && runtime.attempted_steps.length > 0 && (
          <div className="creative-repair-field creative-repair-steps">
            <span className="creative-repair-label">已尝试步骤</span>
            <ul>
              {runtime.attempted_steps.map((step, index) => (
                <li key={`${index}-${step}`}>{step}</li>
              ))}
            </ul>
          </div>
        )}
        {runtime.log_path && (
          <div className="creative-repair-field">
            <span className="creative-repair-label">日志路径</span>
            <code>{runtime.log_path}</code>
            <button
              type="button"
              className="inline-action"
              onClick={() => void handleOpenLog()}
              disabled={busy}
            >
              <FileText size={14} /> 打开日志目录
            </button>
          </div>
        )}
        {runtime.manual_install_command && (
          <div className="creative-repair-field creative-repair-manual">
            <span className="creative-repair-label">手动安装命令</span>
            <code>{runtime.manual_install_command}</code>
          </div>
        )}
      </div>
      <div className="creative-repair-actions">
        <button
          type="button"
          className="inline-action primary-inline"
          onClick={() => void handleRepair()}
          disabled={busy}
        >
          <ArrowClockwise size={16} /> {busy ? "修复中..." : "一键修复"}
        </button>
        {detail && <p className="creative-repair-detail" role="status">{detail}</p>}
        {error && <p className="creative-repair-error" role="alert">{error}</p>}
      </div>
    </section>
  );
}
