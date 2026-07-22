export type BridgeCommand = {
  type: string;
  requestId?: string;
  targetRequestId?: string;
  prompt?: string;
  provider?: string;
  model?: string;
  thinkingLevel?: string;
  [key: string]: unknown;
};

export type BridgeEvent = {
  type: string;
  requestId?: string;
  errorCode?: string;
  error?: string;
  [key: string]: unknown;
};

export type CommandHandler = (command: BridgeCommand) => void;
export type CommandErrorHandler = (error: unknown, line: string) => void;

export class JsonlCommandReader {
  private buffer = "";

  constructor(
    private readonly onCommand: CommandHandler,
    private readonly onError: CommandErrorHandler = () => undefined,
  ) {}

  push(chunk: string): void {
    this.buffer += chunk;
    while (true) {
      const newlineIndex = this.buffer.indexOf("\n");
      if (newlineIndex === -1) return;
      let line = this.buffer.slice(0, newlineIndex);
      this.buffer = this.buffer.slice(newlineIndex + 1);
      if (line.endsWith("\r")) line = line.slice(0, -1);
      if (!line) continue;
      try {
        this.onCommand(parseCommand(line));
      } catch (error: unknown) {
        this.onError(error, line);
      }
    }
  }

  end(): void {
    if (this.buffer.length === 0) return;
    let line = this.buffer;
    this.buffer = "";
    if (line.endsWith("\r")) line = line.slice(0, -1);
    if (!line) return;
    try {
      this.onCommand(parseCommand(line));
    } catch (error: unknown) {
      this.onError(error, line);
    }
  }
}

export function parseCommand(line: string): BridgeCommand {
  const value: unknown = JSON.parse(line);
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("command must be a JSON object");
  }
  const command = value as Record<string, unknown>;
  if (typeof command.type !== "string" || command.type.trim() === "") {
    throw new Error("command type is required");
  }
  return command as BridgeCommand;
}

export function encodeEvent(event: BridgeEvent): string {
  return `${JSON.stringify(event)}\n`;
}
