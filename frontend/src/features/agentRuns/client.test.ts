import { afterEach, describe, expect, it, vi } from "vitest";

import { getAgentRun } from "./client";

class FakeEventSource {
  static lastUrl = "";
  addEventListener() {}
  removeEventListener() {}
  close() {}
  constructor(url: string) {
    FakeEventSource.lastUrl = url;
  }
}

async function captureSseUrl(apiBase: string | undefined): Promise<string> {
  FakeEventSource.lastUrl = "";
  vi.stubGlobal("EventSource", FakeEventSource);
  if (apiBase === undefined) {
    vi.stubEnv("VITE_LANGDRILL_API_BASE", "");
  } else {
    vi.stubEnv("VITE_LANGDRILL_API_BASE", apiBase);
  }
  // API 在 api.ts 模块加载时求值，所以必须在 stub 之后重新导入。
  vi.resetModules();
  const { subscribeAgentRun } = await import("./client");
  const unsubscribe = subscribeAgentRun("r1", () => {});
  unsubscribe();
  return FakeEventSource.lastUrl;
}

describe("agent run SSE endpoint", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
    vi.resetModules();
  });

  it("targets the local backend in packaged desktop builds", async () => {
    // 桌面版前端从 tauri asset protocol 加载，相对路径会解析到 http://tauri.localhost，
    // EventSource 永远到不了 FastAPI，而卡片没有 onerror 也没有轮询兜底，会静默冻住。
    const url = await captureSseUrl("http://127.0.0.1:18080");

    expect(url).toBe("http://127.0.0.1:18080/api/agent-runs/r1/events?after=0");
  });

  it("stays relative in web mode so the Vite proxy keeps working", async () => {
    const url = await captureSseUrl(undefined);

    expect(url).toBe("/api/agent-runs/r1/events?after=0");
  });
});

describe("agent run client", () => {
  it("loads the stable run envelope", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(
          JSON.stringify({
            run: { id: "r1", status: "running", task_type: "index" },
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      ),
    );

    await expect(getAgentRun("r1")).resolves.toMatchObject({
      id: "r1",
      status: "running",
      task_type: "index",
    });
  });
});
