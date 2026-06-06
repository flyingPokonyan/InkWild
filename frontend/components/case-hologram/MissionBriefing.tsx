"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";

import { tEnum } from "@/lib/case-board-i18n";
import type { CaseBoard, TimePressure } from "@/lib/types";

interface MissionBriefingProps {
  caseBoard: CaseBoard | undefined;
  progressPhase: string;
}

const PREVIEW_COUNT = 5;

const PRESSURE_COLOR: Record<TimePressure, string> = {
  low: "var(--lv-ink-3)",
  medium: "var(--lv-accent)",
  high: "var(--lv-warn)",
  critical: "var(--lv-danger)",
};

/**
 * 案件板头部：当前目标 + 阶段 + 紧迫度 + 未解疑问。
 * 紧迫度只在非 low 时显示——避免每次打开都看到一个"低"徽章变成纯装饰。
 */
export function MissionBriefing({ caseBoard, progressPhase }: MissionBriefingProps) {
  const [showAnswered, setShowAnswered] = useState(false);
  const t = useTranslations("play.case");

  const currentObjective = caseBoard?.current_objective ?? "";
  const all = caseBoard?.unresolved_questions ?? [];
  const open = all.filter((q) => q.status !== "answered").slice(0, PREVIEW_COUNT);
  const answered = all.filter((q) => q.status === "answered");
  const unresolved = showAnswered ? [...open, ...answered] : open;
  const pressure = caseBoard?.time_pressure;
  const showPressure = pressure && pressure !== "low";

  if (!currentObjective && all.length === 0 && !progressPhase && !showPressure) {
    return (
      <section style={{ display: "grid", gap: "var(--lv-s-3)" }}>
        <h2 className="lv-t-caps" style={{ color: "var(--lv-ink-3)" }}>
          {t("briefing")}
        </h2>
        <p className="lv-t-body" style={{ color: "var(--lv-ink-3)" }}>
          {t("noData")}
        </p>
      </section>
    );
  }

  return (
    <section style={{ display: "grid", gap: "var(--lv-s-3)" }}>
      <div className="flex items-center justify-between">
        <h2 className="lv-t-caps" style={{ color: "var(--lv-ink-3)" }}>
          {t("briefing")}
        </h2>
        {showPressure && (
          <span
            className="lv-t-meta"
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: "var(--lv-s-1)",
              borderRadius: "var(--lv-r-pill)",
              border: `1px solid ${PRESSURE_COLOR[pressure]}`,
              padding: "2px var(--lv-s-2)",
              color: PRESSURE_COLOR[pressure],
            }}
          >
            <span
              aria-hidden="true"
              style={{
                width: 5,
                height: 5,
                borderRadius: "var(--lv-r-pill)",
                background: PRESSURE_COLOR[pressure],
              }}
            />
            {tEnum(t, "pressure", pressure)}
          </span>
        )}
      </div>

      {currentObjective && (
        <div
          style={{
            borderRadius: "var(--lv-r-card)",
            border: "1px solid var(--lv-accent)",
            background: "var(--lv-accent-soft)",
            padding: "var(--lv-s-3) var(--lv-s-4)",
          }}
        >
          <p className="lv-t-body-long" style={{ color: "var(--lv-ink)" }}>
            {currentObjective}
          </p>
        </div>
      )}

      {progressPhase && (
        <div className="flex items-center" style={{ gap: "var(--lv-s-2)" }}>
          <span
            aria-hidden="true"
            style={{
              display: "inline-block",
              width: 6,
              height: 6,
              borderRadius: "var(--lv-r-pill)",
              background: "var(--lv-accent)",
            }}
          />
          <span className="lv-t-meta" style={{ color: "var(--lv-ink-2)" }}>
            {progressPhase}
          </span>
        </div>
      )}

      {unresolved.length > 0 && (
        <div style={{ display: "grid", gap: "var(--lv-s-2)" }}>
          <h3 className="lv-t-caps" style={{ color: "var(--lv-ink-3)" }}>
            {t("unresolvedQuestions")}
          </h3>
          <ul style={{ display: "grid", gap: "var(--lv-s-2)" }}>
            {unresolved.map((q, i) => {
              const isAnswered = q.status === "answered";
              return (
                <li
                  key={`${i}-${q.question}`}
                  className="lv-t-body"
                  style={{
                    borderRadius: "var(--lv-r-card)",
                    border: "1px solid var(--lv-line)",
                    padding: "var(--lv-s-2) var(--lv-s-3)",
                    color: isAnswered ? "var(--lv-ink-3)" : "var(--lv-ink-2)",
                    textDecoration: isAnswered ? "line-through" : "none",
                  }}
                >
                  <span>{q.question}</span>
                  {isAnswered && q.answer && (
                    <p
                      className="lv-t-meta"
                      style={{
                        marginTop: "var(--lv-s-1)",
                        color: "var(--lv-ink-3)",
                        textDecoration: "none",
                      }}
                    >
                      {q.answer}
                    </p>
                  )}
                </li>
              );
            })}
          </ul>
          {answered.length > 0 && (
            <button
              type="button"
              onClick={() => setShowAnswered((v) => !v)}
              className="lv-t-meta"
              style={{
                alignSelf: "flex-start",
                background: "transparent",
                border: 0,
                padding: "var(--lv-s-1) 0",
                color: showAnswered ? "var(--lv-ink-3)" : "var(--lv-accent)",
                cursor: "pointer",
              }}
            >
              {showAnswered ? t("collapse") : t("showAnswered", { n: answered.length })}
            </button>
          )}
        </div>
      )}
    </section>
  );
}
