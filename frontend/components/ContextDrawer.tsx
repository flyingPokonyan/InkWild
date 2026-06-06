"use client";

import { buildContextSections } from "@/lib/context-drawer";
import type { DrawerMode } from "@/lib/play-layout";
import { useGameStore } from "@/stores/game";

interface ContextDrawerProps {
  open: boolean;
  mode: DrawerMode;
  onToggle: () => void;
}

/** Group clues by their foundAt time, preserving order. */
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

export function ContextDrawer({ open, mode, onToggle }: ContextDrawerProps) {
  const gameState = useGameStore((state) => state.gameState);

  if (!gameState || !open) return null;

  const { clues, npcs, inventory } = buildContextSections(gameState);
  const clueGroups = groupCluesByTime(clues);

  return (
    <>
      <button type="button" aria-label="关闭案情板" onClick={onToggle} className="play-drawer-backdrop" />
      <aside className={`play-drawer ${mode === "modal" ? "play-drawer-modal" : "play-drawer-floating"}`}>
        <div className="play-drawer-header">
          <div className="play-drawer-label">案情摘要</div>
          <button type="button" onClick={onToggle} className="play-header-button">关闭</button>
        </div>

        <div className="play-drawer-body">
          {/* Timeline */}
          <div className="play-drawer-section">
            <h2 className="play-drawer-section-title">线索 · {clues.length}</h2>
            {clueGroups.length === 0 ? (
              <p className="ctx-empty">暂无</p>
            ) : (
              <div className="ctx-timeline">
                {clueGroups.map((group) => (
                  <div key={group.time} className="ctx-timeline-group">
                    <div className="ctx-timeline-dot" />
                    <div className="ctx-timeline-time">{group.time}</div>
                    <div className="ctx-timeline-items">
                      {group.items.map((item) => (
                        <div key={item} className="ctx-timeline-item">{item}</div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* NPCs */}
          <div className="play-drawer-section">
            <h2 className="play-drawer-section-title">人物</h2>
            {npcs.length === 0 ? (
              <p className="ctx-empty">暂无</p>
            ) : (
              <div className="ctx-npc-list">
                {npcs.map((npc) => (
                  <span key={npc.name} className="ctx-npc">
                    {npc.name}<span className="ctx-npc-att">{npc.attitude}</span>
                  </span>
                ))}
              </div>
            )}
          </div>

          {/* Inventory */}
          {inventory.length > 0 && (
            <div className="play-drawer-section">
              <h2 className="play-drawer-section-title">物品</h2>
              <div className="ctx-tag-list">
                {inventory.map((item) => (
                  <span key={item} className="ctx-tag">{item}</span>
                ))}
              </div>
            </div>
          )}
        </div>
      </aside>
    </>
  );
}
