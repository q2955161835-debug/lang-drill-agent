export type AgentRunStatus =
  | "queued"
  | "running"
  | "paused"
  | "completed"
  | "failed"
  | "cancelled";

export type AgentRun = {
  id: string;
  session_id?: string | null;
  task_type: string;
  status: AgentRunStatus;
  goal: string;
  completion_criteria: string[];
  plan_version?: number;
  error_code: string;
  created_at?: string;
  updated_at?: string;
};

export type AgentRunStep = {
  id: string;
  run_id: string;
  plan_version: number;
  sequence: number;
  title: string;
  description: string;
  tool_names: string[];
  completion_criteria: string[];
  status: string;
  attempts: number;
  max_attempts: number;
  lease_owner: string;
  lease_expires_at: string | null;
  evidence: Record<string, unknown>;
  error_code: string;
  created_at?: string;
  updated_at?: string;
};

export type AgentToolCall = {
  id: string;
  run_id: string;
  step_id: string;
  tool_name: string;
  status: string;
  input_payload: Record<string, unknown>;
  output_payload: Record<string, unknown>;
  evidence: Record<string, unknown>;
  error_code: string;
};

export type AgentApproval = {
  id: string;
  run_id: string;
  step_id: string;
  tool_call_id: string | null;
  capability: string;
  risk_level: string;
  status: string;
  request_payload: Record<string, unknown>;
  decision: Record<string, unknown>;
};

export type AgentRunDetail = {
  run: AgentRun;
  steps: AgentRunStep[];
  tool_calls: AgentToolCall[];
  approvals: AgentApproval[];
};

export type AgentRunEvent = {
  id: number;
  event_type: string;
  payload: Record<string, unknown>;
};

export type AgentRunApi = {
  getDetail(id: string): Promise<AgentRunDetail>;
  pause(id: string): Promise<AgentRun>;
  resume(id: string): Promise<AgentRun>;
  cancel(id: string): Promise<AgentRun>;
  subscribe(id: string, onEvent: (event: AgentRunEvent) => void): () => void;
};
