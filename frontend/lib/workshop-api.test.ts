import { afterEach, describe, expect, it, vi } from "vitest";

import { streamAdminEvents } from "./workshop-api";

afterEach(() => {
  vi.restoreAllMocks();
});

function streamFromText(text: string): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      controller.enqueue(encoder.encode(text));
      controller.close();
    },
  });
}

describe("streamAdminEvents", () => {
  it("exposes SSE ids as event seq and reports completion", async () => {
    const onEvent = vi.fn();
    const onProgress = vi.fn();
    const onResult = vi.fn();

    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        streamFromText(
          [
            'id: 7\nevent: progress\ndata: {"phase":"outline","code":"started","message":"开始"}\n\n',
            'id: 8\nevent: result\ndata: {"draft_id":"d1"}\n\n',
            "id: 9\nevent: done\ndata: {}\n\n",
          ].join(""),
        ),
        { status: 200, headers: { "Content-Type": "text/event-stream" } },
      ),
    );

    const result = await streamAdminEvents("/api/workshop/generation-tasks/t1/stream", {
      onEvent,
      onProgress,
      onResult,
    });

    expect(result.completed).toBe(true);
    expect(onEvent).toHaveBeenCalledWith({
      name: "progress",
      seq: 7,
      payload: { phase: "outline", code: "started", message: "开始" },
    });
    expect(onProgress).toHaveBeenCalledWith({
      phase: "outline",
      code: "started",
      message: "开始",
      meta: undefined,
    });
    expect(onResult).toHaveBeenCalledWith({ draft_id: "d1" });
  });
});
