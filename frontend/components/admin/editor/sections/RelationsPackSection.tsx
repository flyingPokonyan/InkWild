"use client";

import { useState } from "react";

type NpcRelation = {
  target: string;
  trust: number;
  kind?: string;
  why?: string;
};

export type RelationsPackData = {
  relations_by_npc?: Record<string, NpcRelation[]>;
};

type Props = {
  relationsPack?: RelationsPackData | null;
};

function trustColor(trust: number): string {
  if (trust > 0) return "var(--lv-success, #5cb85c)";
  if (trust < 0) return "var(--lv-danger)";
  return "var(--lv-ink-4)";
}

function trustLabel(trust: number): string {
  if (trust > 60) return "高度信任";
  if (trust > 20) return "信任";
  if (trust > 0) return "略微信任";
  if (trust === 0) return "中立";
  if (trust > -20) return "略微疑虑";
  if (trust > -60) return "不信任";
  return "敌对";
}

export function RelationsPackSection({ relationsPack }: Props) {
  const [expandedNpc, setExpandedNpc] = useState<string | null>(null);

  if (!relationsPack || !relationsPack.relations_by_npc) return null;

  const entries = Object.entries(relationsPack.relations_by_npc);
  if (entries.length === 0) return null;

  const totalRelations = entries.reduce((sum, [, rels]) => sum + rels.length, 0);

  return (
    <section
      aria-labelledby="relations-pack-heading"
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
          id="relations-pack-heading"
          className="lv-t-h2"
          style={{ margin: 0, color: "var(--lv-ink)" }}
        >
          NPC 关系网
        </h2>
        <span className="lv-t-caps" style={{ color: "var(--lv-ink-4)" }}>
          READ-ONLY · {entries.length} NPC · {totalRelations} 关系
        </span>
      </header>

      <ul
        style={{
          padding: 0,
          listStyle: "none",
          display: "flex",
          flexDirection: "column",
          gap: "var(--lv-s-2)",
        }}
      >
        {entries.map(([npcName, relations]) => {
          const isExpanded = expandedNpc === npcName;

          return (
            <li
              key={npcName}
              style={{
                borderRadius: "var(--lv-r-card)",
                border: "1px solid var(--lv-line)",
                overflow: "hidden",
              }}
            >
              {/* NPC header button */}
              <button
                type="button"
                onClick={() => setExpandedNpc(isExpanded ? null : npcName)}
                style={{
                  width: "100%",
                  background: "transparent",
                  border: 0,
                  cursor: "pointer",
                  display: "flex",
                  alignItems: "center",
                  gap: "var(--lv-s-3)",
                  padding: "var(--lv-s-3) var(--lv-s-4)",
                  textAlign: "left",
                  minHeight: 44,
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
                  style={{ color: "var(--lv-ink-4)", minWidth: 12 }}
                  aria-hidden
                >
                  {isExpanded ? "▼" : "▶"}
                </span>
                <span
                  className="lv-t-h3"
                  style={{ color: "var(--lv-ink)", flex: 1 }}
                >
                  {npcName}
                </span>
                <span className="lv-t-meta" style={{ color: "var(--lv-ink-3)" }}>
                  {relations.length} 条关系
                </span>
              </button>

              {/* Relations list */}
              {isExpanded && (
                <div
                  style={{
                    borderTop: "1px solid var(--lv-line)",
                    background: "var(--lv-bg-0)",
                  }}
                >
                  {relations.length === 0 && (
                    <p
                      className="lv-t-meta"
                      style={{
                        margin: 0,
                        padding: "var(--lv-s-3) var(--lv-s-4)",
                        color: "var(--lv-ink-4)",
                      }}
                    >
                      无关系记录
                    </p>
                  )}
                  {relations.map((rel, idx) => (
                    <div
                      key={`${rel.target}-${idx}`}
                      style={{
                        display: "grid",
                        gridTemplateColumns: "140px 90px 100px 1fr",
                        gap: "var(--lv-s-3)",
                        alignItems: "start",
                        padding: "var(--lv-s-3) var(--lv-s-4)",
                        borderBottom:
                          idx < relations.length - 1
                            ? "1px solid var(--lv-line)"
                            : undefined,
                      }}
                    >
                      {/* Target */}
                      <div
                        className="lv-t-body"
                        style={{ fontWeight: 500, color: "var(--lv-ink)" }}
                      >
                        → {rel.target}
                      </div>

                      {/* Trust */}
                      <div
                        style={{
                          display: "flex",
                          alignItems: "center",
                          gap: "var(--lv-s-1)",
                        }}
                      >
                        <span
                          className="lv-t-meta"
                          style={{
                            color: trustColor(rel.trust),
                            fontFamily: "var(--lv-font-mono)",
                            fontWeight: 600,
                          }}
                        >
                          {rel.trust > 0 ? `+${rel.trust}` : rel.trust}
                        </span>
                        <span className="lv-t-meta" style={{ color: "var(--lv-ink-3)" }}>
                          {trustLabel(rel.trust)}
                        </span>
                      </div>

                      {/* Kind */}
                      <div>
                        {rel.kind ? (
                          <span
                            className="lv-t-meta"
                            style={{
                              borderRadius: "var(--lv-r-pill)",
                              background: "var(--lv-bg-2)",
                              padding: "2px 8px",
                              color: "var(--lv-ink-3)",
                            }}
                          >
                            {rel.kind}
                          </span>
                        ) : (
                          <span className="lv-t-meta" style={{ color: "var(--lv-ink-4)" }}>
                            —
                          </span>
                        )}
                      </div>

                      {/* Why */}
                      <div>
                        {rel.why ? (
                          <p
                            className="lv-t-body"
                            style={{ margin: 0, color: "var(--lv-ink-2)" }}
                          >
                            {rel.why}
                          </p>
                        ) : (
                          <span className="lv-t-meta" style={{ color: "var(--lv-ink-4)" }}>
                            —
                          </span>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
