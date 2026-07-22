import { describe, expect, it, vi } from "vitest";

import { getAgentRun } from "./client";

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
