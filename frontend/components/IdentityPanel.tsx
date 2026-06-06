"use client";

import { useMemo } from "react";
import { useTranslations } from "next-intl";

import { useGameStore } from "@/stores/game";

interface IdentityPanelProps {
  open: boolean;
  onClose: () => void;
}

export function IdentityPanel({ open, onClose }: IdentityPanelProps) {
  const gameState = useGameStore((state) => state.gameState);
  const characterName = useGameStore((state) => state.characterName);
  const characterDesc = useGameStore((state) => state.characterDesc);
  const characterAbilities = useGameStore((state) => state.characterAbilities);
  const t = useTranslations("play");
  const ts = useTranslations("play.side");
  const tc = useTranslations("play.case");

  const visitedLocations = useMemo(() => {
    if (!gameState) return [];
    return gameState.visited_locations.length > 0
      ? gameState.visited_locations
      : [gameState.current_location];
  }, [gameState]);

  if (!open || !gameState) return null;

  return (
    <>
      <div
        className="lv-theme fixed inset-0"
        style={{
          zIndex: "var(--lv-z-drawer)" as unknown as number,
          background: "rgba(6, 6, 10, 0.55)",
          backdropFilter: "blur(12px) saturate(120%)",
          WebkitBackdropFilter: "blur(12px) saturate(120%)",
        }}
        onClick={onClose}
      />

      <div
        className="lv-theme fixed inset-y-0 right-0 flex flex-col"
        style={{
          zIndex: "var(--lv-z-drawer)" as unknown as number,
          width: 320,
          maxWidth: "85vw",
          background: "rgba(17, 17, 20, 0.78)",
          backdropFilter: "blur(28px) saturate(140%)",
          WebkitBackdropFilter: "blur(28px) saturate(140%)",
          borderLeft: "1px solid var(--lv-line)",
        }}
      >
        <div
          className="flex items-center justify-between"
          style={{
            padding: "var(--lv-s-4)",
            borderBottom: "1px solid var(--lv-line)",
          }}
        >
          <h2 className="lv-t-h3" style={{ color: "var(--lv-ink)" }}>
            {ts("profile")}
          </h2>
          <button
            type="button"
            onClick={onClose}
            aria-label={t("closePanelGeneric")}
            style={{
              padding: "var(--lv-s-1)",
              color: "var(--lv-ink-3)",
              borderRadius: "var(--lv-r-pill)",
            }}
          >
            <svg
              width="18"
              height="18"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M18 6 6 18" />
              <path d="m6 6 12 12" />
            </svg>
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
            <div
              style={{
                borderRadius: "var(--lv-r-card)",
                background: "var(--lv-accent-soft)",
                border: "1px solid var(--lv-accent)",
                padding: "var(--lv-s-4)",
              }}
            >
              <div className="lv-t-h3" style={{ color: "var(--lv-accent)" }}>
                {characterName}
              </div>
              {characterDesc && (
                <div
                  className="lv-t-body-long"
                  style={{ marginTop: "var(--lv-s-2)", color: "var(--lv-ink-2)" }}
                >
                  {characterDesc}
                </div>
              )}
              {characterAbilities.length > 0 && (
                <div
                  className="flex flex-wrap"
                  style={{ marginTop: "var(--lv-s-3)", gap: "var(--lv-s-1)" }}
                >
                  {characterAbilities.map((ability) => (
                    <span
                      key={ability}
                      className="lv-t-meta"
                      style={{
                        borderRadius: "var(--lv-r-pill)",
                        padding: "2px var(--lv-s-2)",
                        background: "rgba(255, 255, 255, 0.06)",
                        color: "var(--lv-ink)",
                      }}
                    >
                      {ability}
                    </span>
                  ))}
                </div>
              )}
            </div>
          )}

          <Section title={tc("location")}>
            <div className="lv-t-body" style={{ color: "var(--lv-ink)" }}>
              {gameState.current_location}
            </div>
            <div
              className="lv-t-meta"
              style={{ marginTop: "var(--lv-s-1)", color: "var(--lv-ink-3)" }}
            >
              {gameState.current_time}
              {gameState.round_number != null && ` · ${tc("round")} ${gameState.round_number}`}
            </div>
          </Section>

          <Section title={`${ts("clues")} (${gameState.discovered_clues.length})`}>
            {gameState.discovered_clues.length > 0 ? (
              <ul style={{ display: "grid", gap: "var(--lv-s-2)" }}>
                {gameState.discovered_clues.map((clue) => (
                  <li
                    key={clue.id}
                    style={{
                      borderRadius: "var(--lv-r-card)",
                      border: "1px solid var(--lv-line)",
                      padding: "var(--lv-s-2) var(--lv-s-3)",
                    }}
                  >
                    <div className="lv-t-body" style={{ color: "var(--lv-ink-2)" }}>
                      {clue.content}
                    </div>
                    <div
                      className="lv-t-meta"
                      style={{ marginTop: "var(--lv-s-1)", color: "var(--lv-ink-3)" }}
                    >
                      {clue.found_at}
                    </div>
                  </li>
                ))}
              </ul>
            ) : (
              <div className="lv-t-meta" style={{ color: "var(--lv-ink-3)" }}>
                {ts("noClues")}
              </div>
            )}
          </Section>

          {Object.keys(gameState.npc_relations).length > 0 && (
            <Section
              title={`${ts("people")} (${Object.keys(gameState.npc_relations).length})`}
            >
              <ul style={{ display: "grid", gap: "var(--lv-s-2)" }}>
                {Object.entries(gameState.npc_relations).map(([name, relation]) => (
                  <li
                    key={name}
                    style={{
                      borderRadius: "var(--lv-r-card)",
                      border: "1px solid var(--lv-line)",
                      padding: "var(--lv-s-2) var(--lv-s-3)",
                    }}
                  >
                    <div className="flex items-center justify-between">
                      <span className="lv-t-body" style={{ color: "var(--lv-ink)" }}>
                        {name}
                      </span>
                      <span className="lv-t-meta" style={{ color: "var(--lv-ink-3)" }}>
                        {tc("trust")} {relation.trust}/10
                      </span>
                    </div>
                    {relation.last_interaction && (
                      <div
                        className="lv-t-meta"
                        style={{ marginTop: "var(--lv-s-1)", color: "var(--lv-ink-3)" }}
                      >
                        {relation.last_interaction}
                      </div>
                    )}
                  </li>
                ))}
              </ul>
            </Section>
          )}

          <Section title={`${ts("inventory")} (${gameState.player_inventory.length})`}>
            {gameState.player_inventory.length > 0 ? (
              <div className="flex flex-wrap" style={{ gap: "var(--lv-s-2)" }}>
                {gameState.player_inventory.map((item) => (
                  <span
                    key={item}
                    className="lv-t-meta"
                    style={{
                      borderRadius: "var(--lv-r-pill)",
                      border: "1px solid var(--lv-line)",
                      padding: "2px var(--lv-s-2)",
                      color: "var(--lv-ink-2)",
                    }}
                  >
                    {item}
                  </span>
                ))}
              </div>
            ) : (
              <div className="lv-t-meta" style={{ color: "var(--lv-ink-3)" }}>
                {ts("noInventory")}
              </div>
            )}
          </Section>

          <Section title={`${tc("visited")} (${visitedLocations.length})`}>
            <ul style={{ display: "grid", gap: "var(--lv-s-1)" }}>
              {visitedLocations.map((location) => (
                <li
                  key={location}
                  className="lv-t-body"
                  style={{
                    borderRadius: "var(--lv-r-card)",
                    padding: "var(--lv-s-2) var(--lv-s-3)",
                    background:
                      location === gameState.current_location
                        ? "var(--lv-accent-soft)"
                        : "transparent",
                    color:
                      location === gameState.current_location
                        ? "var(--lv-accent)"
                        : "var(--lv-ink-2)",
                  }}
                >
                  {location}
                </li>
              ))}
            </ul>
          </Section>
        </div>
      </div>
    </>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section style={{ display: "grid", gap: "var(--lv-s-2)" }}>
      <div className="lv-t-caps" style={{ color: "var(--lv-ink-3)" }}>
        {title}
      </div>
      {children}
    </section>
  );
}
