import { ArrowDown, ArrowUp, type LucideIcon } from "lucide-react";

type DeltaDir = "up" | "down" | "up-bad" | "down-good";

interface Props {
  label: string;
  value: React.ReactNode;
  unit?: string;
  delta?: React.ReactNode;
  deltaDir?: DeltaDir;
  deltaLabel?: string;
  icon?: LucideIcon;
  sub?: React.ReactNode;
}

export function KpiCard({
  label,
  value,
  unit,
  delta,
  deltaDir,
  deltaLabel,
  icon: Icon,
  sub,
}: Props) {
  const upArrow = deltaDir === "up" || deltaDir === "up-bad";
  return (
    <div className="kpi">
      <div className="kpi-label">
        {Icon && (
          <span className="kpi-label-ico">
            <Icon size={13} />
          </span>
        )}
        {label}
      </div>
      <div className="kpi-value">
        {value}
        {unit && <span className="kpi-unit">{unit}</span>}
      </div>
      <div className="kpi-meta">
        {delta != null && (
          <span className="kpi-delta" data-dir={deltaDir}>
            {upArrow ? <ArrowUp size={10} /> : <ArrowDown size={10} />}
            {delta}
          </span>
        )}
        {(sub || deltaLabel) && <span>{sub || deltaLabel}</span>}
      </div>
    </div>
  );
}
