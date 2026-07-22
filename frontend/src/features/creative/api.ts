import { apiGet, apiPost } from "../../api";
import type {
  CreativeApprovalRequest,
  CreativeAuditEvent,
  CreativeModeSettingsState,
  CreativeRuntimeRepairResult,
  CreativeRuntimeStatus,
  CreativeStatusResponse,
  PermissionProfile,
} from "./types";

export type CreativeApi = {
  status(): Promise<CreativeStatusResponse>;
  runtimeStatus(): Promise<CreativeRuntimeStatus>;
  saveSettings(patch: Partial<CreativeModeSettingsState>): Promise<CreativeModeSettingsState>;
  listApprovals(): Promise<CreativeApprovalRequest[]>;
  resolveApproval(approvalId: string, action: "approve" | "deny"): Promise<{ ok: boolean }>;
  listAuditEvents(runId?: string): Promise<CreativeAuditEvent[]>;
  repairRuntime(): Promise<CreativeRuntimeRepairResult>;
  openRuntimeLog(): Promise<{ path: string }>;
};

export const creativeApi: CreativeApi = {
  status() {
    return apiGet("/api/creative/status");
  },
  runtimeStatus() {
    return apiGet("/api/creative/runtime-status");
  },
  async saveSettings(patch) {
    const response = await apiPost<{ settings: CreativeModeSettingsState }>("/api/creative/settings", patch);
    return response.settings;
  },
  async listApprovals() {
    const response = await apiGet<{ approvals: CreativeApprovalRequest[] }>("/api/creative/approvals");
    return response.approvals;
  },
  resolveApproval(approvalId, action) {
    return apiPost(`/api/creative/approvals/${encodeURIComponent(approvalId)}/resolve`, { action });
  },
  async listAuditEvents(runId = "") {
    const params = new URLSearchParams();
    if (runId) params.set("run_id", runId);
    const query = params.toString();
    const response = await apiGet<{ events: CreativeAuditEvent[] }>(
      `/api/creative/audit${query ? `?${query}` : ""}`,
    );
    return response.events;
  },
  repairRuntime() {
    return apiPost("/api/creative/runtime/repair", {});
  },
  openRuntimeLog() {
    return apiPost("/api/creative/runtime/open-log", {});
  },
};

export function isRuntimeReady(runtime: CreativeRuntimeStatus | undefined): boolean {
  return Boolean(runtime && runtime.ready && runtime.state === "ready");
}

export function isProfileValid(profile: string): profile is PermissionProfile {
  return profile === "request_approval" || profile === "smart_approval" || profile === "full_access" || profile === "custom";
}
