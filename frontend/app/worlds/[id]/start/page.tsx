"use client";

import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { useTranslations } from "next-intl";

import {
  AuthorsNotePrompt,
  CardDetailStrip,
  type DetailEntry,
  ChoiceScene,
  ListChoiceOption,
  MediaChoiceCard,
} from "@/components/choice";
import { GameLoadingScreen } from "@/components/GameLoadingScreen";
import { LoadingPulse } from "@/components/ui/LoadingPulse";
import { Modal } from "@/components/ui/Modal";
import { useGameHistory } from "@/lib/api/history";
import { useWorldDetail } from "@/lib/api/worlds";
import { buildLoginHref } from "@/lib/auth-redirect";
import { difficultyLevel } from "@/lib/difficulty";
import { LV_EASE, lvStaggerContainer } from "@/lib/motion";
import { withReturn } from "@/lib/play-return";
import type { GameHistoryItem } from "@/lib/types";
import {
  buildScriptCards,
  getInitialWorldSelection,
  resolvePlayableCharacters,
  resolveStartScriptId,
  type WorldMode,
} from "@/lib/world-entry";
import { useAuthStore } from "@/stores/auth";
import { useGameStore } from "@/stores/game";

type StepId = "mode" | "script" | "character" | "confirm";

function getSteps(hasScriptMode: boolean, selectedMode: WorldMode | null): StepId[] {
  if (!selectedMode) return ["mode"];
  if (selectedMode === "script" && hasScriptMode) return ["mode", "script", "character", "confirm"];
  return ["mode", "character", "confirm"];
}

type SelectionState = {
  stepIndex: number;
  mode: WorldMode | null;
  script: string | null;
  character: string | null;
};

type SelectionAction =
  | { type: "init"; mode: WorldMode | null; script: string | null; character: string | null }
  | { type: "presetScript"; script: string; character: string | null }
  | { type: "selectMode"; mode: WorldMode }
  | { type: "selectScript"; script: string }
  | { type: "selectCharacter"; character: string }
  | { type: "advance" }
  | { type: "back" };

function selectionReducer(state: SelectionState, action: SelectionAction): SelectionState {
  switch (action.type) {
    case "init":
      return {
        stepIndex: 0,
        mode: action.mode,
        script: action.script,
        character: action.character,
      };
    case "presetScript":
      // 从剧本详情页深链进来：剧本已定，直接落到「选角色」步（mode→script→character = index 2）
      return {
        stepIndex: 2,
        mode: "script",
        script: action.script,
        character: action.character,
      };
    case "selectMode":
      return { ...state, mode: action.mode, stepIndex: 1 };
    case "selectScript":
      return { ...state, script: action.script, stepIndex: state.stepIndex + 1 };
    case "selectCharacter":
      return { ...state, character: action.character, stepIndex: state.stepIndex + 1 };
    case "advance":
      return { ...state, stepIndex: state.stepIndex + 1 };
    case "back":
      return { ...state, stepIndex: Math.max(0, state.stepIndex - 1) };
    default:
      return state;
  }
}

export default function PlaySetupPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const searchParams = useSearchParams();
  const returnTo = searchParams.get("return");
  // 剧本详情页深链：?mode=script&script=<id>，预选剧本并跳过模式/剧本两步
  const presetMode = searchParams.get("mode");
  const presetScriptId = searchParams.get("script");
  const startGame = useGameStore((state) => state.startGame);
  const resumeGame = useGameStore((state) => state.resumeGame);
  // 方案 A：入场 loading 全程在本页展示，处理提示文案随流式推进。
  const processingHint = useGameStore((state) => state.processingHint);

  const t = useTranslations("worlds");
  const ts = useTranslations("worlds.step");

  const { data: world, isLoading } = useWorldDetail(id);
  // 查重数据源：用户所有 sessions，再筛 active + 同 world。
  // 缓存命中时无网络；start 页 mount 时若过期会刷一次。
  const { data: historyList = [] } = useGameHistory();
  const activeSameWorld = useMemo(
    () =>
      historyList.filter(
        (g) =>
          g.world_id === id &&
          (g.status === "playing" || g.status === "paused"),
      ),
    [historyList, id],
  );

  // 「放弃旧的开新」时把旧 session id 暂存这里，handleStart 提交时一并传后端，
  // 让 /start 在同一请求内原子地 abandon 旧的 + 开新的。
  const [forceAbandonSessionId, setForceAbandonSessionId] = useState<string | null>(null);
  const [duplicatePrompt, setDuplicatePrompt] = useState<{
    session: GameHistoryItem;
    pending: { type: "script" | "character"; id: string };
  } | null>(null);

  const [selection, dispatch] = useReducer(selectionReducer, {
    stepIndex: 0,
    mode: null,
    script: null,
    character: null,
  });
  const [authorsNote, setAuthorsNote] = useState("");
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);
  const [focusedScriptId, setFocusedScriptId] = useState<string | null>(null);
  const [focusedCharacterId, setFocusedCharacterId] = useState<string | null>(null);
  const observerRef = useRef<IntersectionObserver | null>(null);

  useEffect(() => {
    if (world && selection.mode === null && selection.character === null) {
      const presetScript =
        presetMode === "script" && world.has_script_mode && presetScriptId
          ? world.scripts.find((s) => s.id === presetScriptId) ?? null
          : null;
      if (presetScript) {
        const candidates = resolvePlayableCharacters(world, presetScript);
        dispatch({
          type: "presetScript",
          script: presetScript.id,
          character: candidates[0]?.id ?? null,
        });
        return;
      }
      const initial = getInitialWorldSelection(world);
      dispatch({
        type: "init",
        mode: null,
        script: initial.scriptId,
        character: initial.characterId,
      });
    }
  }, [world, selection.mode, selection.character, presetMode, presetScriptId]);

  const steps = useMemo(
    () => (world ? getSteps(world.has_script_mode, selection.mode) : (["mode"] as StepId[])),
    [world, selection.mode],
  );
  const totalSteps = steps.length;
  const safeStepIndex = Math.min(selection.stepIndex, totalSteps - 1);
  const currentStepId = steps[safeStepIndex] || "mode";

  // 切步时清空 focused（避免上一步残留），让新步骤按 hover/IO 重新决定。
  // 用「渲染期按变化重置」模式而非 useEffect —— 避免 setState-in-effect 的级联渲染，
  // 且在新步骤首帧前就清掉旧 focus（无残留闪烁）。
  const [prevStepId, setPrevStepId] = useState(currentStepId);
  if (prevStepId !== currentStepId) {
    setPrevStepId(currentStepId);
    setFocusedScriptId(null);
    setFocusedCharacterId(null);
  }

  const canSelectScriptMode = Boolean(
    world?.has_script_mode && world?.scripts && world.scripts.length > 0,
  );

  const scriptCards = useMemo(() => (world ? buildScriptCards(world) : []), [world]);

  // 剧本模式下，角色步骤只展示当前所选剧本允许的可玩角色（空名单 = 全量）。
  const playableCharacters = useMemo(() => {
    if (!world) return [];
    const selectedScript =
      selection.mode === "script"
        ? world.scripts.find((s) => s.id === selection.script) ?? null
        : null;
    return resolvePlayableCharacters(world, selectedScript);
  }, [world, selection.mode, selection.script]);

  const attachCarousel = useCallback(
    (node: HTMLDivElement | null) => {
      observerRef.current?.disconnect();
      observerRef.current = null;
      if (!node) return;
      if (currentStepId !== "script" && currentStepId !== "character") return;
      // PC（hover 可用）只用 hover 驱动 strip，避免 IO 在初始 observe 时自动选中中间卡。
      // 触屏设备走 IO，根据 scroll-snap 中心卡设置 focus。
      if (typeof window !== "undefined" && window.matchMedia("(hover: hover)").matches) {
        return;
      }

      const observer = new IntersectionObserver(
        (entries) => {
          let bestId: string | null = null;
          let bestRatio = 0;
          entries.forEach((e) => {
            if (e.isIntersecting && e.intersectionRatio > bestRatio) {
              bestRatio = e.intersectionRatio;
              bestId = e.target.getAttribute("data-card-id");
            }
          });
          if (bestId) {
            if (currentStepId === "script") setFocusedScriptId(bestId);
            else setFocusedCharacterId(bestId);
          }
        },
        {
          root: node,
          rootMargin: "0px -40% 0px -40%",
          threshold: [0.5, 0.75, 1],
        },
      );

      node.querySelectorAll("[data-card-id]").forEach((card) => observer.observe(card));
      observerRef.current = observer;
    },
    [currentStepId, scriptCards, world?.characters],
  );

  const handleSelectMode = (mode: WorldMode) => {
    dispatch({ type: "selectMode", mode });
  };

  // 查重：剧本模式按 (world, script) 比对；自由模式按 (world, character, free)。
  // 用户已明确「选了该剧本则提示」「无剧本世界 + 重复 character 则提示」，
  // 所以两个 select 入口分别拦一下；命中就弹 modal、暂停步进。
  const handleSelectScript = (sid: string) => {
    const dup = activeSameWorld.find(
      (g) => g.script_id === sid && g.session_id !== forceAbandonSessionId,
    );
    if (dup) {
      setDuplicatePrompt({ session: dup, pending: { type: "script", id: sid } });
      return;
    }
    dispatch({ type: "selectScript", script: sid });
  };

  const handleSelectCharacter = (cid: string) => {
    if (selection.mode === "free") {
      const dup = activeSameWorld.find(
        (g) =>
          g.mode === "free" &&
          g.character_id === cid &&
          g.session_id !== forceAbandonSessionId,
      );
      if (dup) {
        setDuplicatePrompt({ session: dup, pending: { type: "character", id: cid } });
        return;
      }
    }
    dispatch({ type: "selectCharacter", character: cid });
  };

  const handleContinueOld = useCallback(async () => {
    if (!duplicatePrompt) return;
    const old = duplicatePrompt.session;
    setDuplicatePrompt(null);
    if (old.status === "paused") {
      // resumeGame 内部会跑 SSE 重启流，play 页通过 isStreaming 显示 GameLoadingScreen。
      void resumeGame(old.session_id);
    }
    router.push(withReturn(`/play/${old.session_id}`, returnTo));
  }, [duplicatePrompt, resumeGame, router, returnTo]);

  const handleAbandonOldStartNew = useCallback(() => {
    if (!duplicatePrompt) return;
    setForceAbandonSessionId(duplicatePrompt.session.session_id);
    const pending = duplicatePrompt.pending;
    setDuplicatePrompt(null);
    if (pending.type === "script") {
      dispatch({ type: "selectScript", script: pending.id });
    } else {
      dispatch({ type: "selectCharacter", character: pending.id });
    }
  }, [duplicatePrompt]);

  const goBack = useCallback(() => {
    if (safeStepIndex === 0) {
      router.push(withReturn(`/worlds/${id}`, returnTo));
    } else {
      dispatch({ type: "back" });
    }
  }, [safeStepIndex, router, id, returnTo]);

  const handleStart = useCallback(async () => {
    if (!world || !selection.mode || !selection.character || starting) return;
    setStarting(true);
    setStartError(null);

    const authStore = useAuthStore.getState();
    const signedInUser = authStore.hasLoaded ? authStore.user : await authStore.loadMe();
    if (!signedInUser) {
      setStarting(false);
      const stateError = useAuthStore.getState().error;
      if (stateError) {
        setStartError(stateError);
      } else {
        router.push(buildLoginHref(withReturn(`/worlds/${id}`, returnTo)));
      }
      return;
    }

    const character = world.characters.find((c) => c.id === selection.character);
    const scriptId =
      selection.mode === "script" ? resolveStartScriptId(world, selection.script) : undefined;
    const scriptName = scriptId ? world.scripts.find((s) => s.id === scriptId)?.name : undefined;

    const sessionId = await startGame(
      world.id,
      selection.character,
      selection.mode,
      character?.name,
      character?.description,
      character?.abilities,
      world.name,
      scriptId,
      scriptName,
      authorsNote || undefined,
      forceAbandonSessionId || undefined,
    );

    if (sessionId) {
      router.push(withReturn(`/play/${sessionId}`, returnTo));
      return;
    }

    setStartError(useGameStore.getState().error || ts("startError", { message: "" }));
    setStarting(false);
  }, [world, selection, authorsNote, starting, startGame, router, id, ts, forceAbandonSessionId, returnTo]);

  if (isLoading || !world) {
    return (
      <div
        className="lv-h-dvh"
        style={{
          background: "var(--lv-bg)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        <LoadingPulse variant="block" />
      </div>
    );
  }

  if (starting) {
    const characterName = world.characters.find((c) => c.id === selection.character)?.name ?? null;
    const scriptName =
      selection.mode === "script" && selection.script
        ? world.scripts.find((s) => s.id === selection.script)?.name ?? null
        : null;
    return (
      <GameLoadingScreen
        worldName={world.name}
        characterName={characterName}
        scriptName={scriptName}
        processing={processingHint}
      />
    );
  }

  const stepHeader: Record<StepId, { eyebrow: string; title: string }> = {
    mode: { eyebrow: t("scriptMode") === "剧本模式" ? "模式" : "Mode", title: "" },
    script: { eyebrow: "剧本", title: "" },
    character: { eyebrow: "角色", title: "" },
    confirm: { eyebrow: "", title: "" },
  };

  const header = stepHeader[currentStepId];

  const renderStepContent = () => {
    switch (currentStepId) {
      case "mode":
        return (
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              gap: "var(--lv-s-2)",
              width: "100%",
              maxWidth: 480,
              margin: "0 auto",
            }}
          >
            <ListChoiceOption
              index={1}
              title={t("modeScript")}
              description={ts("modeScriptDesc")}
              badge={{ glyph: t("modeScriptGlyph"), tone: "accent" }}
              disabled={!canSelectScriptMode}
              disabledNote={!canSelectScriptMode ? ts("noScripts") : undefined}
              selected={selection.mode === "script"}
              onSelect={() => canSelectScriptMode && handleSelectMode("script")}
            />
            <ListChoiceOption
              index={2}
              title={t("modeFree")}
              description={ts("modeFreeDesc")}
              badge={{ glyph: t("modeFreeGlyph"), tone: "accent-2" }}
              selected={selection.mode === "free"}
              onSelect={() => handleSelectMode("free")}
            />
          </div>
        );

      case "script": {
        const focusedScript = focusedScriptId
          ? scriptCards.find((s) => s.id === focusedScriptId) ?? null
          : null;
        const scriptEntries: DetailEntry[] = focusedScript
          ? [
              { label: "难度", value: t("difficultyName", { level: difficultyLevel(focusedScript.difficulty) }) },
              { label: "时长", value: focusedScript.estimatedTime },
            ]
          : [];
        return (
          <div style={{ display: "flex", flexDirection: "column", gap: "var(--lv-s-4)" }}>
            <div
              ref={attachCarousel}
              onMouseLeave={() => setFocusedScriptId(null)}
              className="lv-media-grid"
              style={{
                maxWidth: 920,
                margin: "0 auto",
                width: "100%",
              }}
            >
              {scriptCards.map((script) => (
                <MediaChoiceCard
                  key={script.id}
                  cardId={script.id}
                  coverImage={script.coverImage}
                  title={script.name}
                  selected={false}
                  onSelect={() => handleSelectScript(script.id)}
                  onFocus={() => setFocusedScriptId(script.id)}
                />
              ))}
            </div>
            <CardDetailStrip
              cardKey={focusedScript?.id ?? "empty"}
              entries={scriptEntries}
              description={focusedScript?.description}
              descriptionMaxChars={200}
            />
          </div>
        );
      }

      case "character": {
        const focusedCharacter = focusedCharacterId
          ? world.characters.find((c) => c.id === focusedCharacterId) ?? null
          : null;
        const characterEntries: DetailEntry[] = focusedCharacter
          ? [
              ...(focusedCharacter.abilities[0]
                ? [{ label: "身份", value: focusedCharacter.abilities[0] }]
                : []),
              ...(focusedCharacter.abilities.length > 1
                ? [
                    {
                      label: "特长",
                      value: focusedCharacter.abilities.slice(1, 3).join(" · "),
                    },
                  ]
                : []),
              ...(focusedCharacter.starting_location
                ? [{ label: "起点", value: focusedCharacter.starting_location }]
                : []),
            ]
          : [];
        return (
          <div style={{ display: "flex", flexDirection: "column", gap: "var(--lv-s-4)" }}>
            <div
              ref={attachCarousel}
              onMouseLeave={() => setFocusedCharacterId(null)}
              className="lv-media-grid"
              style={{
                maxWidth: 920,
                margin: "0 auto",
                width: "100%",
              }}
            >
              {playableCharacters.map((character) => (
                <MediaChoiceCard
                  key={character.id}
                  cardId={character.id}
                  coverImage={character.avatar}
                  title={character.name}
                  selected={false}
                  onSelect={() => handleSelectCharacter(character.id)}
                  onFocus={() => setFocusedCharacterId(character.id)}
                />
              ))}
            </div>
            <CardDetailStrip
              cardKey={focusedCharacter?.id ?? "empty"}
              entries={characterEntries}
              description={focusedCharacter?.description}
              descriptionMaxChars={180}
            />
          </div>
        );
      }

      case "confirm":
        return (
          <AuthorsNotePrompt
            value={authorsNote}
            onChange={setAuthorsNote}
            placeholder={ts("authorsNotePlaceholder")}
            ariaLabel={ts("authorsNote")}
            ctaLabel={ts("go")}
            error={startError}
            onSubmit={() => {
              void handleStart();
            }}
          />
        );

      default:
        return null;
    }
  };

  return (
    <ChoiceScene
      eyebrow={header.eyebrow}
      title={header.title}
      coverImage={world.cover_image}
      onBack={goBack}
      backLabel={`← ${safeStepIndex === 0 ? ts("backToWorld") : ts("back")}`}
      steps={{ current: safeStepIndex, total: totalSteps }}
    >
      <AnimatePresence mode="wait">
        <motion.div
          key={currentStepId}
          variants={lvStaggerContainer}
          initial="hidden"
          animate="show"
          exit={{ opacity: 0, transition: { duration: 0.15, ease: LV_EASE } }}
          style={{ width: "100%" }}
        >
          {renderStepContent()}
        </motion.div>
      </AnimatePresence>

      <DuplicateSessionModal
        open={!!duplicatePrompt}
        session={duplicatePrompt?.session ?? null}
        worldName={world?.name ?? ""}
        onContinueOld={() => void handleContinueOld()}
        onAbandonOldStartNew={handleAbandonOldStartNew}
        onCancel={() => setDuplicatePrompt(null)}
      />
    </ChoiceScene>
  );
}

interface DuplicateSessionModalProps {
  open: boolean;
  session: GameHistoryItem | null;
  worldName: string;
  onContinueOld: () => void;
  onAbandonOldStartNew: () => void;
  onCancel: () => void;
}

function DuplicateSessionModal({
  open,
  session,
  worldName,
  onContinueOld,
  onAbandonOldStartNew,
  onCancel,
}: DuplicateSessionModalProps) {
  if (!session) return null;
  // 副文按 mode 区分：剧本走「第 N 回合」，自由走「第 N 天 · 当前地点」。
  // 数据来自 /history GameHistoryItem，已包含 rounds_played / current_time / current_location。
  const isScript = session.mode === "script";
  const subtitle = isScript
    ? `进度：第 ${session.rounds_played ?? 0} 回合`
    : [session.current_time, session.current_location].filter(Boolean).join(" · ");

  return (
    <Modal
      open={open}
      onClose={onCancel}
      maxWidth={460}
      title={`已有进行中的「${worldName}」`}
      footer={
        <>
          <button type="button" className="lv-btn-confirm-cancel" onClick={onCancel}>
            取消
          </button>
          <button
            type="button"
            className="lv-btn-confirm-primary"
            onClick={onContinueOld}
            autoFocus
          >
            继续旧的
          </button>
          <button
            type="button"
            className="lv-btn-confirm-primary is-danger"
            onClick={onAbandonOldStartNew}
          >
            放弃旧的，开新局
          </button>
        </>
      }
    >
      <p style={{ margin: 0, color: "var(--lv-ink-2)" }}>
        {session.character_name ? `${session.character_name}` : "你"}的故事还在
        {isScript ? "剧本" : "自由"}模式里继续。
      </p>
      {subtitle && (
        <p style={{ margin: "8px 0 0", color: "var(--lv-ink-3)", fontSize: 13 }}>
          {subtitle}
        </p>
      )}
    </Modal>
  );
}
