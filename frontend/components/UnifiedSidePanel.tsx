"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslations } from "next-intl";

import { buildContextSections } from "@/lib/context-drawer";
import { useGameStore } from "@/stores/game";

interface UnifiedSidePanelProps {
  open: boolean;
  mode: "docked" | "modal";
  onToggle: () => void;
}

function groupCluesByTime(clues: { content: string; foundAt: string }[]) {
  const groups: { time: string; items: string[] }[] = [];
  for (const clue of clues) {
    const last = groups[groups.length - 1];
    if (last && last.time === clue.foundAt) {
      last.items.push(clue.content);
    } else {
      groups.push({ time: clue.foundAt, items: [clue.content] });
    }
  }
  return groups;
}

/**
 * 自由模式右侧/底部抽屉。§12.5 同款规则：禁止全息特效堆叠。
 */
export function UnifiedSidePanel({ open, mode, onToggle }: UnifiedSidePanelProps) {
  const gameState = useGameStore((s) => s.gameState);
  const characterName = useGameStore((s) => s.characterName);
  const characterDesc = useGameStore((s) => s.characterDesc);
  const characterAbilities = useGameStore((s) => s.characterAbilities);
  const t = useTranslations("play");
  const ts = useTranslations("play.side");
  const tc = useTranslations("play.case");

  const [closing, setClosing] = useState(false);
  const panelRef = useRef<HTMLDivElement>(null);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const isDesktop = mode === "docked";

  const handleClose = useCallback(() => {
    if (closing) return;
    setClosing(true);
    timeoutRef.current = setTimeout(() => {
      setClosing(false);
      onToggle();
    }, 200);
  }, [closing, onToggle]);

  useEffect(() => {
    return () => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
    };
  }, []);

  const visitedLocations = useMemo(() => {
    if (!gameState) return [];
    return gameState.visited_locations.length > 0
      ? gameState.visited_locations
      : [gameState.current_location];
  }, [gameState]);

  if ((!open && !closing) || !gameState) return null;

  const { clues, npcs, inventory } = buildContextSections(gameState);
  const clueGroups = groupCluesByTime(clues);

  return (
    <>
      <button
        type="button"
        aria-label={t("closePanelGeneric")}
        onClick={handleClose}
        className="lv-theme fixed inset-0"
        style={{
          zIndex: "var(--lv-z-drawer)" as unknown as number,
          background: "rgba(6, 6, 10, 0.54)",
          backdropFilter: "blur(26px) brightness(0.5)",
          WebkitBackdropFilter: "blur(26px) brightness(0.5)",
          opacity: closing ? 0 : 1,
          transition: "opacity var(--lv-dur-fast) var(--lv-ease)",
        }}
      />

      <aside
        ref={panelRef}
        className="lv-theme fixed flex flex-col"
        style={{
          zIndex: "var(--lv-z-drawer)" as unknown as number,
          background: isDesktop ? "rgba(17, 17, 20, 0.78)" : "rgba(17, 17, 20, 0.86)",
          backdropFilter: "blur(28px) saturate(140%)",
          WebkitBackdropFilter: "blur(28px) saturate(140%)",
          border: "1px solid var(--lv-line)",
          overflow: "hidden",
          ...(isDesktop
            ? {
                top: 0,
                right: 0,
                height: "100dvh",
                width: 440,
                borderTopLeftRadius: "var(--lv-r-card)",
                borderBottomLeftRadius: "var(--lv-r-card)",
              }
            : {
                left: 0,
                right: 0,
                bottom: 0,
                maxHeight: "72dvh",
                borderTopLeftRadius: 20,
                borderTopRightRadius: 20,
                paddingBottom: "env(safe-area-inset-bottom)",
              }),
        }}
      >
        {!isDesktop && (
          <div
            aria-hidden="true"
            style={{
              flexShrink: 0,
              display: "flex",
              justifyContent: "center",
              padding: "10px 0 0",
            }}
          >
            <span
              style={{
                width: 38,
                height: 4,
                borderRadius: "var(--lv-r-pill)",
                background: "rgba(255, 255, 255, 0.16)",
              }}
            />
          </div>
        )}

        {/* Header */}
        <div
          className="flex shrink-0 items-center justify-between"
          style={{
            padding: isDesktop ? "var(--lv-s-4)" : "13px 16px 12px",
            borderBottom: "1px solid var(--lv-line)",
          }}
        >
          <div style={{ display: "grid", gap: "var(--lv-s-1)" }}>
            <span className="lv-t-caps" style={{ color: "var(--lv-ink-3)" }}>
              {t("identityCaps")}
            </span>
            <span className="lv-t-h3" style={{ color: "var(--lv-ink)" }}>
              {characterName || tc("title")}
            </span>
          </div>
          <button
            type="button"
            onClick={handleClose}
            aria-label={t("closePanelGeneric")}
            className="lv-t-meta"
            style={{
              color: "var(--lv-ink-3)",
              padding: "var(--lv-s-1) var(--lv-s-2)",
            }}
          >
            {isDesktop ? (
              <svg
                width="14"
                height="14"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.5"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d="M18 6 6 18" />
                <path d="m6 6 12 12" />
              </svg>
            ) : (
              tc("close")
            )}
          </button>
        </div>

        <div
          className="flex-1 overflow-y-auto"
          style={{
            padding: "var(--lv-s-4)",
            display: "flex",
            flexDirection: "column",
            gap: "var(--lv-s-6)",
          }}
        >
          {characterName && (
            <Section title={ts("profile")}>
              {characterDesc && (
                <p className="lv-t-narrative" style={{ color: "var(--lv-ink-2)" }}>
                  {characterDesc}
                </p>
              )}
              {characterAbilities.length > 0 && (
                <div
                  className="flex flex-wrap"
                  style={{ marginTop: "var(--lv-s-3)", gap: "var(--lv-s-2)" }}
                >
                  {characterAbilities.map((a) => (
                    <span
                      key={a}
                      className="lv-t-meta"
                      style={{
                        borderRadius: "var(--lv-r-pill)",
                        border: "1px solid var(--lv-line)",
                        padding: "2px var(--lv-s-2)",
                        color: "var(--lv-ink-2)",
                      }}
                    >
                      {a}
                    </span>
                  ))}
                </div>
              )}
            </Section>
          )}

          <Section title={ts("env")}>
            <div
              style={{
                borderRadius: "var(--lv-r-card)",
                border: "1px solid var(--lv-line)",
                padding: "var(--lv-s-3) var(--lv-s-4)",
              }}
            >
              <div className="lv-t-h3" style={{ color: "var(--lv-ink)" }}>
                {gameState.current_location}
              </div>
              <div
                className="lv-t-meta"
                style={{ marginTop: "var(--lv-s-1)", color: "var(--lv-ink-3)" }}
              >
                {gameState.current_time}
                {gameState.round_number != null && (
                  <span style={{ marginLeft: "var(--lv-s-3)" }}>
                    · {tc("round")} {gameState.round_number}
                  </span>
                )}
              </div>
              {visitedLocations.length > 1 && (
                <div
                  className="flex flex-wrap"
                  style={{
                    marginTop: "var(--lv-s-3)",
                    paddingTop: "var(--lv-s-3)",
                    borderTop: "1px solid var(--lv-line)",
                    gap: "var(--lv-s-2)",
                  }}
                >
                  {visitedLocations.map((loc) => (
                    <span
                      key={loc}
                      className="lv-t-meta"
                      style={{
                        color:
                          loc === gameState.current_location
                            ? "var(--lv-ink)"
                            : "var(--lv-ink-3)",
                      }}
                    >
                      {loc}
                    </span>
                  ))}
                </div>
              )}
            </div>
          </Section>

          <Section title={ts("inventory")}>
            {inventory.length === 0 ? (
              <p className="lv-t-meta" style={{ color: "var(--lv-ink-3)" }}>
                {ts("noInventory")}
              </p>
            ) : (
              <div className="flex flex-wrap" style={{ gap: "var(--lv-s-2)" }}>
                {inventory.map((item) => (
                  <span
                    key={item}
                    className="lv-t-body"
                    style={{
                      borderRadius: "var(--lv-r-pill)",
                      border: "1px solid var(--lv-line)",
                      padding: "var(--lv-s-1) var(--lv-s-3)",
                      color: "var(--lv-ink-2)",
                    }}
                  >
                    {item}
                  </span>
                ))}
              </div>
            )}
          </Section>

          <Section title={ts("people")}>
            {npcs.length === 0 ? (
              <p className="lv-t-meta" style={{ color: "var(--lv-ink-3)" }}>
                {ts("noPeople")}
              </p>
            ) : (
              <div style={{ display: "grid", gap: "var(--lv-s-2)" }}>
                {npcs.map((npc) => (
                  <div
                    key={npc.name}
                    className="flex items-center justify-between"
                    style={{
                      borderRadius: "var(--lv-r-card)",
                      border: "1px solid var(--lv-line)",
                      padding: "var(--lv-s-2) var(--lv-s-3)",
                    }}
                  >
                    <span className="lv-t-body" style={{ color: "var(--lv-ink-2)" }}>
                      {npc.name}
                    </span>
                    <span className="lv-t-meta" style={{ color: "var(--lv-ink-3)" }}>
                      {npc.attitude}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </Section>

          <Section title={`${ts("clues")} (${clues.length})`}>
            {clueGroups.length === 0 ? (
              <p className="lv-t-meta" style={{ color: "var(--lv-ink-3)" }}>
                {ts("noClues")}
              </p>
            ) : (
              <div style={{ display: "grid", gap: "var(--lv-s-4)" }}>
                {clueGroups.map((group) => (
                  <div key={group.time} style={{ display: "grid", gap: "var(--lv-s-2)" }}>
                    <div className="lv-t-caps" style={{ color: "var(--lv-ink-3)" }}>
                      {group.time}
                    </div>
                    <div style={{ display: "grid", gap: "var(--lv-s-2)" }}>
                      {group.items.map((item) => (
                        <div
                          key={item}
                          className="lv-t-body-long"
                          style={{
                            borderRadius: "var(--lv-r-card)",
                            border: "1px solid var(--lv-line)",
                            padding: "var(--lv-s-3)",
                            color: "var(--lv-ink-2)",
                          }}
                        >
                          {item}
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Section>
        </div>
      </aside>
    </>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section style={{ display: "grid", gap: "var(--lv-s-3)" }}>
      <h2 className="lv-t-caps" style={{ color: "var(--lv-ink-3)" }}>
        {title}
      </h2>
      {children}
    </section>
  );
}
