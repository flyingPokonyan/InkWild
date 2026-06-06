"use client";

import { AnimatePresence, motion } from "motion/react";
import { useEffect } from "react";
import { useTranslations } from "next-intl";

import { useGameStore } from "@/stores/game";
import { deriveProgressPhase } from "@/lib/case-board";
import { LV_DUR_PAGE, LV_EASE } from "@/lib/motion";
import type { CaseBoard, GameState } from "@/lib/types";

import { CluesList } from "./CluesList";
import { EmotionalJourney } from "./EmotionalJourney";
import { FieldIntel } from "./FieldIntel";
import { MissionBriefing } from "./MissionBriefing";
import { NpcDynamicList } from "./NpcDynamicList";
import { SuspectProfiles } from "./SuspectProfiles";

interface CaseHologramPanelProps {
  open: boolean;
  mode: "docked" | "modal";
  onToggle: () => void;
}

const PANEL_TRANSITION = { duration: LV_DUR_PAGE, ease: LV_EASE };

export function CaseHologramPanel({ open, mode, onToggle }: CaseHologramPanelProps) {
  const gameState = useGameStore((s) => s.gameState);
  const scriptType = useGameStore((s) => s.scriptType);
  const t = useTranslations("play.case");

  // Esc to close.
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onToggle();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open, onToggle]);

  const caseBoard = (gameState?.case_board ?? undefined) as CaseBoard | undefined;
  const currentAct =
    (gameState?.narrative_arc?.current_act as string | undefined) ?? "";
  const progressPhase =
    caseBoard?.progress_phase ?? deriveProgressPhase(scriptType, currentAct);

  const isDocked = mode === "docked";

  const panelInitial = isDocked
    ? { x: 24, opacity: 0 }
    : { y: "100%", opacity: 0 };
  const panelAnimate = isDocked ? { x: 0, opacity: 1 } : { y: 0, opacity: 1 };
  const panelExit = isDocked
    ? { x: 24, opacity: 0 }
    : { y: "100%", opacity: 0 };

  return (
    <AnimatePresence>
      {open && (
        <>
          {/* Scrim: light dim + thin blur. Docked mode keeps the play area
              legible behind it (not a true modal); mobile modal goes a bit
              darker since the panel covers most of the screen anyway. */}
          <motion.button
            key="scrim"
            type="button"
            aria-label={t("close")}
            onClick={onToggle}
            className="lv-theme fixed inset-0"
            style={{
              zIndex: "var(--lv-z-drawer)" as unknown as number,
              background: isDocked ? "rgba(0, 0, 0, 0.32)" : "rgba(6, 6, 10, 0.54)",
              backdropFilter: isDocked ? "blur(6px)" : "blur(26px) brightness(0.5)",
              WebkitBackdropFilter: isDocked ? "blur(6px)" : "blur(26px) brightness(0.5)",
              border: 0,
              padding: 0,
            }}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={PANEL_TRANSITION}
          />

          <motion.aside
            key="panel"
            className="lv-theme fixed flex flex-col"
            style={{
              zIndex: "var(--lv-z-drawer)" as unknown as number,
              background: isDocked ? "var(--lv-bg-1)" : "rgba(17, 17, 20, 0.86)",
              backdropFilter: isDocked ? undefined : "blur(28px) saturate(140%)",
              WebkitBackdropFilter: isDocked ? undefined : "blur(28px) saturate(140%)",
              border: "1px solid var(--lv-line)",
              overflow: "hidden",
              boxShadow: isDocked
                ? "-24px 0 48px rgba(0, 0, 0, 0.4)"
                : "0 -24px 48px rgba(0, 0, 0, 0.4)",
              ...(isDocked
                ? {
                    top: 0,
                    right: 0,
                    height: "100dvh",
                    width: "min(440px, 92vw)",
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
            initial={panelInitial}
            animate={panelAnimate}
            exit={panelExit}
            transition={PANEL_TRANSITION}
          >
            {/* Drag handle for mobile (visual affordance only) */}
            {!isDocked && (
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

            <div
              className="flex shrink-0 items-center justify-between"
              style={{
                padding: isDocked ? "var(--lv-s-4)" : "13px 16px 12px",
                borderBottom: "1px solid var(--lv-line)",
              }}
            >
              <span className="lv-t-caps" style={{ color: "var(--lv-ink-3)" }}>
                {t("title")}
              </span>
              <button
                type="button"
                onClick={onToggle}
                aria-label={t("close")}
                style={{
                  width: isDocked ? 32 : "auto",
                  height: 32,
                  display: "grid",
                  placeItems: "center",
                  color: "var(--lv-ink-3)",
                  background: "transparent",
                  border: 0,
                  borderRadius: "var(--lv-r-pill)",
                  padding: isDocked ? 0 : "0 var(--lv-s-2)",
                  fontSize: "var(--lv-t-meta)",
                  cursor: "pointer",
                  transition:
                    "color var(--lv-dur-fast) var(--lv-ease), background var(--lv-dur-fast) var(--lv-ease)",
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.color = "var(--lv-ink)";
                  e.currentTarget.style.background = "rgba(255, 255, 255, 0.06)";
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.color = "var(--lv-ink-3)";
                  e.currentTarget.style.background = "transparent";
                }}
              >
                {isDocked ? (
                  <svg
                    width="16"
                    height="16"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    aria-hidden
                  >
                    <path
                      d="M6 18L18 6M6 6l12 12"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                ) : (
                  t("close")
                )}
              </button>
            </div>

            <div
              className="flex-1 overflow-y-auto"
              style={{
                display: "flex",
                flexDirection: "column",
                gap: "calc(var(--lv-s-4) + var(--lv-s-1))",
                padding: "var(--lv-s-4)",
              }}
            >
              <CaseBoardBody
                caseBoard={caseBoard}
                gameState={gameState}
                scriptType={scriptType}
                progressPhase={progressPhase}
              />
            </div>
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  );
}

function CaseBoardBody({
  caseBoard,
  gameState,
  scriptType,
  progressPhase,
}: {
  caseBoard: CaseBoard | undefined;
  gameState: GameState | null;
  scriptType: string | null;
  progressPhase: string;
}) {
  const clues = gameState?.discovered_clues ?? [];

  if (scriptType === "mystery") {
    return (
      <>
        <MissionBriefing caseBoard={caseBoard} progressPhase={progressPhase} />
        <SuspectProfiles caseBoard={caseBoard} />
        <CluesList clues={clues} />
        <NpcDynamicList
          npcDynamic={caseBoard?.npc_dynamic}
          excludeNames={Array.isArray(caseBoard?.suspects) ? caseBoard.suspects.map((s) => s.name) : []}
        />
        <FieldIntel gameState={gameState} />
      </>
    );
  }

  if (scriptType === "emotional") {
    return (
      <>
        <MissionBriefing caseBoard={caseBoard} progressPhase={progressPhase} />
        <NpcDynamicList npcDynamic={caseBoard?.npc_dynamic} />
        <EmotionalJourney caseBoard={caseBoard} />
        <FieldIntel gameState={gameState} />
      </>
    );
  }

  return (
    <>
      <MissionBriefing caseBoard={caseBoard} progressPhase={progressPhase} />
      <NpcDynamicList npcDynamic={caseBoard?.npc_dynamic} />
      <FieldIntel gameState={gameState} />
    </>
  );
}
