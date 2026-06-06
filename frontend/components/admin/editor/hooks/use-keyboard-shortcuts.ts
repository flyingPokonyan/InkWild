"use client";

import { useEffect } from "react";

interface ShortcutMap {
  /** ⌘/Ctrl + S — 手动保存 */
  onSave?: () => void;
  /** ⌘/Ctrl + Enter — 发布 */
  onPublish?: () => void;
}

/**
 * 编辑器全局快捷键。注意：当焦点在 input/textarea 时，⌘S 仍生效（拦截浏览器保存）；
 * Cmd+Enter 在 textarea 中允许通过（避免阻塞换行就是用户主动发布）。
 */
export function useKeyboardShortcuts({ onSave, onPublish }: ShortcutMap) {
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const mod = e.metaKey || e.ctrlKey;
      if (!mod) return;

      if (e.key === "s" || e.key === "S") {
        e.preventDefault();
        onSave?.();
        return;
      }
      if (e.key === "Enter") {
        e.preventDefault();
        onPublish?.();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onSave, onPublish]);
}
