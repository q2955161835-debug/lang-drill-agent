import { InMemoryCredentialStore } from "@earendil-works/pi-ai";
import { Type } from "typebox";
import {
  createAgentSession,
  defineTool,
  ModelRuntime,
  SessionManager,
} from "@earendil-works/pi-coding-agent";
import type { BridgeCommand } from "./protocol.js";
import type { BridgeSession, SessionEvent } from "./server.js";

export type ToolRequest = {
  toolName: string;
  toolCallId: string;
  arguments: Record<string, unknown>;
};

export type ToolResponse = {
  output: string;
  isError?: boolean;
};

export type PiSessionFactoryOptions = {
  authPath?: string;
  modelsPath?: string;
  apiKey?: string;
  onToolRequest?: (request: ToolRequest) => Promise<ToolResponse>;
};

export async function createPiSession(
  command: BridgeCommand,
  options: PiSessionFactoryOptions = {},
): Promise<BridgeSession> {
  const credentials = new InMemoryCredentialStore();
  const modelRuntime = await ModelRuntime.create({
    credentials,
    ...(options.authPath ? { authPath: options.authPath } : {}),
    ...(options.modelsPath ? { modelsPath: options.modelsPath } : {}),
  });
  if (command.provider && options.apiKey) {
    modelRuntime.setRuntimeApiKey(command.provider, options.apiKey);
  }
  const model = command.provider && command.model
    ? modelRuntime.getModel(command.provider, command.model)
    : undefined;

  const customTools = createPolicyProxyTools(options.onToolRequest);
  const { session } = await createAgentSession({
    modelRuntime,
    ...(model ? { model } : {}),
    ...(command.thinkingLevel ? { thinkingLevel: command.thinkingLevel as never } : {}),
    sessionManager: SessionManager.inMemory(),
    noTools: "all",
    customTools,
  });
  return new PiSdkBridgeSession(session, options.onToolRequest);
}

function createPolicyProxyTools(
  onToolRequest: PiSessionFactoryOptions["onToolRequest"],
) {
  const request = async (
    toolName: string,
    toolCallId: string,
    args: Record<string, unknown>,
  ): Promise<{
    content: [{ type: "text"; text: string }];
    details: { blocked: boolean; reasonCode: string; toolName: string };
    isError: boolean;
  }> => {
    if (!onToolRequest) {
      return {
        content: [{ type: "text" as const, text: "Tool policy gateway is unavailable." }],
        details: {
          blocked: true,
          reasonCode: "POLICY_GATEWAY_UNAVAILABLE",
          toolName,
        },
        isError: true,
      };
    }
    const result = await onToolRequest({ toolName, toolCallId, arguments: args });
    return {
      content: [{ type: "text" as const, text: result.output }],
      details: {
        blocked: false,
        reasonCode: result.isError ? "POLICY_TOOL_ERROR" : "POLICY_EXECUTED",
        toolName,
      },
      isError: result.isError ?? false,
    };
  };
  return [
    defineTool({
      name: "read",
      label: "Read",
      description: "Request a policy-checked file read.",
      parameters: Type.Object({ path: Type.String() }),
      execute: (toolCallId, params) => request("read", toolCallId, params),
    }),
    defineTool({
      name: "write",
      label: "Write",
      description: "Request a policy-checked file write.",
      parameters: Type.Object({ path: Type.String(), content: Type.String() }),
      execute: (toolCallId, params) => request("write", toolCallId, params),
    }),
    defineTool({
      name: "edit",
      label: "Edit",
      description: "Request a policy-checked exact file edit.",
      parameters: Type.Object({
        path: Type.String(),
        oldText: Type.String(),
        newText: Type.String(),
      }),
      execute: (toolCallId, params) => request("edit", toolCallId, params),
    }),
    defineTool({
      name: "bash",
      label: "Bash",
      description: "Request a policy-checked shell command.",
      parameters: Type.Object({ command: Type.String() }),
      execute: (toolCallId, params) => request("bash", toolCallId, params),
    }),
  ];
}

class PiSdkBridgeSession implements BridgeSession {
  constructor(
    private readonly session: {
      prompt: (prompt: string) => Promise<void>;
      subscribe: (listener: (event: any) => void) => () => void;
      abort: () => Promise<void>;
      dispose: () => void;
    },
    private readonly onToolRequest?: (request: ToolRequest) => Promise<ToolResponse>,
  ) {}

  async prompt(prompt: string, emit: (event: SessionEvent) => void): Promise<void> {
    const unsubscribe = this.session.subscribe((event: any) => {
      if (event.type === "message_update") {
        const delta = event.assistantMessageEvent;
        if (delta?.type === "text_delta") {
          emit({ type: "message.delta", delta: delta.delta });
        }
      } else if (event.type === "tool_execution_start") {
        emit({
          type: "tool.requested",
          toolCallId: event.toolCallId,
          toolName: event.toolName,
          arguments: event.args ?? {},
        });
      } else if (event.type === "tool_execution_end") {
        emit({
          type: "tool.completed",
          toolCallId: event.toolCallId,
          toolName: event.toolName,
          isError: event.isError,
        });
      }
    });
    try {
      await this.session.prompt(prompt);
    } finally {
      unsubscribe();
    }
  }

  abort(): Promise<void> {
    return this.session.abort();
  }

  dispose(): void {
    this.session.dispose();
  }
}
