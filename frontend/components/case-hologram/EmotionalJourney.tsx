"use client";

import { useTranslations } from "next-intl";

import { tEnum } from "@/lib/case-board-i18n";
import type { CaseBoard } from "@/lib/types";

interface EmotionalJourneyProps {
  caseBoard: CaseBoard | undefined;
}

/**
 * Emotional 模式聚合段：代价仪表 / 道德抉择 / 未回收伏笔三合一。
 * 同一标题下用 sub-heading 切区，节省一屏 vertical space。
 */
export function EmotionalJourney({ caseBoard }: EmotionalJourneyProps) {
  const t = useTranslations("play.case");
  const meter = caseBoard?.personal_cost_meter;
  const dilemmas = caseBoard?.moral_dilemma_log ?? [];
  const hooks = caseBoard?.unrecovered_hooks ?? [];

  const hasMeter = !!meter && hasAnyMeter(meter);
  const hasDilemmas = dilemmas.length > 0;
  const hasHooks = hooks.length > 0;

  if (!hasMeter && !hasDilemmas && !hasHooks) return null;

  return (
    <section style={{ display: "grid", gap: "var(--lv-s-4)" }}>
      <h2 className="lv-t-caps" style={{ color: "var(--lv-ink-3)" }}>
        {t("journey")}
      </h2>

      {hasMeter && (
        <SubSection title={t("personalCost")}>
          <CostMeter
            label={t("exposure")}
            value={meter!.exposure}
            max={10}
            color="var(--lv-warn)"
          />
          <CostMeter
            label={t("transformation")}
            value={meter!.transformation}
            max={10}
            color="var(--lv-accent)"
          />
          {meter?.trust_with_npcs &&
            Object.keys(meter.trust_with_npcs).length > 0 && (
              <div style={{ display: "grid", gap: "var(--lv-s-2)" }}>
                <span className="lv-t-caps" style={{ color: "var(--lv-ink-3)" }}>
                  {t("trustWithNpcs")}
                </span>
                <div style={{ display: "grid", gap: "var(--lv-s-2)" }}>
                  {Object.entries(meter.trust_with_npcs).map(([n, v]) => (
                    <SignedMeter key={n} label={n} value={v} max={10} />
                  ))}
                </div>
              </div>
            )}
        </SubSection>
      )}

      {hasDilemmas && (
        <SubSection title={t("moralDilemmas")}>
          <ol style={{ display: "grid", gap: "var(--lv-s-2)" }}>
            {dilemmas.map((entry, i) => {
              const decided = !!entry.choice;
              return (
                <li
                  key={`${entry.round}-${i}`}
                  style={{
                    borderRadius: "var(--lv-r-card)",
                    border: `1px solid ${decided ? "var(--lv-accent)" : "var(--lv-line)"}`,
                    background: decided ? "var(--lv-accent-soft)" : "transparent",
                    padding: "var(--lv-s-3) var(--lv-s-4)",
                    display: "grid",
                    gap: "var(--lv-s-2)",
                  }}
                >
                  <div className="flex items-center justify-between">
                    <span className="lv-t-caps" style={{ color: "var(--lv-ink-3)" }}>
                      {t("round")} {entry.round}
                    </span>
                    <span
                      className="lv-t-meta"
                      style={{
                        color: decided ? "var(--lv-accent)" : "var(--lv-ink-3)",
                      }}
                    >
                      {decided ? t("decided") : t("pending")}
                    </span>
                  </div>
                  <p className="lv-t-body" style={{ color: "var(--lv-ink)" }}>
                    {entry.dilemma}
                  </p>
                  {entry.options && entry.options.length > 0 && (
                    <div className="flex flex-wrap" style={{ gap: "var(--lv-s-1)" }}>
                      {entry.options.map((opt) => {
                        const isChoice = opt === entry.choice;
                        return (
                          <span
                            key={opt}
                            className="lv-t-meta"
                            style={{
                              borderRadius: "var(--lv-r-pill)",
                              border: `1px solid ${isChoice ? "var(--lv-accent)" : "var(--lv-line)"}`,
                              padding: "2px var(--lv-s-2)",
                              color: isChoice ? "var(--lv-accent)" : "var(--lv-ink-3)",
                            }}
                          >
                            {opt}
                          </span>
                        );
                      })}
                    </div>
                  )}
                  {entry.fallout_hint && (
                    <p
                      className="lv-t-meta"
                      style={{ color: "var(--lv-ink-3)", lineHeight: 1.6 }}
                    >
                      {entry.fallout_hint}
                    </p>
                  )}
                </li>
              );
            })}
          </ol>
        </SubSection>
      )}

      {hasHooks && (
        <SubSection title={t("hooks")}>
          <ul style={{ display: "grid", gap: "var(--lv-s-2)" }}>
            {hooks.map((h, i) => {
              const isAbandoned = h.status === "abandoned";
              const statusColor =
                h.status === "recovered"
                  ? "var(--lv-ok)"
                  : h.status === "open"
                    ? "var(--lv-accent)"
                    : "var(--lv-ink-3)";
              return (
                <li
                  key={`${h.round_raised}-${i}`}
                  style={{
                    borderRadius: "var(--lv-r-card)",
                    border: "1px solid var(--lv-line)",
                    padding: "var(--lv-s-2) var(--lv-s-3)",
                    opacity: isAbandoned ? 0.55 : 1,
                  }}
                >
                  <div className="flex items-center justify-between">
                    <span className="lv-t-caps" style={{ color: "var(--lv-ink-3)" }}>
                      {t("round")} {h.round_raised}
                    </span>
                    <span className="lv-t-meta" style={{ color: statusColor }}>
                      {tEnum(t, "hookStatus", h.status)}
                    </span>
                  </div>
                  <p
                    className="lv-t-body"
                    style={{
                      marginTop: "var(--lv-s-1)",
                      color: "var(--lv-ink-2)",
                      lineHeight: 1.6,
                      textDecoration: isAbandoned ? "line-through" : "none",
                    }}
                  >
                    {h.hook_text}
                  </p>
                </li>
              );
            })}
          </ul>
        </SubSection>
      )}
    </section>
  );
}

function hasAnyMeter(m: NonNullable<CaseBoard["personal_cost_meter"]>): boolean {
  return (
    typeof m.exposure === "number" ||
    typeof m.transformation === "number" ||
    (!!m.trust_with_npcs && Object.keys(m.trust_with_npcs).length > 0)
  );
}

function SubSection({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div style={{ display: "grid", gap: "var(--lv-s-2)" }}>
      <h3 className="lv-t-caps" style={{ color: "var(--lv-ink-3)" }}>
        {title}
      </h3>
      <div style={{ display: "grid", gap: "var(--lv-s-3)" }}>{children}</div>
    </div>
  );
}

function CostMeter({
  label,
  value,
  max,
  color,
}: {
  label: string;
  value: number | undefined;
  max: number;
  color: string;
}) {
  if (typeof value !== "number") return null;
  const pct = Math.max(0, Math.min(max, value)) / max;
  return (
    <div style={{ display: "grid", gap: "var(--lv-s-1)" }}>
      <div className="flex items-center justify-between">
        <span className="lv-t-meta" style={{ color: "var(--lv-ink-2)" }}>
          {label}
        </span>
        <span className="lv-t-meta" style={{ color: "var(--lv-ink-3)" }}>
          {value} / {max}
        </span>
      </div>
      <div
        aria-hidden="true"
        style={{
          position: "relative",
          height: 4,
          borderRadius: "var(--lv-r-pill)",
          background: "rgba(255, 255, 255, 0.06)",
        }}
      >
        <span
          style={{
            position: "absolute",
            inset: 0,
            right: `${(1 - pct) * 100}%`,
            background: color,
            borderRadius: "var(--lv-r-pill)",
          }}
        />
      </div>
    </div>
  );
}

function SignedMeter({
  label,
  value,
  max,
}: {
  label: string;
  value: number;
  max: number;
}) {
  const clamped = Math.max(-max, Math.min(max, value));
  const isNeg = clamped < 0;
  const pct = Math.abs(clamped) / max;
  const color = isNeg ? "var(--lv-danger)" : "var(--lv-ok)";
  return (
    <div style={{ display: "grid", gap: "var(--lv-s-1)" }}>
      <div className="flex items-center justify-between">
        <span className="lv-t-meta" style={{ color: "var(--lv-ink-2)" }}>
          {label}
        </span>
        <span className="lv-t-meta" style={{ color }}>
          {clamped > 0 ? `+${clamped}` : clamped}
        </span>
      </div>
      <div
        aria-hidden="true"
        style={{
          position: "relative",
          height: 4,
          borderRadius: "var(--lv-r-pill)",
          background: "rgba(255, 255, 255, 0.06)",
        }}
      >
        <span
          style={{
            position: "absolute",
            left: "50%",
            top: -2,
            bottom: -2,
            width: 1,
            background: "rgba(255, 255, 255, 0.18)",
          }}
        />
        <span
          style={{
            position: "absolute",
            top: 0,
            bottom: 0,
            background: color,
            borderRadius: "var(--lv-r-pill)",
            ...(isNeg
              ? { right: "50%", width: `${pct * 50}%` }
              : { left: "50%", width: `${pct * 50}%` }),
          }}
        />
      </div>
    </div>
  );
}
