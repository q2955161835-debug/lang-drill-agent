import { apiGet, apiPost } from "../../api";
import type {
  AgentRun,
  AgentRunApi,
  AgentRunDetail,
  AgentRunEvent,
} from "./types";

export async function getAgentRun(id: string): Promise<AgentRun> {
  const response = await apiGet<{ run: AgentRun }>(
    `/api/agent-runs/${encodeURIComponent(id)}`,
  );
  return response.run;
}

export async function getAgentRunDetail(id: string): Promise<AgentRunDetail> {
  return apiGet(`/api/agent-runs/${encodeURIComponent(id)}/plan`);
}

async function runAction(id: string, action: "pause" | "resume" | "cancel"): Promise<AgentRun> {
  const response = await apiPost<{ run: AgentRun }>(
    `/api/agent-runs/${encodeURIComponent(id)}/${action}`,
    {},
  );
  return response.run;
}

const EVENT_TYPES = [
  "plan_replaced",
  "step_claimed",
  "step_completed",
  "step_failed",
  "step_retry_scheduled",
  "tool_call_recorded",
  "tool_call_completed",
  "tool_call_failed",
  "approval_requested",
  "paused",
  "resumed",
  "cancelled",
  "replan_required",
  "run_completed",
];

export function subscribeAgentRun(
  id: string,
  onEvent: (event: AgentRunEvent) => void,
  after = 0,
): () => void {
  const source = new EventSource(
    `/api/agent-runs/${encodeURIComponent(id)}/events?after=${after}`,
  );
  const listeners = new Map<string, EventListener>();
  const accept = (eventType: string, event: MessageEvent<string>) => {
    onEvent({
      id: Number(event.lastEventId),
      event_type: eventType,
      payload: JSON.parse(event.data) as Record<string, unknown>,
    });
  };
  source.onmessage = (message) => accept("message", message);
  for (const eventType of EVENT_TYPES) {
    const listener: EventListener = (event) => accept(eventType, event as MessageEvent<string>);
    listeners.set(eventType, listener);
    source.addEventListener(eventType, listener);
  }
  return () => {
    for (const [eventType, listener] of listeners) {
      source.removeEventListener(eventType, listener);
    }
    source.close();
  };
}

export const agentRunApi: AgentRunApi = {
  getDetail: getAgentRunDetail,
  pause: (id) => runAction(id, "pause"),
  resume: (id) => runAction(id, "resume"),
  cancel: (id) => runAction(id, "cancel"),
  subscribe: (id, onEvent) => subscribeAgentRun(id, onEvent),
};
