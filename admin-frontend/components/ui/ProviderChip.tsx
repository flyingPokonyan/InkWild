import { colorFromString } from "@/lib/format";
import { resolveProviderIcon } from "@/lib/providerIcon";
import type { ModelProviderSummary } from "@/lib/types";

const PROVIDER_TYPE_INITIALS: Record<string, string> = {
  openai_compatible: "OA",
  xai: "XA",
  gemini: "GM",
  seedream_image: "SD",
};

export function providerInitials(p: { name: string; provider_type: string }): string {
  return (
    PROVIDER_TYPE_INITIALS[p.provider_type] ||
    (p.name || "?").slice(0, 2).toUpperCase()
  );
}

export function providerColor(p: { id: string }): string {
  return colorFromString(p.id);
}

interface Props {
  provider:
    | Pick<ModelProviderSummary, "id" | "name" | "provider_type">
    | null
    | undefined;
  withName?: boolean;
}

export function ProviderChip({ provider, withName = true }: Props) {
  if (!provider) return <span className="dim-2">—</span>;

  const iconPath = resolveProviderIcon(provider.name, provider.provider_type);

  return (
    <span className="prov-chip">
      {iconPath ? (
        <span className="prov-logo" title={provider.name}>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={iconPath} alt="" width={18} height={18} loading="lazy" />
        </span>
      ) : (
        <span
          className="prov-ico"
          style={{ background: providerColor(provider) }}
        >
          {providerInitials(provider)}
        </span>
      )}
      {withName && <span>{provider.name}</span>}
    </span>
  );
}
