import type { ModelCapability } from "@/lib/types";
import {
  CAPABILITY_ICON_PATHS,
  CAPABILITY_LABELS,
} from "./shared";

interface TaCapsProps {
  caps: ModelCapability[];
  size?: number;
  states?: Partial<Record<ModelCapability, "on" | "fail" | undefined>>;
  onClickCap?: (cap: ModelCapability) => void;
  busy?: ModelCapability | null;
}

export function TaCaps({ caps, size = 20, states, onClickCap, busy }: TaCapsProps) {
  if (caps.length === 0) return null;
  return (
    <span className="inline-flex items-center gap-1.5">
      {caps.map((c) => {
        const d = CAPABILITY_ICON_PATHS[c];
        if (!d) return null;
        const state = states?.[c];
        const cls = state === "fail" ? "ta-cap fail" : state === "on" ? "ta-cap on" : "ta-cap";
        const isBusy = busy === c;
        const Tag = onClickCap ? "button" : "span";
        return (
          <Tag
            key={c}
            type={onClickCap ? "button" : undefined}
            className={cls}
            title={CAPABILITY_LABELS[c]}
            aria-label={CAPABILITY_LABELS[c]}
            onClick={onClickCap ? () => onClickCap(c) : undefined}
            style={{
              width: size,
              height: size,
              cursor: onClickCap ? "pointer" : undefined,
              opacity: isBusy ? 0.5 : 1,
            }}
          >
            <svg
              viewBox="0 0 20 20"
              fill="none"
              stroke="currentColor"
              strokeWidth={1.4}
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d={d} />
            </svg>
          </Tag>
        );
      })}
    </span>
  );
}
