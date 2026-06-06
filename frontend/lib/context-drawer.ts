import type { GameState } from "./types";

export interface ContextClueItem {
  content: string;
  foundAt: string;
}

export interface ContextNpcItem {
  name: string;
  attitude: string;
}

export interface ContextSections {
  clues: ContextClueItem[];
  npcs: ContextNpcItem[];
  inventory: string[];
}

function trustToAttitude(trust: number): string {
  if (trust <= 2) return "警惕";
  if (trust <= 4) return "戒备";
  if (trust <= 6) return "中立";
  if (trust <= 8) return "友善";
  return "信任";
}

export function buildContextSections(gameState: GameState): ContextSections {
  return {
    clues: gameState.discovered_clues.map((clue) => ({
      content: clue.content,
      foundAt: clue.found_at,
    })),
    npcs: Object.entries(gameState.npc_relations).map(([name, rel]) => ({
      name,
      attitude: trustToAttitude(rel.trust),
    })),
    inventory: gameState.player_inventory,
  };
}
