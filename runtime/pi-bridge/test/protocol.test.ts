import { describe, expect, it, vi } from "vitest";

import { JsonlCommandReader } from "../src/protocol.js";
import { PiBridgeServer, type BridgeSession } from "../src/server.js";

function parseLines(lines: string[]) {
  return lines.map((line) => JSON.parse(line) as Record<string, unknown>);
}

function fakeSession(onPrompt?: (prompt: string) => void): BridgeSession {
  return {
    prompt: async (prompt, emit) => {
      onPrompt?.(prompt);
      emit({ type: "message.delta", delta: `reply:${prompt}` });
    },
    abort: vi.fn(async () => undefined),
    dispose: vi.fn(),
  };
}

describe("strict JSONL framing", () => {
  it("splits only on LF and emits one JSON object per line", async () => {
    const received: unknown[] = [];
    const reader = new JsonlCommandReader((command) => received.push(command));

    reader.push('{"type":"health","requestId":"r1","note":"left\u2028right"}\r');
    expect(received).toEqual([]);
    reader.push("\n");

    expect(received).toEqual([
      { type: "health", requestId: "r1", note: "left\u2028right" },
    ]);
  });

  it("reports malformed input and continues reading later commands", async () => {
    const lines: string[] = [];
    const server = new PiBridgeServer({
      writeLine: (line) => lines.push(line),
      createSession: async () => fakeSession(),
    });

    server.push("{not-json}\n{\"type\":\"health\",\"requestId\":\"r1\"}\n");
    await server.waitForIdle();

    expect(parseLines(lines)).toEqual([
      expect.objectContaining({ type: "run.failed", errorCode: "INVALID_JSON" }),
      expect.objectContaining({ type: "ready", requestId: "r1" }),
    ]);
  });
});

describe("request-scoped sessions", () => {
  it("creates a fresh in-memory session for every run", async () => {
    const lines: string[] = [];
    const prompts: string[] = [];
    const createSession = vi.fn(async () => fakeSession((prompt) => prompts.push(prompt)));
    const server = new PiBridgeServer({
      writeLine: (line) => lines.push(line),
      createSession,
    });

    server.push(
      '{"type":"run","requestId":"a","prompt":"remember alpha"}\n' +
      '{"type":"run","requestId":"b","prompt":"what was alpha?"}\n',
    );
    await server.waitForIdle();

    expect(createSession).toHaveBeenCalledTimes(2);
    expect(prompts).toEqual(["remember alpha", "what was alpha?"]);
    expect(parseLines(lines).filter((event) => event.type === "run.completed")).toHaveLength(2);
  });

  it("propagates cancellation to the exact active request", async () => {
    const lines: string[] = [];
    let release: (() => void) | undefined;
    const session = fakeSession();
    session.prompt = () => new Promise<void>((resolve) => {
      release = resolve;
    });
    const server = new PiBridgeServer({
      writeLine: (line) => lines.push(line),
      createSession: async () => session,
    });

    server.push('{"type":"run","requestId":"a","prompt":"long task"}\n');
    await server.waitForEvent("run.started");
    server.push('{"type":"cancel","requestId":"cancel-a","targetRequestId":"a"}\n');
    await server.waitForEvent("run.cancelled");
    release?.();
    await server.waitForIdle();

    expect(session.abort).toHaveBeenCalledTimes(1);
    expect(parseLines(lines)).toContainEqual(
      expect.objectContaining({ type: "run.cancelled", requestId: "a" }),
    );
  });
});
