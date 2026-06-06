export interface SSEBufferResult {
  blocks: string[];
  rest: string;
}

export function extractSSEBlocks(buffer: string): SSEBufferResult {
  const normalized = buffer.replace(/\r\n/g, "\n");
  const segments = normalized.split("\n\n");

  return {
    blocks: segments.slice(0, -1).filter((segment) => segment.trim().length > 0),
    rest: segments.at(-1) ?? "",
  };
}
