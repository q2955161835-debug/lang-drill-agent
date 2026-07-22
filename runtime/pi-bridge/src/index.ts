import { PiBridgeServer } from "./server.js";
import { createPiSession } from "./session.js";

const server = new PiBridgeServer({
  writeLine: (line) => process.stdout.write(line),
  createSession: (command) => createPiSession(command),
});

process.stdin.setEncoding("utf8");
process.stdin.on("data", (chunk: string) => server.push(chunk));
process.stdin.on("end", () => server.end());
