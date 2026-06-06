"use client";

import { useGameStore } from "@/stores/game";

export function QuickActions() {
  const quickActions = useGameStore((state) => state.quickActions);
  const sendAction = useGameStore((state) => state.sendAction);
  const isStreaming = useGameStore((state) => state.isStreaming);

  if (quickActions.length === 0) return null;

  return (
    <div className="play-quick-actions" aria-label="快捷动作">
      {quickActions.map((action, index) => (
        <button
          key={`${action}-${index}`}
          type="button"
          onClick={() => {
            void sendAction(action);
          }}
          disabled={isStreaming}
          className="play-quick-chip"
        >
          {action}
        </button>
      ))}
    </div>
  );
}
