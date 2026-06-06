import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import type { ChatMessage, GameState } from "@/lib/types";
import { useGameStore } from "@/stores/game";

import { ChatPanel } from "./ChatPanel";
import { GameHeader } from "./GameHeader";
import { QuickActions } from "./QuickActions";

// GameHeader 现在内含 CreditBalanceChip（用 TanStack Query 拉余额），渲染需要 provider。
function withQuery(ui: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{ui}</QueryClientProvider>;
}

vi.mock("next/link", () => ({
  default: ({
    href,
    children,
    ...props
  }: {
    href: string;
    children: React.ReactNode;
    [key: string]: unknown;
  }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

vi.mock("next-intl", () => ({
  useTranslations: (namespace?: string) => (key: string) => {
    const messages: Record<string, string> = {
      "play.leaveWorld": "离开世界",
      "play.pause": "暂停",
      "play.openCaseBoard": "案件板",
      "play.closePanel": "关闭",
      "play.identityCaps": "身份",
      "play.regenerate": "重新生成",
      "play.retryMaxed": "重试次数上限",
    };
    return messages[namespace ? `${namespace}.${key}` : key] ?? key;
  },
}));

const baseGameState: GameState = {
  current_time: "申时三刻",
  current_location: "茶摊后院",
  player_inventory: ["旧采访簿"],
  discovered_clues: [
    { id: "c1", content: "泥脚印", found_at: "申时三刻" },
    { id: "c2", content: "水烟味", found_at: "申时三刻" },
    { id: "c3", content: "袖口污渍", found_at: "申时三刻" },
  ],
  npc_relations: {},
  triggered_events: [],
  visited_locations: ["茶摊后院"],
  round_number: 7,
};

const messages: ChatMessage[] = [
  {
    id: "n1",
    role: "narrator",
    content:
      "后院的雨棚漏着水，一滴一滴砸在铁盆里。\n你注意到灶台旁边多了一只泥脚印。",
    timestamp: 1,
  },
  {
    id: "u1",
    role: "user",
    content: "我先看那只脚印，再问王福今晚有没有人从后门进过。",
    timestamp: 2,
  },
];

beforeEach(() => {
  vi.stubGlobal("requestAnimationFrame", (cb: FrameRequestCallback) => {
    cb(0);
    return 1;
  });
  vi.stubGlobal("cancelAnimationFrame", vi.fn());
  HTMLElement.prototype.scrollTo = vi.fn();
});

afterEach(() => {
  useGameStore.getState().reset();
  vi.restoreAllMocks();
});

test("game header matches the mobile demo information density", () => {
  useGameStore.setState({ gameState: baseGameState });

  render(withQuery(<GameHeader drawerOpen={false} onToggleDrawer={vi.fn()} onPause={vi.fn()} />));

  expect(screen.getByText("茶摊后院")).toHaveClass("play-header-title");
  expect(screen.getByText("申时三刻 · 第 7 回合")).toHaveClass("play-header-meta");
  expect(screen.getByText("3")).toHaveClass("play-header-clue-badge");
});

test("quick actions render as the demo's horizontal action rail", () => {
  useGameStore.setState({
    quickActions: ["查看四周", "询问王福", "整理线索"],
    isStreaming: false,
  });

  const { container } = render(<QuickActions />);

  const rail = container.querySelector(".play-quick-actions");
  expect(rail).not.toBeNull();
  expect(rail).toHaveTextContent("查看四周");
  expect(rail).toHaveTextContent("询问王福");
  expect(rail).toHaveTextContent("整理线索");
});

test("chat panel exposes the demo identity strip and composer overlap spacer", () => {
  useGameStore.setState({
    gameState: baseGameState,
    messages,
    characterName: "沈清禾",
    characterDesc: "记者 · 善于套话 · 随身带着相机和旧采访簿",
    characterAbilities: [],
    streamPhase: "idle",
    processingHint: null,
  });

  const { container } = render(<ChatPanel />);

  const identity = container.querySelector(".play-identity");
  expect(identity).not.toBeNull();
  expect(identity).toHaveTextContent("沈清禾");
  expect(container.querySelector(".play-composer-spacer")).not.toBeNull();
});
