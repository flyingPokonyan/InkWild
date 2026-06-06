"use client";

import { useState } from "react";

type SharedEventPerception = {
  knows?: string;
  believes?: string;
  feels?: string;
};

type SharedEvent = {
  id: string;
  title: string;
  summary: string;
  era?: string;
  involved_npcs?: string[];
  perceptions?: Record<string, SharedEventPerception>;
  source_passage_ids?: string[];
};

export type SharedEventsData = SharedEvent[];

type Props = {
  sharedEvents?: SharedEventsData | null;
};

export function SharedEventsSection({ sharedEvents }: Props) {
  const [expandedId, setExpandedId] = useState<string | null>(null);

  if (!sharedEvents || sharedEvents.length === 0) return null;

  return (
    <section
      aria-labelledby="shared-events-heading"
      style={{
        borderRadius: "var(--lv-r-card)",
        border: "1px solid var(--lv-line-2)",
        background: "var(--lv-bg-1)",
        padding: "var(--lv-s-6)",
        display: "flex",
        flexDirection: "column",
        gap: "var(--lv-s-4)",
      }}
    >
      <header
        style={{
          display: "flex",
          alignItems: "baseline",
          justifyContent: "space-between",
          gap: "var(--lv-s-2)",
        }}
      >
        <h2
          id="shared-events-heading"
          className="lv-t-h2"
          style={{ margin: 0, color: "var(--lv-ink)" }}
        >
          共享事件
        </h2>
        <span className="lv-t-caps" style={{ color: "var(--lv-ink-4)" }}>
          READ-ONLY · {sharedEvents.length} 条
        </span>
      </header>

      <div
        style={{
          borderRadius: "var(--lv-r-card)",
          border: "1px solid var(--lv-line)",
          overflow: "hidden",
        }}
      >
        {/* Table header */}
        <div
          className="lv-t-caps"
          style={{
            display: "grid",
            gridTemplateColumns: "1fr 80px 1fr 80px",
            gap: "var(--lv-s-3)",
            padding: "var(--lv-s-2) var(--lv-s-4)",
            background: "var(--lv-bg-2)",
            color: "var(--lv-ink-3)",
            borderBottom: "1px solid var(--lv-line)",
          }}
        >
          <span>标题</span>
          <span>年代</span>
          <span>涉及 NPC</span>
          <span style={{ textAlign: "right" }}>来源</span>
        </div>

        {sharedEvents.map((ev, idx) => {
          const isExpanded = expandedId === ev.id;
          const perceptionEntries = Object.entries(ev.perceptions ?? {});
          const sourceCount = ev.source_passage_ids?.length ?? 0;

          return (
            <div
              key={ev.id}
              style={{
                borderBottom:
                  idx < sharedEvents.length - 1 ? "1px solid var(--lv-line)" : undefined,
              }}
            >
              {/* Row */}
              <button
                type="button"
                onClick={() => setExpandedId(isExpanded ? null : ev.id)}
                style={{
                  width: "100%",
                  background: "transparent",
                  border: 0,
                  cursor: "pointer",
                  display: "grid",
                  gridTemplateColumns: "1fr 80px 1fr 80px",
                  gap: "var(--lv-s-3)",
                  padding: "var(--lv-s-3) var(--lv-s-4)",
                  textAlign: "left",
                  minHeight: 44,
                  alignItems: "center",
                  transition: "background var(--lv-dur-fast) var(--lv-ease)",
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.background = "var(--lv-bg-2)";
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.background = "transparent";
                }}
                aria-expanded={isExpanded}
              >
                <span className="lv-t-body" style={{ color: "var(--lv-ink)", fontWeight: 500 }}>
                  {ev.title}
                </span>
                <span className="lv-t-meta" style={{ color: "var(--lv-ink-3)" }}>
                  {ev.era ?? "—"}
                </span>
                <div
                  style={{
                    display: "flex",
                    flexWrap: "wrap",
                    gap: "var(--lv-s-1)",
                  }}
                >
                  {(ev.involved_npcs ?? []).map((npc) => (
                    <span
                      key={npc}
                      className="lv-t-meta"
                      style={{
                        borderRadius: "var(--lv-r-pill)",
                        background: "var(--lv-bg-2)",
                        padding: "2px 8px",
                        color: "var(--lv-ink-2)",
                      }}
                    >
                      {npc}
                    </span>
                  ))}
                  {(ev.involved_npcs ?? []).length === 0 && (
                    <span className="lv-t-meta" style={{ color: "var(--lv-ink-4)" }}>
                      —
                    </span>
                  )}
                </div>
                <span
                  className="lv-t-meta"
                  style={{ color: "var(--lv-ink-4)", textAlign: "right" }}
                >
                  {sourceCount} 条
                </span>
              </button>

              {/* Expanded detail */}
              {isExpanded && (
                <div
                  style={{
                    padding: "var(--lv-s-4)",
                    borderTop: "1px solid var(--lv-line)",
                    background: "var(--lv-bg-0)",
                    display: "flex",
                    flexDirection: "column",
                    gap: "var(--lv-s-4)",
                  }}
                >
                  {/* Summary */}
                  <div>
                    <div
                      className="lv-t-caps"
                      style={{ color: "var(--lv-ink-3)", marginBottom: "var(--lv-s-1)" }}
                    >
                      摘要
                    </div>
                    <p
                      className="lv-t-body"
                      style={{ margin: 0, whiteSpace: "pre-wrap", color: "var(--lv-ink-2)" }}
                    >
                      {ev.summary}
                    </p>
                  </div>

                  {/* Perceptions */}
                  {perceptionEntries.length > 0 && (
                    <div>
                      <div
                        className="lv-t-caps"
                        style={{ color: "var(--lv-ink-3)", marginBottom: "var(--lv-s-2)" }}
                      >
                        NPC 视角
                      </div>
                      <div
                        style={{
                          display: "flex",
                          flexDirection: "column",
                          gap: "var(--lv-s-2)",
                        }}
                      >
                        {perceptionEntries.map(([npcName, p]) => (
                          <div
                            key={npcName}
                            style={{
                              borderRadius: "var(--lv-r-card)",
                              border: "1px solid var(--lv-line)",
                              padding: "var(--lv-s-3) var(--lv-s-4)",
                            }}
                          >
                            <div
                              className="lv-t-body"
                              style={{ fontWeight: 600, color: "var(--lv-ink)", marginBottom: "var(--lv-s-2)" }}
                            >
                              {npcName}
                            </div>
                            <div
                              style={{
                                display: "flex",
                                flexDirection: "column",
                                gap: "var(--lv-s-1)",
                              }}
                            >
                              {p.knows && (
                                <div className="lv-t-body">
                                  <span style={{ color: "var(--lv-ink-3)" }}>知道：</span>
                                  <span style={{ color: "var(--lv-ink-2)" }}>{p.knows}</span>
                                </div>
                              )}
                              {p.believes && (
                                <div className="lv-t-body">
                                  <span style={{ color: "var(--lv-ink-3)" }}>相信：</span>
                                  <span style={{ color: "var(--lv-ink-2)" }}>{p.believes}</span>
                                </div>
                              )}
                              {p.feels && (
                                <div className="lv-t-body">
                                  <span style={{ color: "var(--lv-ink-3)" }}>感受：</span>
                                  <span style={{ color: "var(--lv-ink-2)" }}>{p.feels}</span>
                                </div>
                              )}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Source passage IDs */}
                  {sourceCount > 0 && (
                    <div
                      className="lv-t-meta"
                      style={{ color: "var(--lv-ink-4)" }}
                    >
                      来源片段：{(ev.source_passage_ids ?? []).join("、")}
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </section>
  );
}
