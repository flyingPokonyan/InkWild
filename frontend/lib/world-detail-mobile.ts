export function compactMobileMeta(value: string, maxLength = 10): string {
  const [firstPart] = value.split(/[，,\/]/);
  const normalized = firstPart.trim();
  return normalized.length > maxLength
    ? `${normalized.slice(0, Math.max(1, maxLength - 1))}...`
    : normalized;
}

export function shouldShowWorldSynopsisToggle(description: string, threshold = 60): boolean {
  return description.trim().length > threshold;
}
