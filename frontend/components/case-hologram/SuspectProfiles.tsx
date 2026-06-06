"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";

import { tEnum } from "@/lib/case-board-i18n";
import type { CaseBoard, NpcDynamicEntry } from "@/lib/types";

interface SuspectProfilesProps {
  caseBoard: CaseBoard | undefined;
}

// Director may emit Chinese labels rather than the enum key; map them for
// visual treatment. Display text always goes through tEnum (which keeps the
// raw value if no translation exists).
const LEVEL_ALIAS: Record<string, "low" | "medium" | "high"> = {
  low: "low",
  medium: "medium",
  high: "high",
  低: "low",
  较低: "low",
  中: "medium",
  中等: "medium",
  高: "high",
  极高: "high",
};

const LEVEL_COLOR: Record<"low" | "medium" | "high", string> = {
  low: "var(--lv-ink-3)",
  medium: "var(--lv-warn)",
  high: "var(--lv-danger)",
};

/**
 * Mystery 模式嫌疑人列表。
 * 主信息：name + 等级左侧色条 + reason（自然语言，包含动机/不在场/关键证据）。
 * 展开：合并对应 NPC 的 trust / mood / current_stance / last_shift_reason。
 */
export function SuspectProfiles({ caseBoard }: SuspectProfilesProps) {
  const [expanded, setExpanded] = useState<string | null>(null);
  const t = useTranslations("play.case");

  const suspects = Array.isArray(caseBoard?.suspects) ? caseBoard.suspects : [];
  if (suspects.length === 0) return null;

  const npcDynamic = caseBoard?.npc_dynamic ?? {};

  return (
    <section style={{ display: "grid", gap: "var(--lv-s-3)" }}>
      <h2 className="lv-t-caps" style={{ color: "var(--lv-ink-3)" }}>
        {t("suspects")}
      </h2>
      <div style={{ display: "grid", gap: "var(--lv-s-2)" }}>
        {suspects.map((suspect) => {
          const rawLevel = suspect.suspicion_level;
          const level = LEVEL_ALIAS[rawLevel] ?? "low";
          const color = LEVEL_COLOR[level];
          const isOpen = expanded === suspect.name;
          const dyn = npcDynamic[suspect.name];

          return (
            <button
              key={suspect.name}
              type="button"
              onClick={() => setExpanded(isOpen ? null : suspect.name)}
              style={{
                width: "100%",
                position: "relative",
                borderRadius: "var(--lv-r-card)",
                border: "1px solid var(--lv-line)",
                background: "transparent",
                padding: "var(--lv-s-3) var(--lv-s-4)",
                paddingLeft: "calc(var(--lv-s-4) + 3px)",
                textAlign: "left",
                transition: "background var(--lv-dur-fast) var(--lv-ease)",
              }}
            >
              {/* Severity bar on the left edge — single hint of state, no chips. */}
              <span
                aria-hidden="true"
                style={{
                  position: "absolute",
                  left: 0,
                  top: "var(--lv-s-3)",
                  bottom: "var(--lv-s-3)",
                  width: 3,
                  background: color,
                  borderTopRightRadius: "var(--lv-r-pill)",
                  borderBottomRightRadius: "var(--lv-r-pill)",
                }}
              />

              <div className="flex items-center justify-between">
                <span className="lv-t-body" style={{ color: "var(--lv-ink)" }}>
                  {suspect.name}
                </span>
                <span className="lv-t-meta" style={{ color }}>
                  {tEnum(t, "suspicion", rawLevel)}
                </span>
              </div>

              {suspect.reason && (
                <p
                  className="lv-t-body"
                  style={{
                    marginTop: "var(--lv-s-2)",
                    color: "var(--lv-ink-2)",
                    lineHeight: 1.7,
                  }}
                >
                  {suspect.reason}
                </p>
              )}

              {isOpen && dyn && hasAnyDyn(dyn) && (
                <div
                  style={{
                    marginTop: "var(--lv-s-3)",
                    paddingTop: "var(--lv-s-3)",
                    borderTop: "1px solid var(--lv-line)",
                    display: "grid",
                    gap: "var(--lv-s-2)",
                  }}
                >
                  <DynRow label={t("trust")} value={dyn.trust} max={10} />
                  {dyn.mood && (
                    <Inline
                      label={t("mood")}
                      value={dyn.mood}
                      color="var(--lv-ink-2)"
                    />
                  )}
                  {dyn.current_stance && (
                    <Inline
                      label={t("stance")}
                      value={dyn.current_stance}
                      color="var(--lv-ink-2)"
                    />
                  )}
                  {dyn.last_shift_reason && (
                    <p
                      className="lv-t-meta"
                      style={{ color: "var(--lv-ink-3)", lineHeight: 1.6 }}
                    >
                      {dyn.last_shift_reason}
                    </p>
                  )}
                </div>
              )}
            </button>
          );
        })}
      </div>
    </section>
  );
}

function hasAnyDyn(d: NpcDynamicEntry): boolean {
  return (
    typeof d.trust === "number" ||
    !!d.mood ||
    !!d.current_stance ||
    !!d.last_shift_reason
  );
}

function DynRow({
  label,
  value,
  max,
}: {
  label: string;
  value: number | undefined;
  max: number;
}) {
  if (typeof value !== "number") return null;
  const pct = Math.max(0, Math.min(max, value)) / max;
  return (
    <div className="flex items-center" style={{ gap: "var(--lv-s-2)" }}>
      <span className="lv-t-caps" style={{ color: "var(--lv-ink-3)" }}>
        {label}
      </span>
      <span
        aria-hidden="true"
        style={{
          position: "relative",
          display: "inline-block",
          flex: 1,
          maxWidth: 100,
          height: 3,
          borderRadius: "var(--lv-r-pill)",
          background: "rgba(255, 255, 255, 0.08)",
        }}
      >
        <span
          style={{
            position: "absolute",
            inset: 0,
            right: `${(1 - pct) * 100}%`,
            background: "var(--lv-accent)",
            borderRadius: "var(--lv-r-pill)",
          }}
        />
      </span>
      <span className="lv-t-meta" style={{ color: "var(--lv-ink-2)" }}>
        {value}
      </span>
    </div>
  );
}

function Inline({
  label,
  value,
  color,
}: {
  label: string;
  value: string;
  color: string;
}) {
  return (
    <div className="lv-t-meta" style={{ color: "var(--lv-ink-3)" }}>
      {label} <span style={{ color }}>{value}</span>
    </div>
  );
}
