export type PermissionProfile = "request_approval" | "smart_approval" | "full_access" | "custom";

export type CreativeRuntimeState = "not_installed" | "installing" | "ready" | "install_failed" | "corrupt" | "unknown";

export interface CreativeRuntimeStatus {
  state: CreativeRuntimeState;
  version: string;
  error_code: string;
  details: Record<string, unknown>;
  updated_at: string;
  ready: boolean;
  log_path?: string;
  failure_code?: string;
  attempted_steps?: string[];
  manual_install_command?: string;
}

export interface CreativeModeSettingsState {
  enabled: boolean;
  permission_profile: PermissionProfile;
  rules_version: number;
  rules: CreativeRule[];
  created_at: string;
  updated_at: string;
}

export interface CreativeRule {
  id: string;
  tool?: string;
  path_pattern?: string;
  command_prefix?: string;
  network_domain?: string;
  confirmation: "allow" | "require_approval" | "deny";
  precedence: number;
}

export interface CreativeAuditEvent {
  id: string;
  run_id: string;
  session_id: string;
  event_type: string;
  reason_code: string;
  payload: Record<string, unknown>;
  created_at: string;
}

export interface CreativeApprovalRequest {
  id: string;
  run_id: string;
  step_id: string;
  capability: string;
  risk_level: string;
  tool_call_id: string;
  request_payload: {
    tool_call_id: string;
    arguments: Record<string, unknown>;
    normalized_targets: string[];
  };
  created_at: string;
  expires_at: string;
  status: "pending" | "approved" | "denied" | "expired";
}

export interface CreativeRuntimeRepairResult {
  ok: boolean;
  log_path: string;
  detail: string;
}

export interface CreativeStatusResponse {
  settings: CreativeModeSettingsState;
  runtime: CreativeRuntimeStatus;
  approvals: CreativeApprovalRequest[];
}

export const PERMISSION_PROFILE_LABELS: Record<PermissionProfile, string> = {
  request_approval: "请求批准",
  smart_approval: "智能审批",
  full_access: "完全访问",
  custom: "自定义",
};

export const PERMISSION_PROFILE_DESCRIPTIONS: Record<PermissionProfile, string> = {
  request_approval: "所有工具调用都需用户逐次确认，适合首次试用或高敏感场景。",
  smart_approval: "工作区内读写与常规命令直接放行，越界写入、联网和依赖安装仍需确认。",
  full_access: "仅保留不可覆盖的灾难性硬限制（递归毁坏根目录、破坏磁盘/引导/固件、隐蔽凭据外传、绕过审计），其余不再审批。",
  custom: "在智能审批基础上叠加自定义规则，按工具、路径、命令前缀和网络域名细化放行或审批。",
};

export const CATASTROPHIC_HARD_BLOCKS: string[] = [
  "未限定根目录的递归毁坏（如递归删除 C:\\）",
  "磁盘/分区/引导/固件破坏",
  "隐蔽凭据外传",
  "绕过或关闭本次策略与审计",
  "目标未解析的破坏性操作",
];
