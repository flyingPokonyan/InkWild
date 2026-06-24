"use client";

import { create } from "zustand";

import { gameHistoryQueryKeys } from "@/lib/api/history";
import {
  applyProcessingEvent,
  completePlayStream,
  createIdlePlayStreamState,
  failPlayStream,
  isActivePlayStreamPhase,
  receiveNarrativeToken,
  startPlayStream,
  type PlayStreamStateSnapshot,
} from "@/lib/play-stream-state";
import { getQueryClient } from "@/lib/query-client";
import { CREDIT_BALANCE_QUERY_KEY, CREDIT_TXNS_QUERY_KEY } from "@/lib/credits";
import { streamAction } from "@/lib/sse";
import { buildHydratedSessionState } from "@/lib/session-detail";
import { createStartGameGate } from "@/lib/start-game-gate";
import type {
  ChatMessage,
  EndingResult,
  GameSessionDetail,
  GameState,
  PlayStreamPhase,
  ProcessingEventPayload,
} from "@/lib/types";

interface GameStore {
  sessionId: string | null;
  messages: ChatMessage[];
  gameState: GameState | null;
  quickActions: string[];
  retryCount: number;
  streamPhase: PlayStreamPhase;
  processingHint: ProcessingEventPayload | null;
  isStreaming: boolean;
  ending: EndingResult | null;
  error: string | null;
  characterName: string | null;
  characterDesc: string | null;
  characterAbilities: string[];
  worldName: string | null;
  scriptName: string | null;
  mode: string | null;
  scriptType: string | null;
  startGame: (
    worldId: string,
    characterId: string,
    mode: string,
    characterName?: string,
    characterDesc?: string,
    characterAbilities?: string[],
    worldName?: string,
    scriptId?: string,
    scriptName?: string,
    authorsNote?: string,
    forceAbandonSessionId?: string,
    startStageId?: string,
  ) => Promise<string | null>;
  sendAction: (actionText: string) => Promise<void>;
  /** 玩家主动退场：生成"落幕白"软收场（ending_type=withdrawn），经 ending 事件落到结局页。 */
  endGame: () => Promise<void>;
  retryAction: () => Promise<void>;
  resumeGame: (sessionId: string) => Promise<void>;
  hydrateSessionDetail: (detail: GameSessionDetail) => void;
  reset: () => void;
}

// 与后端 services/game_service.py:WITHDRAW_COMMANDS 对齐的保留哨兵串。
// 玩家不直接打它；前端检测到退场意图并确认后用它调 action 接口。
const WITHDRAW_COMMAND = "__inkwild_withdraw__";

let messageCounter = 0;

function timestamp(): number {
  return Date.now();
}

function appendNarratorMessage(messages: ChatMessage[], id: string, content: string): ChatMessage[] {
  const existing = messages.find((message) => message.id === id);

  if (existing) {
    return messages.map((message) => (message.id === id ? { ...message, content } : message));
  }

  return [
    ...messages,
    {
      id,
      role: "narrator",
      content,
      timestamp: timestamp(),
    },
  ];
}

function getErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "请求失败";
}

// 触发 /history 列表重新拉取。startGame（新增 session）+ ending（status→ended）走这条；
// 不主动失效会被全局 staleTime 5 分钟卡住，刚开的局不出现在 history。
function invalidateGameHistory() {
  if (typeof window === "undefined") return;
  getQueryClient().invalidateQueries({ queryKey: gameHistoryQueryKeys.all });
}

// 余额 + 流水随每回合结算变化。done 是可靠的结算点 —— 一并失效：余额 chip 立即重拉、
// 不停在扣分前的旧值；play「本局积分」抽屉的流水列表也实时刷新（不用刷页面）。
function invalidateCredits() {
  if (typeof window === "undefined") return;
  const qc = getQueryClient();
  qc.invalidateQueries({ queryKey: CREDIT_BALANCE_QUERY_KEY });
  // 前缀失效：覆盖 all + session 各 scope 的流水缓存。
  qc.invalidateQueries({ queryKey: CREDIT_TXNS_QUERY_KEY });
}

function readPlayStreamState(
  state: Pick<GameStore, "streamPhase" | "processingHint">,
): PlayStreamStateSnapshot {
  return {
    phase: state.streamPhase,
    processing: state.processingHint,
  };
}

function toStreamPatch(state: PlayStreamStateSnapshot) {
  return {
    streamPhase: state.phase,
    processingHint: state.processing,
    isStreaming: isActivePlayStreamPhase(state.phase),
  };
}

const idleStreamState = createIdlePlayStreamState();

export const useGameStore = create<GameStore>((set, get) => ({
  sessionId: null,
  messages: [],
  gameState: null,
  quickActions: [],
  retryCount: 0,
  streamPhase: idleStreamState.phase,
  processingHint: idleStreamState.processing,
  isStreaming: false,
  ending: null,
  error: null,
  characterName: null,
  characterDesc: null,
  characterAbilities: [],
  worldName: null,
  scriptName: null,
  mode: null,
  scriptType: null,

  startGame: async (
    worldId,
    characterId,
    mode,
    characterName,
    characterDesc,
    characterAbilities,
    worldName,
    scriptId,
    scriptName,
    authorsNote,
    forceAbandonSessionId,
    startStageId,
  ) => {
    let openingNarrative = "";
    const startGate = createStartGameGate();

    set({
      sessionId: null,
      messages: [],
      gameState: null,
      quickActions: [],
      retryCount: 0,
      ...toStreamPatch(startPlayStream()),
      ending: null,
      error: null,
      characterName: characterName || null,
      characterDesc: characterDesc || null,
      characterAbilities: characterAbilities || [],
      worldName: worldName || null,
      scriptName: scriptName || null,
      mode: mode || null,
    });

    // Fire and forget — don't await. Resolve as soon as session_id arrives.
    void streamAction(
      "/api/game/start",
      {
        world_id: worldId,
        character_id: characterId,
        mode,
        script_id: scriptId || undefined,
        authors_note: authorsNote || undefined,
        force_abandon_session_id: forceAbandonSessionId || undefined,
        start_stage_id: startStageId || undefined,
      },
      {
        onSessionCreated: (data) => {
          set({ sessionId: data.session_id });
          invalidateGameHistory();
          startGate.markSessionCreated(data.session_id);
          // 方案 A2：session 一创建即放行导航，让 play 页在开场旁白「开始流」之前就挂载，
          // 玩家就能在 play 页上看着正文逐字冒出来 —— 而不是在 setup 读条阶段把流耗光、
          // 落地 play 只剩一段写好的成品。里程碑（体察态度 / 谁进场 / 落笔）随 streaming
          // 继续推进，由 play 页的 GameLoadingScreen 无缝接力。开场流在出正文前失败的兜底
          // 由 play 页 openingFailed 分支处理（session_created 之前失败仍 resolve(null) 留在 setup）。
          startGate.markReady();
        },
        onProcessing: (data) => {
          set((state) =>
            toStreamPatch(
              applyProcessingEvent(
                readPlayStreamState(state),
                data,
                state.gameState?.current_location,
              ),
            ),
          );
        },
        onNarrative: (text) => {
          openingNarrative += text;
          set((state) => ({
            messages: appendNarratorMessage(state.messages, "narrator-opening", openingNarrative),
            ...toStreamPatch(receiveNarrativeToken(readPlayStreamState(state))),
          }));
          // 导航已在 session_created 放行；这里只负责把开场旁白逐字灌进 store，
          // play 页据此在台上逐字呈现。
        },
        onStateUpdate: (data) => {
          // 早期 state_update 只落 gameState/quickActions；导航已在 session_created 放行。
          set({
            gameState: data.game_state as GameState,
            quickActions: Array.isArray(data.quick_actions) ? (data.quick_actions as string[]) : [],
          });
        },
        onCaseBoardUpdate: (data) => {
          // Phase-4 follow-up：case_board 在 done 之后晚一拍刷新（仅更 gameState）。
          if (data.game_state) {
            set({ gameState: data.game_state as GameState });
          }
        },
        onEnding: (data) => {
          set({ ending: data });
          invalidateGameHistory();
          // 开局即结局（极少）也算就绪，放行导航让 play 页展示 ending。
          startGate.markReady();
        },
        onError: (data) => {
          set(() => ({
            error: data.message,
            ...toStreamPatch(failPlayStream()),
          }));
          startGate.markError();
        },
        onDone: () => {
          set((state) => toStreamPatch(completePlayStream(readPlayStreamState(state))));
          invalidateCredits();
          startGate.markDone();
        },
      },
    ).catch((error) => {
      set(() => ({
        error: getErrorMessage(error),
        ...toStreamPatch(failPlayStream()),
      }));
      startGate.markError();
    });

    return startGate.promise;
  },

  sendAction: async (actionText) => {
    const { sessionId, isStreaming } = get();
    if (!sessionId || isStreaming) {
      return;
    }

    const playerMessageId = `player-${++messageCounter}`;
    const narratorMessageId = `narrator-${++messageCounter}`;
    let narrative = "";

    set((state) => ({
      error: null,
      ...toStreamPatch(startPlayStream()),
      retryCount: 0,
      messages: [
        ...state.messages,
        {
          id: playerMessageId,
          role: "user",
          content: actionText,
          timestamp: timestamp(),
        },
      ],
    }));

    try {
      await streamAction(`/api/game/${sessionId}/action`, { action_text: actionText }, {
        onProcessing: (data) => {
          set((state) =>
            toStreamPatch(
              applyProcessingEvent(
                readPlayStreamState(state),
                data,
                state.gameState?.current_location,
              ),
            ),
          );
        },
        onNarrative: (text) => {
          narrative += text;
          set((state) => ({
            messages: appendNarratorMessage(state.messages, narratorMessageId, narrative),
            ...toStreamPatch(receiveNarrativeToken(readPlayStreamState(state))),
          }));
        },
        onStateUpdate: (data) => {
          set({
            gameState: data.game_state as GameState,
            quickActions: Array.isArray(data.quick_actions) ? (data.quick_actions as string[]) : [],
          });
        },
        onCaseBoardUpdate: (data) => {
          // Phase-4 follow-up：case_board 在 done 之后晚一拍刷新。只更 gameState，
          // 不动 streamPhase / quickActions（玩家已在 done 解锁）。
          if (data.game_state) {
            set({ gameState: data.game_state as GameState });
          }
        },
        onEnding: (data) => {
          set({ ending: data });
          invalidateGameHistory();
        },
        onError: (data) =>
          set(() => ({
            error: data.message,
            ...toStreamPatch(failPlayStream()),
          })),
        onDone: () => {
          set((state) => toStreamPatch(completePlayStream(readPlayStreamState(state))));
          invalidateCredits();
        },
      });
    } catch (error) {
      set(() => ({
        error: getErrorMessage(error),
        ...toStreamPatch(failPlayStream()),
      }));
    }
  },

  endGame: async () => {
    const { sessionId, isStreaming } = get();
    if (!sessionId || isStreaming) {
      return;
    }

    // 不写玩家气泡（哨兵串不可见）。立刻置一个临时 ending（summary 暂空）让结局页
    // 幕布即时亮起、用固定 pre 描述顶住 LLM 落幕白的生成空窗；真 ending 事件到达后
    // 带 summary 覆盖，幕布再进入叙事。
    set(() => ({
      error: null,
      ending: { ending_type: "withdrawn", title: "搁笔" },
      ...toStreamPatch(startPlayStream()),
    }));

    let endingReceived = false;
    try {
      await streamAction(`/api/game/${sessionId}/action`, { action_text: WITHDRAW_COMMAND }, {
        onEnding: (data) => {
          endingReceived = true;
          set({ ending: data });
          invalidateGameHistory();
        },
        // 落幕失败（如积分门拦截/网络断）：清掉临时 ending，别把玩家卡在永不前进的幕布上，
        // 退回游戏并提示，可重试或选「离开并保存」。
        onError: (data) =>
          set(() => ({
            ending: null,
            error: data.message,
            ...toStreamPatch(failPlayStream()),
          })),
        onDone: () => {
          set((state) => ({
            ...(endingReceived ? {} : { ending: null }),
            ...toStreamPatch(completePlayStream(readPlayStreamState(state))),
          }));
          invalidateCredits();
        },
      });
    } catch (error) {
      set(() => ({
        ending: null,
        error: getErrorMessage(error),
        ...toStreamPatch(failPlayStream()),
      }));
    }
  },

  retryAction: async () => {
    const { sessionId, isStreaming, retryCount, messages } = get();
    if (!sessionId || isStreaming || retryCount >= 3) {
      return;
    }

    const narratorMessageId = `narrator-retry-${++messageCounter}`;
    let narrative = "";
    const nextMessages = [...messages];
    if (nextMessages[nextMessages.length - 1]?.role === "narrator") {
      nextMessages.pop();
    }

    set({
      messages: nextMessages,
      ...toStreamPatch(startPlayStream()),
      error: null,
      retryCount: retryCount + 1,
    });

    try {
      await streamAction(`/api/game/${sessionId}/retry`, {}, {
        onProcessing: (data) => {
          set((state) =>
            toStreamPatch(
              applyProcessingEvent(
                readPlayStreamState(state),
                data,
                state.gameState?.current_location,
              ),
            ),
          );
        },
        onNarrative: (text) => {
          narrative += text;
          set((state) => ({
            messages: appendNarratorMessage(state.messages, narratorMessageId, narrative),
            ...toStreamPatch(receiveNarrativeToken(readPlayStreamState(state))),
          }));
        },
        onStateUpdate: (data) => {
          set({
            gameState: data.game_state as GameState,
            quickActions: Array.isArray(data.quick_actions) ? (data.quick_actions as string[]) : [],
          });
        },
        onCaseBoardUpdate: (data) => {
          // Phase-4 follow-up：case_board 在 done 之后晚一拍刷新。只更 gameState，
          // 不动 streamPhase / quickActions（玩家已在 done 解锁）。
          if (data.game_state) {
            set({ gameState: data.game_state as GameState });
          }
        },
        onEnding: (data) => {
          set({ ending: data });
          invalidateGameHistory();
        },
        onError: (data) =>
          set(() => ({
            error: data.message,
            ...toStreamPatch(failPlayStream()),
          })),
        onDone: () => {
          set((state) => toStreamPatch(completePlayStream(readPlayStreamState(state))));
          invalidateCredits();
        },
      });
    } catch (error) {
      set(() => ({
        error: getErrorMessage(error),
        ...toStreamPatch(failPlayStream()),
      }));
    }
  },

  resumeGame: async (sessionId) => {
    let recap = "";

    set((state) => ({
      sessionId,
      messages: state.messages,
      quickActions: [],
      ...toStreamPatch(startPlayStream()),
      ending: null,
      error: null,
    }));

    try {
      await streamAction(`/api/game/${sessionId}/resume`, {}, {
        onProcessing: (data) => {
          set((state) =>
            toStreamPatch(
              applyProcessingEvent(
                readPlayStreamState(state),
                data,
                state.gameState?.current_location,
              ),
            ),
          );
        },
        onNarrative: (text) => {
          recap += text;
          set((state) => ({
            messages: appendNarratorMessage(state.messages, "narrator-recap", recap),
            ...toStreamPatch(receiveNarrativeToken(readPlayStreamState(state))),
          }));
        },
        onStateUpdate: (data) => {
          set({
            gameState: data.game_state as GameState,
            quickActions: Array.isArray(data.quick_actions) ? (data.quick_actions as string[]) : [],
          });
        },
        onCaseBoardUpdate: (data) => {
          // Phase-4 follow-up：case_board 在 done 之后晚一拍刷新。只更 gameState，
          // 不动 streamPhase / quickActions（玩家已在 done 解锁）。
          if (data.game_state) {
            set({ gameState: data.game_state as GameState });
          }
        },
        onEnding: (data) => {
          set({ ending: data });
          invalidateGameHistory();
        },
        onError: (data) =>
          set(() => ({
            error: data.message,
            ...toStreamPatch(failPlayStream()),
          })),
        onDone: () => {
          set((state) => toStreamPatch(completePlayStream(readPlayStreamState(state))));
          invalidateCredits();
        },
      });
    } catch (error) {
      set(() => ({
        error: getErrorMessage(error),
        ...toStreamPatch(failPlayStream()),
      }));
    }
  },

  hydrateSessionDetail: (detail) =>
    set({
      ...buildHydratedSessionState(detail),
      retryCount: 0,
      ...toStreamPatch(createIdlePlayStreamState()),
    }),

  reset: () => {
    messageCounter = 0;
    set({
      sessionId: null,
      messages: [],
      gameState: null,
      quickActions: [],
      retryCount: 0,
      ...toStreamPatch(createIdlePlayStreamState()),
      ending: null,
      error: null,
      characterName: null,
      characterDesc: null,
      characterAbilities: [],
      worldName: null,
      scriptName: null,
      mode: null,
      scriptType: null,
    });
  },
}));
