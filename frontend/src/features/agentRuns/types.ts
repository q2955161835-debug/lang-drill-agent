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
  error_code: string;
  created_at?: string;
  updated_at?: string;
};

export type AgentRunEvent = {
  id: number;
  event_type: string;
  payload: Record<string, unknown>;
};
