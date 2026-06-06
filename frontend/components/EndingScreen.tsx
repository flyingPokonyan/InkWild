"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";

import { useGameStore } from "@/stores/game";

const TONE: Record<string, string> = {
  perfect: "所有线索在你手里闭合成环，真相终于没有继续沉入雾中。",
  good: "你已经逼近真相，虽然仍有缺口，但故事总算没有白白消散。",
  bad: "线索来得太迟，迷雾趁你犹疑的片刻吞下了代价。",
  timeout: "你仍停留在雾里，世界却已经继续向前，真相随之冷却。",
  test_exit: "这局故事已按测试暗号提前收束，你可以直接开始下一轮验证。",
};

export function EndingScreen() {
  const router = useRouter();
  const ending = useGameStore((state) => state.ending);
  const gameState = useGameStore((state) => state.gameState);
  const messages = useGameStore((state) => state.messages);
  const reset = useGameStore((state) => state.reset);
  const te = useTranslations("play.ending");

  if (!ending) return null;

  const labelKey = (
    {
      perfect: "perfect",
      good: "good",
      bad: "bad",
      timeout: "timeout",
      test_exit: "testExit",
    } as Record<string, "perfect" | "good" | "bad" | "timeout" | "testExit">
  )[ending.ending_type] || "timeout";
  const label = te(labelKey);
  const tone = TONE[ending.ending_type] || TONE.timeout;
  const playerRounds = messages.filter((m) => m.role === "user").length;

  return (
    <div className="lv-theme flex min-h-dvh items-center justify-center" style={{ padding: "var(--lv-s-12) var(--lv-s-4)" }}>
      <div
        className="text-center"
        style={{
          width: "100%",
          maxWidth: "640px",
          borderRadius: "var(--lv-r-card)",
          border: "1px solid var(--lv-line)",
          background: "var(--lv-bg-1)",
          padding: "var(--lv-s-8)",
        }}
      >
        <span
          className="lv-t-caps"
          style={{
            display: "inline-block",
            borderRadius: "var(--lv-r-pill)",
            background: "var(--lv-accent-soft)",
            color: "var(--lv-accent)",
            padding: "var(--lv-s-1) var(--lv-s-3)",
          }}
        >
          {label}
        </span>
        <h1
          className="lv-t-h1"
          style={{
            marginTop: "var(--lv-s-4)",
            color: "var(--lv-ink)",
            fontFamily: "var(--lv-font-serif)",
            fontWeight: 500,
          }}
        >
          {ending.title}
        </h1>
        <p
          className="lv-t-narrative"
          style={{
            margin: "var(--lv-s-4) auto 0",
            maxWidth: "540px",
            color: "var(--lv-ink-2)",
          }}
        >
          {tone}
        </p>

        <div className="grid sm:grid-cols-3" style={{ marginTop: "var(--lv-s-8)", gap: "var(--lv-s-4)" }}>
          <StatCard value={playerRounds} label={te("rounds")} />
          <StatCard value={gameState?.discovered_clues.length || 0} label={te("clues")} />
          <StatCard value={gameState?.triggered_events.length || 0} label={te("events")} />
        </div>

        <div className="flex flex-col items-center justify-center sm:flex-row" style={{ marginTop: "var(--lv-s-8)", gap: "var(--lv-s-3)" }}>
          <button
            type="button"
            onClick={() => {
              reset();
              router.push("/");
            }}
            className="lv-btn lv-btn-primary"
          >
            {te("backHome")}
          </button>
          <button
            type="button"
            onClick={() => router.push("/history")}
            className="lv-btn"
          >
            {te("viewHistory")}
          </button>
        </div>
      </div>
    </div>
  );
}

function StatCard({ value, label }: { value: number; label: string }) {
  return (
    <div
      style={{
        borderRadius: "var(--lv-r-card)",
        border: "1px solid var(--lv-line)",
        background: "var(--lv-bg)",
        padding: "var(--lv-s-4)",
      }}
    >
      <div className="lv-t-h2" style={{ color: "var(--lv-ink)", fontFamily: "var(--lv-font-sans)" }}>
        {value}
      </div>
      <div
        className="lv-t-caps"
        style={{ marginTop: "var(--lv-s-1)", color: "var(--lv-ink-3)" }}
      >
        {label}
      </div>
    </div>
  );
}
