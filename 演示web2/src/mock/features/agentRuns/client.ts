import { API, apiGet, apiPost } from "../../api";
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
  // 必须带上 API 基础地址：桌面打包版的前端由 Tauri asset protocol 从 frontendDist 加载，
  // 相对路径会解析到 webview 自身的 origin 而不是本地后端（后端不提供静态 SPA），
  // EventSource 因此永远到不了 FastAPI，而这里没有 onerror、AgentRunCard 也没有轮询兜底，
  // 卡片会静默冻住。Web 模式下 API 为空字符串，行为与原先完全一致。
  // 具体的桌面后端地址由 VITE_LANGDRILL_API_BASE 注入，见 api.ts 与桌面构建脚本。
  const source = new EventSource(
    `${API}/api/agent-runs/${encodeURIComponent(id)}/events?after=${after}`,
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
