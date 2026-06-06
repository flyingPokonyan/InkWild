"use client";

import { useEffect, useRef, useState } from "react";

/**
 * 倒计时 hook —— 仅 IPRecognitionCard 等"有默认选项"的场景用。
 * paused 时停止 tick；归零时触发 onTimeout 并自锁，后续不再触发。
 */
export function useChoiceCountdown(opts: {
  totalMs: number;
  paused: boolean;
  onTimeout: () => void;
}): { secondsLeft: number } {
  const { totalMs, paused, onTimeout } = opts;
  const [secondsLeft, setSecondsLeft] = useState(Math.ceil(totalMs / 1000));
  const firedRef = useRef(false);

  useEffect(() => {
    if (paused || firedRef.current) return;
    if (secondsLeft <= 0) {
      firedRef.current = true;
      onTimeout();
      return;
    }
    const t = setTimeout(() => setSecondsLeft((s) => s - 1), 1000);
    return () => clearTimeout(t);
  }, [secondsLeft, paused, onTimeout]);

  return { secondsLeft };
}
