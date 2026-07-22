import { apiGet } from "../../api";
import type { AgentRun, AgentRunEvent } from "./types";

export async function getAgentRun(id: string): Promise<AgentRun> {
  const response = await apiGet<{ run: AgentRun }>(
    `/api/agent-runs/${encodeURIComponent(id)}`,
  );
  return response.run;
}

export function subscribeAgentRun(
  id: string,
  onEvent: (event: AgentRunEvent) => void,
  after = 0,
): () => void {
  const source = new EventSource(
    `/api/agent-runs/${encodeURIComponent(id)}/events?after=${after}`,
  );
  source.onmessage = (message) => {
    onEvent({
      id: Number(message.lastEventId),
      event_type: "message",
      payload: JSON.parse(message.data) as Record<string, unknown>,
    });
  };
  source.addEventListener("progress", (event) => {
    const message = event as MessageEvent<string>;
    onEvent({
      id: Number(message.lastEventId),
      event_type: "progress",
      payload: JSON.parse(message.data) as Record<string, unknown>,
    });
  });
  return () => source.close();
}
