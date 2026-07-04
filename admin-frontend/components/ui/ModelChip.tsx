import { resolveModelIcon } from "@/lib/providerIcon";

interface ModelIconProps {
  modelId: string;
  displayName?: string | null;
}

export function ModelIcon({ modelId, displayName }: ModelIconProps) {
  const iconPath = resolveModelIcon(modelId, displayName);
  if (!iconPath) return null;

  return (
    <span className="prov-logo model-logo" title={displayName || modelId}>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={iconPath} alt="" width={18} height={18} loading="lazy" />
    </span>
  );
}

interface ModelChipProps extends ModelIconProps {
  showId?: boolean;
}

export function ModelChip({ modelId, displayName, showId = true }: ModelChipProps) {
  return (
    <span className="model-chip">
      <ModelIcon modelId={modelId} displayName={displayName} />
      <span className="model-copy">
        <span className="model-name">{displayName || modelId}</span>
        {showId && (
          <span className="mono dim model-id">
            {modelId}
          </span>
        )}
      </span>
    </span>
  );
}
