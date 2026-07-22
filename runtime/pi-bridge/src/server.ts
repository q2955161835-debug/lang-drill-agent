import { JsonlCommandReader, type BridgeCommand, type BridgeEvent } from "./protocol.js";

export type SessionEvent = {
  type: string;
  [key: string]: unknown;
};

export interface BridgeSession {
  prompt(prompt: string, emit: (event: SessionEvent) => void): Promise<void>;
  abort(): Promise<void>;
  dispose(): void;
}

export type BridgeToolRequest = {
  toolName: string;
  toolCallId: string;
  arguments: Record<string, unknown>;
};

export type BridgeToolResponse = {
  output: string;
  isError?: boolean;
};

export type ToolRequestHandler = (
  request: BridgeToolRequest,
) => Promise<BridgeToolResponse>;

export type BridgeServerOptions = {
  writeLine: (line: string) => void;
  createSession: (
    command: BridgeCommand,
    requestTool: ToolRequestHandler,
  ) => Promise<BridgeSession>;
};

type ActiveRun = {
  requestId: string;
  session: BridgeSession;
  cancelled: boolean;
  promise: Promise<void>;
};

export class PiBridgeServer {
  private readonly reader: JsonlCommandReader;
  private readonly activeRuns = new Map<string, ActiveRun>();
  private readonly pendingTasks = new Set<Promise<void>>();
  private readonly eventWaiters = new Map<string, Array<() => void>>();
  private readonly pendingToolRequests = new Map<
    string,
    (response: BridgeToolResponse) => void
  >();

  constructor(private readonly options: BridgeServerOptions) {
    this.reader = new JsonlCommandReader(
      (command) => {
        const task = this.dispatch(command).catch((error: unknown) => {
        this.emit({
          type: "run.failed",
          requestId: command.requestId,
          errorCode: "BRIDGE_DISPATCH_FAILED",
          error: error instanceof Error ? error.message : "bridge dispatch failed",
        });
      });
          this.pendingTasks.add(task);
          void task.finally(() => this.pendingTasks.delete(task));
        },
        (error) => {
          this.emit({
            type: "run.failed",
            errorCode: "INVALID_JSON",
            error: error instanceof Error ? error.message : "invalid JSON command",
          });
        },
      );
  }

  push(chunk: string): void {
    try {
      this.reader.push(chunk);
    } catch (error: unknown) {
      this.emit({
        type: "run.failed",
        errorCode: "INVALID_JSON",
        error: error instanceof Error ? error.message : "invalid JSON command",
      });
    }
  }

  end(): void {
    try {
      this.reader.end();
    } catch (error: unknown) {
      this.emit({
        type: "run.failed",
        errorCode: "INVALID_JSON",
        error: error instanceof Error ? error.message : "invalid JSON command",
      });
    }
  }

  async waitForIdle(): Promise<void> {
    while (this.pendingTasks.size > 0) {
      await Promise.all([...this.pendingTasks]);
    }
  }

  waitForEvent(type: string): Promise<void> {
    return new Promise((resolve) => {
      const waiters = this.eventWaiters.get(type) ?? [];
      waiters.push(resolve);
      this.eventWaiters.set(type, waiters);
    });
  }

  private async dispatch(command: BridgeCommand): Promise<void> {
    switch (command.type) {
      case "health":
      case "initialize":
        this.emit({ type: "ready", requestId: command.requestId });
        return;
      case "run":
        await this.run(command);
        return;
      case "cancel":
        await this.cancel(command);
        return;
      case "tool.result":
        this.resolveToolRequest(command);
        return;
      case "approve":
        this.emit({
          type: "approval.received",
          requestId: command.requestId,
          targetRequestId: command.targetRequestId,
        });
        return;
      case "shutdown":
        for (const active of this.activeRuns.values()) {
          active.cancelled = true;
          await active.session.abort();
        }
        this.emit({ type: "shutdown.completed", requestId: command.requestId });
        return;
      default:
        this.emit({
          type: "run.failed",
          requestId: command.requestId,
          errorCode: "UNKNOWN_COMMAND",
          error: `unknown bridge command: ${command.type}`,
        });
    }
  }

  private async run(command: BridgeCommand): Promise<void> {
    const requestId = this.requireRequestId(command);
    const prompt = typeof command.prompt === "string" ? command.prompt : "";
    if (!prompt.trim()) {
      this.emit({
        type: "run.failed",
        requestId,
        errorCode: "PROMPT_REQUIRED",
      });
      return;
    }
    if (this.activeRuns.has(requestId)) {
      this.emit({
        type: "run.failed",
        requestId,
        errorCode: "REQUEST_ALREADY_ACTIVE",
      });
      return;
    }

    const session = await this.options.createSession(
      command,
      (request) => this.requestTool(requestId, request),
    );
    const active: ActiveRun = {
      requestId,
      session,
      cancelled: false,
      promise: Promise.resolve(),
    };
    this.activeRuns.set(requestId, active);
    this.emit({ type: "run.started", requestId });

    const runPromise = (async () => {
      try {
        await session.prompt(prompt, (event) => {
          this.emit({ ...event, requestId });
        });
        if (!active.cancelled) {
          this.emit({ type: "run.completed", requestId });
        }
      } catch (error: unknown) {
        if (!active.cancelled) {
          this.emit({
            type: "run.failed",
            requestId,
            errorCode: "PI_RUN_FAILED",
            error: error instanceof Error ? error.message : "Pi run failed",
          });
        }
      } finally {
        this.activeRuns.delete(requestId);
        session.dispose();
      }
    })();
    active.promise = runPromise;
    await runPromise;
  }

  private async cancel(command: BridgeCommand): Promise<void> {
    const targetRequestId = command.targetRequestId ?? command.requestId;
    if (!targetRequestId) {
      this.emit({
        type: "run.failed",
        requestId: command.requestId,
        errorCode: "TARGET_REQUEST_REQUIRED",
      });
      return;
    }
    const active = this.activeRuns.get(targetRequestId);
    if (!active) {
      this.emit({
        type: "run.failed",
        requestId: command.requestId,
        errorCode: "REQUEST_NOT_ACTIVE",
      });
      return;
    }
    active.cancelled = true;
    this.cancelPendingTools(targetRequestId);
    await active.session.abort();
    this.emit({ type: "run.cancelled", requestId: targetRequestId });
  }

  private requestTool(
    requestId: string,
    request: BridgeToolRequest,
  ): Promise<BridgeToolResponse> {
    const key = `${requestId}:${request.toolCallId}`;
    if (this.pendingToolRequests.has(key)) {
      return Promise.resolve({
        output: "Duplicate tool request was rejected.",
        isError: true,
      });
    }
    this.emit({ type: "tool.requested", requestId, ...request });
    return new Promise((resolve) => {
      this.pendingToolRequests.set(key, resolve);
    });
  }

  private resolveToolRequest(command: BridgeCommand): void {
    const requestId = command.targetRequestId;
    const toolCallId = command.toolCallId;
    if (typeof requestId !== "string" || typeof toolCallId !== "string") {
      throw new Error("tool result targetRequestId and toolCallId are required");
    }
    const key = `${requestId}:${toolCallId}`;
    const resolve = this.pendingToolRequests.get(key);
    if (!resolve) throw new Error("tool request is not pending");
    this.pendingToolRequests.delete(key);
    resolve({
      output: typeof command.output === "string" ? command.output : "",
      isError: command.isError === true,
    });
    this.emit({ type: "tool.completed", requestId, toolCallId });
  }

  private cancelPendingTools(requestId: string): void {
    const prefix = `${requestId}:`;
    for (const [key, resolve] of this.pendingToolRequests) {
      if (!key.startsWith(prefix)) continue;
      this.pendingToolRequests.delete(key);
      resolve({ output: "Tool request cancelled.", isError: true });
    }
  }

  private requireRequestId(command: BridgeCommand): string {
    const requestId = command.requestId?.trim();
    if (!requestId) throw new Error("requestId is required");
    return requestId;
  }

  private emit(event: BridgeEvent): void {
    this.options.writeLine(`${JSON.stringify(event)}\n`);
    const waiters = this.eventWaiters.get(event.type);
    if (!waiters) return;
    this.eventWaiters.delete(event.type);
    for (const resolve of waiters) resolve();
  }
}
