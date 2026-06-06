"use client";

import { useState } from "react";

type EventTrigger = {
  npc_name?: string;
  condition_dsl?: string;
  intent_payload?: Record<string, unknown>;
  probability?: number;
};

type EventEffects = {
  world_state_changes?: Record<string, unknown>;
  spawn_clues?: string[];
  npc_mood_changes?: Record<string, string>;
};

type EventRumor = {
  text: string;
  knower_npcs?: string[];
};

type EventDataEntry = {
  id: string;
  kind: "npc_intent_driven" | "conditional";
  summary: string;
  trigger?: EventTrigger;
  effects?: EventEffects;
  rumors?: EventRumor[];
  disabled?: boolean;
  disabled_reason?: string;
};

export type EventsDataList = EventDataEntry[];

type Props = {
  eventsData?: EventsDataList | null;
};

const KIND_LABELS: Record<EventDataEntry["kind"], string> = {
  npc_intent_driven: "NPC 意图",
  conditional: "条件触发",
};

export function EventsDataSection({ eventsData }: Props) {
  const [expandedId, setExpandedId] = useState<string | null>(null);

  if (!eventsData || eventsData.length === 0) return null;

  const activeCount = eventsData.filter((e) => !e.disabled).length;

  return (
    <section
      aria-labelledby="events-data-heading"
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
          id="events-data-heading"
          className="lv-t-h2"
          style={{ margin: 0, color: "var(--lv-ink)" }}
        >
          世界事件
        </h2>
        <span className="lv-t-caps" style={{ color: "var(--lv-ink-4)" }}>
          READ-ONLY · {activeCount}/{eventsData.length} 启用
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
            gridTemplateColumns: "1fr 100px 1fr 60px 80px",
            gap: "var(--lv-s-3)",
            padding: "var(--lv-s-2) var(--lv-s-4)",
            background: "var(--lv-bg-2)",
            color: "var(--lv-ink-3)",
            borderBottom: "1px solid var(--lv-line)",
          }}
        >
          <span>ID</span>
          <span>类型</span>
          <span>触发条件</span>
          <span style={{ textAlign: "right" }}>Rumors</span>
          <span style={{ textAlign: "right" }}>状态</span>
        </div>

        {eventsData.map((ev, idx) => {
          const isExpanded = expandedId === ev.id;
          const rumorCount = ev.rumors?.length ?? 0;
          const dsl = ev.trigger?.condition_dsl ?? ev.trigger?.npc_name ?? "—";

          return (
            <div
              key={ev.id}
              style={{
                borderBottom:
                  idx < eventsData.length - 1 ? "1px solid var(--lv-line)" : undefined,
                opacity: ev.disabled ? 0.6 : 1,
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
                  gridTemplateColumns: "1fr 100px 1fr 60px 80px",
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
                <span
                  className="lv-t-meta"
                  style={{
                    fontFamily: "var(--lv-font-mono)",
                    color: "var(--lv-ink-2)",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                  }}
                >
                  {ev.id}
                </span>
                <span
                  className="lv-t-meta"
                  style={{
                    borderRadius: "var(--lv-r-pill)",
                    background: "var(--lv-bg-2)",
                    padding: "2px 8px",
                    color: "var(--lv-ink-3)",
                    display: "inline-block",
                  }}
                >
                  {KIND_LABELS[ev.kind] ?? ev.kind}
                </span>
                <span
                  className="lv-t-meta"
                  style={{
                    color: "var(--lv-ink-3)",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                    fontFamily: dsl !== "—" ? "var(--lv-font-mono)" : undefined,
                  }}
                >
                  {dsl}
                </span>
                <span
                  className="lv-t-meta"
                  style={{ color: "var(--lv-ink-3)", textAlign: "right" }}
                >
                  {rumorCount}
                </span>
                <span style={{ textAlign: "right" }}>
                  {ev.disabled ? (
                    <span
                      className="lv-t-caps"
                      style={{
                        borderRadius: "var(--lv-r-pill)",
                        background: "rgba(184,92,92,0.15)",
                        color: "var(--lv-danger)",
                        padding: "2px 8px",
                        display: "inline-block",
                      }}
                    >
                      禁用
                    </span>
                  ) : (
                    <span
                      className="lv-t-caps"
                      style={{
                        borderRadius: "var(--lv-r-pill)",
                        background: "rgba(92,184,92,0.15)",
                        color: "var(--lv-success, #5cb85c)",
                        padding: "2px 8px",
                        display: "inline-block",
                      }}
                    >
                      启用
                    </span>
                  )}
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

                  {/* Trigger details */}
                  {ev.trigger && (
                    <div>
                      <div
                        className="lv-t-caps"
                        style={{ color: "var(--lv-ink-3)", marginBottom: "var(--lv-s-1)" }}
                      >
                        触发器（raw）
                      </div>
                      <pre
                        className="lv-t-meta"
                        style={{
                          margin: 0,
                          padding: "var(--lv-s-3)",
                          borderRadius: "var(--lv-r-card)",
                          background: "var(--lv-bg-2)",
                          color: "var(--lv-ink-2)",
                          fontFamily: "var(--lv-font-mono)",
                          overflowX: "auto",
                          whiteSpace: "pre-wrap",
                          wordBreak: "break-all",
                        }}
                      >
                        {JSON.stringify(ev.trigger, null, 2)}
                      </pre>
                    </div>
                  )}

                  {/* Rumors */}
                  {rumorCount > 0 && (
                    <div>
                      <div
                        className="lv-t-caps"
                        style={{ color: "var(--lv-ink-3)", marginBottom: "var(--lv-s-2)" }}
                      >
                        谣言（{rumorCount} 条）
                      </div>
                      <ul
                        style={{
                          padding: 0,
                          listStyle: "none",
                          display: "flex",
                          flexDirection: "column",
                          gap: "var(--lv-s-2)",
                        }}
                      >
                        {(ev.rumors ?? []).map((r, i) => (
                          <li
                            key={i}
                            style={{
                              borderRadius: "var(--lv-r-card)",
                              border: "1px solid var(--lv-line)",
                              padding: "var(--lv-s-3) var(--lv-s-4)",
                            }}
                          >
                            <p
                              className="lv-t-body"
                              style={{ margin: 0, color: "var(--lv-ink-2)" }}
                            >
                              {r.text}
                            </p>
                            {(r.knower_npcs ?? []).length > 0 && (
                              <div
                                className="lv-t-meta"
                                style={{
                                  marginTop: "var(--lv-s-1)",
                                  color: "var(--lv-ink-4)",
                                }}
                              >
                                知情 NPC：{(r.knower_npcs ?? []).join("、")}
                              </div>
                            )}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {/* Disabled reason */}
                  {ev.disabled && ev.disabled_reason && (
                    <div
                      className="lv-t-body"
                      style={{
                        padding: "var(--lv-s-3) var(--lv-s-4)",
                        borderRadius: "var(--lv-r-card)",
                        background: "rgba(184,92,92,0.08)",
                        color: "var(--lv-danger)",
                      }}
                    >
                      禁用原因：{ev.disabled_reason}
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
