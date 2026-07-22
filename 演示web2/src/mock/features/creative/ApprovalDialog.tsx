import { useCallback, useEffect, useState } from "react";
import { Check, Clock, X } from "@phosphor-icons/react";

import type { CreativeApi } from "./api";
import type { CreativeApprovalRequest } from "./types";

interface Props {
  api: CreativeApi;
  onResolved?: () => void;
}

function isStale(approval: CreativeApprovalRequest, now: number = Date.now()): boolean {
  if (!approval.expires_at) return false;
  const expires = Date.parse(approval.expires_at);
  return Number.isNaN(expires) ? false : expires < now;
}

export function ApprovalDialog({ api, onResolved }: Props) {
  const [approvals, setApprovals] = useState<CreativeApprovalRequest[]>([]);
  const [busy, setBusy] = useState<string>("");
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    try {
      const list = await api.listApprovals();
      setApprovals(list);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "加载审批列表失败");
    }
  }, [api]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const handleResolve = async (approvalId: string, action: "approve" | "deny") => {
    setBusy(approvalId);
    setError("");
    try {
      await api.resolveApproval(approvalId, action);
      await refresh();
      onResolved?.();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "审批操作失败");
    } finally {
      setBusy("");
    }
  };

  if (approvals.length === 0 && !error) {
    return <p className="hint">没有等待审批的工具调用。</p>;
  }

  return (
    <div className="creative-approval-dialog" aria-label="创造模式审批">
      {error && <p className="hint" role="alert">{error}</p>}
      {approvals.map((approval) => {
        const stale = isStale(approval);
        const disabled = stale || busy === approval.id;
        return (
          <div key={approval.id} className="creative-approval-card">
            <div className="creative-approval-head">
              <Clock size={16} weight={stale ? "bold" : "regular"} />
              <strong>{approval.capability}</strong>
              <span className="creative-approval-risk">{approval.risk_level}</span>
              {stale && <span className="creative-approval-stale">已过期</span>}
            </div>
            <div className="creative-approval-grid">
              <div className="creative-approval-field">
                <span className="creative-approval-label">运行 ID</span>
                <code>{approval.run_id}</code>
              </div>
              <div className="creative-approval-field">
                <span className="creative-approval-label">工具调用 ID</span>
                <code>{approval.request_payload.tool_call_id}</code>
              </div>
              {approval.request_payload.normalized_targets.length > 0 && (
                <div className="creative-approval-field">
                  <span className="creative-approval-label">目标</span>
                  <ul>
                    {approval.request_payload.normalized_targets.map((target, index) => (
                      <li key={`${index}-${target}`}>{target}</li>
                    ))}
                  </ul>
                </div>
              )}
              {Object.keys(approval.request_payload.arguments).length > 0 && (
                <div className="creative-approval-field">
                  <span className="creative-approval-label">参数</span>
                  <code>{JSON.stringify(approval.request_payload.arguments)}</code>
                </div>
              )}
            </div>
            <div className="creative-approval-actions">
              <button
                type="button"
                className="inline-action primary-inline"
                onClick={() => void handleResolve(approval.id, "approve")}
                disabled={disabled}
              >
                <Check size={16} /> 批准
              </button>
              <button
                type="button"
                className="inline-action"
                onClick={() => void handleResolve(approval.id, "deny")}
                disabled={disabled}
              >
                <X size={16} /> 拒绝
              </button>
            </div>
          </div>
        );
      })}
    </div>
  );
}
