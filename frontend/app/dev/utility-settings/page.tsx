"use client";

/**
 * Desktop-only visual demo: utility surfaces redesign.
 * 去金 chrome + 统一 settings 语言。不接真实 API，不改生产页。
 * 打开：/dev/utility-settings
 */

import { useState, type ReactNode } from "react";
import {
  BadgeCheck,
  Bell,
  Bug,
  Camera,
  Check,
  ChevronRight,
  Coins,
  Gift,
  ImagePlus,
  Lightbulb,
  LogOut,
  Megaphone,
  MessageSquare,
  Pencil,
  UserRound,
} from "lucide-react";

type Panel = "account" | "credits" | "notif" | "feedback";
type Mode = "before" | "after";

const TXNS = [
  { title: "雾隐镇 · 剧本模式", meta: "第 12 回合 · 14:22", delta: "−18", bal: "1,282", note: null as string | null },
  { title: "生成世界", meta: "生成世界 · 11:08", delta: "−120", bal: "1,300", note: "赛博雨夜" },
  { title: "注册赠送", meta: "赠送 · 昨天", delta: "+500", bal: "1,420", note: null },
  { title: "失败未扣费", meta: "第 3 回合 · 昨天", delta: "0", bal: "920", note: "LLM 超时" },
];

const NOTIFS = [
  { unread: true, icon: Gift, title: "注册赠送已到账", sub: "500 积分已入账，可在游玩与创作中使用。", time: "12 分钟前" },
  { unread: true, icon: BadgeCheck, title: "世界「赛博雨夜」已通过审核", sub: "现已出现在发现页。", time: "2 小时前" },
  { unread: false, icon: Coins, title: "积分余额偏低", sub: "当前余额 42，游玩可能受限。", time: "昨天" },
  { unread: false, icon: MessageSquare, title: "反馈有新回复", sub: "关于「案件板在移动端…」", time: "3 天前" },
];

export default function UtilitySettingsDemoPage() {
  const [mode, setMode] = useState<Mode>("after");
  const [panel, setPanel] = useState<Panel>("account");

  return (
    <main className="lv-theme usd-root">
      {/* Mobile gate */}
      <div className="usd-mobile-gate">
        <p className="lv-t-h3">仅桌面预览</p>
        <p className="lv-t-meta" style={{ color: "var(--lv-ink-3)", maxWidth: 280, textAlign: "center" }}>
          本 demo 只覆盖桌面 utility 表面。移动端刻意不动。
        </p>
      </div>

      <div className="usd-desktop">
        <header className="usd-top">
          <div>
            <div className="lv-t-caps usd-kicker">Dev · Utility settings</div>
            <h1 className="usd-title">账户 / 积分 / 通知 / 反馈 · 桌面提案</h1>
            <p className="usd-lead">
              去金 chrome · 中性 active · 未读用 badge 红点 · 无 soft gold 光晕 · 同一套 settings 语言
            </p>
          </div>
          <div className="usd-mode">
            <button
              type="button"
              className={mode === "before" ? "is-on" : ""}
              onClick={() => setMode("before")}
            >
              现状
            </button>
            <button
              type="button"
              className={mode === "after" ? "is-on" : ""}
              onClick={() => setMode("after")}
            >
              提案
            </button>
          </div>
        </header>

        <div className="usd-tabs" role="tablist">
          {(
            [
              ["account", "账户"],
              ["credits", "积分"],
              ["notif", "通知"],
              ["feedback", "反馈"],
            ] as const
          ).map(([key, label]) => (
            <button
              key={key}
              type="button"
              role="tab"
              aria-selected={panel === key}
              className={panel === key ? "is-on" : ""}
              onClick={() => setPanel(key)}
            >
              {label}
            </button>
          ))}
        </div>

        <div className="usd-stage" data-mode={mode}>
          {panel === "account" && (mode === "before" ? <BeforeAccount /> : <AfterAccount />)}
          {panel === "credits" && (mode === "before" ? <BeforeCredits /> : <AfterCredits />)}
          {panel === "notif" && (mode === "before" ? <BeforeNotif /> : <AfterNotif />)}
          {panel === "feedback" && (mode === "before" ? <BeforeFeedback /> : <AfterFeedback />)}
        </div>

        <aside className="usd-notes">
          {mode === "before" ? (
            <ul>
              <li>Active：金竖条 + 金 tint 背景</li>
              <li>未读点 / hover 链接：香槟金</li>
              <li>页面顶光：gold radial soft</li>
              <li>各表面局部 CSS 命名空间，节奏不齐</li>
            </ul>
          ) : (
            <ul>
              <li>Active：中性白系 fill，无金竖条</li>
              <li>未读：<code>--lv-badge</code> 小红点，不绑 accent</li>
              <li>无 soft gold 铺底；余额用 mono 数字层级</li>
              <li>Shared：page title / section card / row / chip / empty</li>
              <li>金色仅保留 focus ring（浏览器默认走 token 时）</li>
            </ul>
          )}
        </aside>
      </div>

      <style jsx global>{USD_CSS}</style>
    </main>
  );
}

/* ───────────────────────── BEFORE ───────────────────────── */

function BeforeAccount() {
  return (
    <div className="bf-shell">
      <aside className="bf-rail">
        <IdBlock goldHint />
        <nav className="bf-nav">
          <NavItemBefore active icon={<UserRound size={16} />} label="账户" />
          <NavItemBefore icon={<Coins size={16} />} label="我的积分" bal="1,282" goldBal />
        </nav>
        <button type="button" className="bf-logout">
          <LogOut size={14} /> 退出登录
        </button>
      </aside>
      <section>
        <h2 className="bf-page-title">账户</h2>
        <div className="bf-card bf-avatar-row">
          <div className="bf-avatar lg">玩</div>
          <div>
            <button type="button" className="bf-pill">
              <Camera size={13} /> 更换头像
            </button>
            <div className="bf-hint">PNG / JPG · ≤ 2MB</div>
          </div>
        </div>
        <div className="bf-card">
          <div className="bf-card-head">资料</div>
          <RowBefore label="昵称" value="雾行者" action={<Pencil size={14} />} />
          <RowBefore label="邮箱" value="player@inkwild.app" muted />
          <RowBefore label="登录方式" value="邮箱密码" muted last />
        </div>
        <div className="bf-card">
          <div className="bf-card-head">安全</div>
          <RowBefore label="修改密码" value="" action={<ChevronRight size={15} />} />
          <RowBefore label="删除账户" value="即将推出" muted last />
        </div>
      </section>
    </div>
  );
}

function BeforeCredits() {
  return (
    <div className="bf-shell">
      <aside className="bf-rail">
        <IdBlock goldHint />
        <nav className="bf-nav">
          <NavItemBefore icon={<UserRound size={16} />} label="账户" />
          <NavItemBefore active icon={<Coins size={16} />} label="我的积分" bal="1,282" goldBal />
        </nav>
        <button type="button" className="bf-logout">
          <LogOut size={14} /> 退出登录
        </button>
      </aside>
      <section>
        <div className="bf-glow" aria-hidden />
        <h2 className="bf-page-title">我的积分</h2>
        <div className="bf-hero-bal">
          <div className="bf-hero-label">可用余额</div>
          <div className="bf-hero-num gold">1,282</div>
          <div className="bf-stats">
            <Stat label="本周消耗" value="312" />
            <Stat label="本周获得" value="500" />
            <Stat label="累计游玩" value="48 局" />
          </div>
        </div>
        <Ledger mock filterGold />
      </section>
    </div>
  );
}

function BeforeNotif() {
  return (
    <div className="bf-panel">
      <div className="bf-panel-head">
        <div>
          <h2>通知</h2>
          <p>2 条未读</p>
        </div>
        <span className="bf-panel-mark gold">
          <Bell size={16} />
        </span>
      </div>
      <div className="bf-tabs">
        <button type="button" className="is-on">
          消息 <span className="bf-count">2</span>
        </button>
        <button type="button">公告</button>
        <button type="button" className="bf-readall gold-hover">
          全部已读
        </button>
      </div>
      <div className="bf-list">
        {NOTIFS.map((n) => (
          <button key={n.title} type="button" className="bf-row">
            {n.unread && <span className="bf-dot gold" />}
            <span className="bf-ico">
              <n.icon size={14} />
            </span>
            <span className="bf-body">
              <span className="bf-t">{n.title}</span>
              <span className="bf-s">{n.sub}</span>
              <span className="bf-time">{n.time}</span>
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}

function BeforeFeedback() {
  return (
    <div className="bf-fb">
      <h2 className="bf-page-title" style={{ marginBottom: 18 }}>
        意见反馈
      </h2>
      <div className="bf-cats">
        <button type="button" className="bf-cat is-on">
          <Bug size={15} /> 问题
        </button>
        <button type="button" className="bf-cat">
          <Lightbulb size={15} /> 建议
        </button>
      </div>
      <label className="bf-label">描述</label>
      <textarea className="bf-ta" rows={4} defaultValue="" placeholder="发生了什么？" />
      <button type="button" className="bf-upload">
        <ImagePlus size={15} /> 截图
      </button>
      <label className="bf-label">联系方式（可选）</label>
      <input className="bf-input" placeholder="邮箱或微信号" />
      <button type="button" className="lv-btn lv-btn-primary lv-btn-lg bf-submit">
        提交
      </button>
    </div>
  );
}

/* ───────────────────────── AFTER ───────────────────────── */

function AfterAccount() {
  return (
    <div className="af-shell">
      <aside className="af-rail">
        <IdBlock />
        <nav className="af-nav">
          <NavItemAfter active icon={<UserRound size={16} />} label="账户" />
          <NavItemAfter icon={<Coins size={16} />} label="我的积分" bal="1,282" />
        </nav>
        <button type="button" className="af-logout">
          <LogOut size={14} /> 退出登录
        </button>
      </aside>
      <section className="af-main">
        <header className="af-page-head">
          <h2>账户</h2>
          <p>身份与安全设置</p>
        </header>

        <div className="af-card af-identity">
          <div className="af-avatar lg">玩</div>
          <div className="af-identity-meta">
            <div className="af-identity-name">雾行者</div>
            <div className="af-identity-sub">player@inkwild.app</div>
            <button type="button" className="af-ghost-btn">
              <Camera size={13} /> 更换头像
            </button>
          </div>
        </div>

        <Section title="资料">
          <RowAfter label="昵称" value="雾行者" action="编辑" />
          <RowAfter label="邮箱" value="player@inkwild.app" muted />
          <RowAfter label="登录方式" value="邮箱密码" muted last />
        </Section>

        <Section title="安全">
          <RowAfter label="修改密码" action="更改" />
          <RowAfter label="删除账户" value="即将推出" muted last />
        </Section>
      </section>
    </div>
  );
}

function AfterCredits() {
  return (
    <div className="af-shell">
      <aside className="af-rail">
        <IdBlock />
        <nav className="af-nav">
          <NavItemAfter icon={<UserRound size={16} />} label="账户" />
          <NavItemAfter active icon={<Coins size={16} />} label="我的积分" bal="1,282" />
        </nav>
        <button type="button" className="af-logout">
          <LogOut size={14} /> 退出登录
        </button>
      </aside>
      <section className="af-main">
        <header className="af-page-head">
          <h2>我的积分</h2>
          <p>余额与流水，冷静账本</p>
        </header>

        <div className="af-wallet">
          <div className="af-wallet-main">
            <div className="af-wallet-label">可用余额</div>
            <div className="af-wallet-num">1,282</div>
          </div>
          <div className="af-wallet-grid">
            <div>
              <span>本周消耗</span>
              <b>312</b>
            </div>
            <div>
              <span>本周获得</span>
              <b>500</b>
            </div>
            <div>
              <span>累计游玩</span>
              <b>48</b>
            </div>
          </div>
        </div>

        <Ledger mock />
      </section>
    </div>
  );
}

function AfterNotif() {
  return (
    <div className="af-panel">
      <div className="af-panel-head">
        <div>
          <h2>通知</h2>
          <p>2 条未读 · 只保留必要动作</p>
        </div>
        <button type="button" className="af-text-btn">
          全部已读
        </button>
      </div>
      <div className="af-seg">
        <button type="button" className="is-on">
          消息 <span className="af-badge">2</span>
        </button>
        <button type="button">公告</button>
      </div>
      <div className="af-list">
        {NOTIFS.map((n) => (
          <button key={n.title} type="button" className="af-row">
            {n.unread && <span className="af-dot" aria-label="未读" />}
            <span className="af-ico">
              <n.icon size={14} />
            </span>
            <span className="af-body">
              <span className={`af-t${n.unread ? " is-unread" : ""}`}>{n.title}</span>
              <span className="af-s">{n.sub}</span>
              <span className="af-time">{n.time}</span>
            </span>
          </button>
        ))}
      </div>
      <div className="af-panel-foot">
        <span className="af-ico sm">
          <Megaphone size={12} />
        </span>
        <span className="lv-t-meta" style={{ color: "var(--lv-ink-4)" }}>
          公告 level 用 ink / warn / danger，不再用 accent
        </span>
      </div>
    </div>
  );
}

function AfterFeedback() {
  const [cat, setCat] = useState<"bug" | "idea">("bug");
  return (
    <div className="af-fb">
      <header className="af-page-head">
        <h2>意见反馈</h2>
        <p>低摩擦一次提交，无装饰色</p>
      </header>
      <div className="af-seg full">
        <button type="button" className={cat === "bug" ? "is-on" : ""} onClick={() => setCat("bug")}>
          <Bug size={14} /> 问题
        </button>
        <button type="button" className={cat === "idea" ? "is-on" : ""} onClick={() => setCat("idea")}>
          <Lightbulb size={14} /> 建议
        </button>
      </div>
      <label className="af-field-label">描述</label>
      <textarea className="af-ta" rows={4} placeholder="发生了什么？尽量包含复现步骤" />
      <button type="button" className="af-ghost-btn" style={{ alignSelf: "flex-start", margin: "12px 0 16px" }}>
        <ImagePlus size={14} /> 添加截图
      </button>
      <label className="af-field-label">联系方式（可选）</label>
      <input className="af-input" placeholder="邮箱或微信号" />
      <button type="button" className="lv-btn lv-btn-primary lv-btn-lg" style={{ width: "100%", justifyContent: "center", marginTop: 20 }}>
        提交
      </button>
      <div className="af-success-preview">
        <span className="af-success-mark">
          <Check size={18} strokeWidth={2.4} />
        </span>
        <div>
          <strong>已收到</strong>
          <p>成功态只用 success 绿，不用金</p>
        </div>
      </div>
    </div>
  );
}

/* ───────────────────────── shared mock bits ───────────────────────── */

function IdBlock({ goldHint }: { goldHint?: boolean }) {
  return (
    <div className={goldHint ? "bf-id" : "af-id"}>
      <div className={goldHint ? "bf-avatar" : "af-avatar"}>玩</div>
      <div>
        <div className={goldHint ? "bf-name" : "af-name"}>雾行者</div>
        <div className={goldHint ? "bf-email" : "af-email"}>player@inkwild.app</div>
      </div>
    </div>
  );
}

function NavItemBefore({
  active,
  icon,
  label,
  bal,
  goldBal,
}: {
  active?: boolean;
  icon: ReactNode;
  label: string;
  bal?: string;
  goldBal?: boolean;
}) {
  return (
    <div className={`bf-nav-item${active ? " is-active" : ""}`}>
      <span className="bf-nav-rule" />
      {icon}
      <span>{label}</span>
      {bal && <span className={`bf-nav-bal${goldBal ? " gold" : ""}`}>{bal}</span>}
    </div>
  );
}

function NavItemAfter({
  active,
  icon,
  label,
  bal,
}: {
  active?: boolean;
  icon: ReactNode;
  label: string;
  bal?: string;
}) {
  return (
    <div className={`af-nav-item${active ? " is-active" : ""}`}>
      {icon}
      <span>{label}</span>
      {bal && <span className="af-nav-bal">{bal}</span>}
    </div>
  );
}

function RowBefore({
  label,
  value,
  muted,
  last,
  action,
}: {
  label: string;
  value: string;
  muted?: boolean;
  last?: boolean;
  action?: ReactNode;
}) {
  return (
    <div className={`bf-row-line${last ? " last" : ""}`}>
      <span className="bf-row-label">{label}</span>
      <span className="bf-row-right">
        {value && <span className={muted ? "muted" : ""}>{value}</span>}
        {action}
      </span>
    </div>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="af-card">
      <div className="af-section-label">{title}</div>
      {children}
    </div>
  );
}

function RowAfter({
  label,
  value,
  muted,
  last,
  action,
}: {
  label: string;
  value?: string;
  muted?: boolean;
  last?: boolean;
  action?: string;
}) {
  return (
    <div className={`af-row-line${last ? " last" : ""}`}>
      <span className="af-row-label">{label}</span>
      <span className="af-row-right">
        {value && <span className={muted ? "muted" : ""}>{value}</span>}
        {action && <span className="af-row-action">{action}</span>}
      </span>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="bf-stat-l">{label}</div>
      <div className="bf-stat-v">{value}</div>
    </div>
  );
}

function Ledger({ mock, filterGold }: { mock?: boolean; filterGold?: boolean }) {
  void mock;
  return (
    <div className={filterGold ? "bf-ledger" : "af-ledger"}>
      <div className={filterGold ? "bf-ledger-head" : "af-ledger-head"}>
        <strong>流水</strong>
        <div className={filterGold ? "bf-filters" : "af-filters"}>
          <button type="button" className="is-on">
            全部
          </button>
          <button type="button">游玩</button>
          <button type="button">创作</button>
          <button type="button">赠送</button>
        </div>
      </div>
      <div className={filterGold ? "bf-date" : "af-date"}>7 月 8 日</div>
      {TXNS.map((t) => (
        <div key={t.title + t.meta} className={filterGold ? "bf-txn" : "af-txn"}>
          <div>
            <div className={filterGold ? "bf-txn-t" : "af-txn-t"}>{t.title}</div>
            <div className={filterGold ? "bf-txn-m" : "af-txn-m"}>{t.meta}</div>
            {t.note && <div className={filterGold ? "bf-txn-n" : "af-txn-n"}>{t.note}</div>}
          </div>
          <div className={filterGold ? "bf-txn-side" : "af-txn-side"}>
            <div
              className={`${filterGold ? "bf-txn-d" : "af-txn-d"}${t.delta.startsWith("+") ? " pos" : ""}${t.delta === "0" ? " zero" : ""}`}
            >
              {t.delta === "0" ? "未扣费" : t.delta}
            </div>
            <div className={filterGold ? "bf-txn-b" : "af-txn-b"}>{t.bal}</div>
          </div>
        </div>
      ))}
    </div>
  );
}

/* ───────────────────────── CSS ───────────────────────── */

const USD_CSS = `
  .usd-root {
    min-height: 100dvh;
    background: var(--lv-bg);
    color: var(--lv-ink);
  }

  .usd-mobile-gate {
    display: none;
    min-height: 100dvh;
    place-items: center;
    flex-direction: column;
    gap: 10px;
    padding: 32px;
  }

  .usd-desktop {
    max-width: 1180px;
    margin: 0 auto;
    padding: 40px 40px 80px;
  }

  @media (max-width: 768px) {
    .usd-desktop { display: none !important; }
    .usd-mobile-gate { display: flex; }
  }

  .usd-top {
    display: flex;
    align-items: flex-end;
    justify-content: space-between;
    gap: 24px;
    margin-bottom: 28px;
  }
  .usd-kicker { color: var(--lv-ink-3); margin-bottom: 8px; }
  .usd-title {
    margin: 0;
    font-family: var(--lv-font-serif);
    font-size: clamp(28px, 3vw, 36px);
    font-weight: 500;
    letter-spacing: -0.02em;
  }
  .usd-lead {
    margin: 8px 0 0;
    color: var(--lv-ink-3);
    font-size: 14px;
    max-width: 560px;
    line-height: 1.55;
  }

  .usd-mode, .usd-tabs {
    display: inline-flex;
    gap: 4px;
    padding: 4px;
    border-radius: var(--lv-r-pill);
    background: rgba(255,255,255,0.04);
    border: 1px solid var(--lv-line);
  }
  .usd-mode button, .usd-tabs button {
    height: 34px;
    padding: 0 16px;
    border: none;
    border-radius: var(--lv-r-pill);
    background: transparent;
    color: var(--lv-ink-3);
    font-size: 13px;
    font-weight: 500;
    cursor: pointer;
  }
  .usd-mode button.is-on, .usd-tabs button.is-on {
    background: rgba(255,255,255,0.1);
    color: var(--lv-ink);
  }

  .usd-tabs { margin-bottom: 20px; }

  .usd-stage {
    position: relative;
    border-radius: 20px;
    border: 1px solid var(--lv-line);
    background: #0a0a0c;
    padding: 28px 28px 32px;
    min-height: 560px;
    overflow: hidden;
  }
  .usd-stage[data-mode="before"] {
    background:
      radial-gradient(ellipse 50% 40% at 50% -10%, rgba(223,194,144,0.07), transparent 60%),
      #0a0a0c;
  }

  .usd-notes {
    margin-top: 18px;
    padding: 14px 18px;
    border-radius: var(--lv-r-card);
    border: 1px solid var(--lv-line);
    background: rgba(255,255,255,0.02);
  }
  .usd-notes ul {
    margin: 0;
    padding-left: 18px;
    color: var(--lv-ink-3);
    font-size: 13px;
    line-height: 1.7;
  }
  .usd-notes code {
    font-family: var(--lv-font-mono);
    font-size: 12px;
    color: var(--lv-ink-2);
  }

  /* ── BEFORE ── */
  .bf-shell {
    display: grid;
    grid-template-columns: 220px 1fr;
    gap: 48px;
    align-items: start;
    position: relative;
  }
  .bf-rail { display: flex; flex-direction: column; gap: 20px; }
  .bf-id { display: flex; align-items: center; gap: 12px; }
  .bf-avatar {
    width: 48px; height: 48px; border-radius: 50%;
    display: grid; place-items: center;
    background: rgba(245,242,235,0.08);
    border: 1px solid var(--lv-line-2);
    font-weight: 500; font-size: 18px;
  }
  .bf-avatar.lg { width: 64px; height: 64px; font-size: 24px; font-family: var(--lv-font-serif); }
  .bf-name { font-size: 16px; font-weight: 500; }
  .bf-email { font-size: 12px; color: var(--lv-ink-3); margin-top: 2px; }
  .bf-nav { display: flex; flex-direction: column; gap: 2px; }
  .bf-nav-item {
    position: relative;
    display: flex; align-items: center; gap: 10px;
    height: 42px; padding: 0 14px;
    border-radius: var(--lv-r-card);
    color: var(--lv-ink-3); font-size: 13px;
  }
  .bf-nav-rule {
    position: absolute; left: 0; top: 50%; transform: translateY(-50%);
    width: 2px; height: 0; border-radius: 2px; background: var(--lv-accent);
  }
  .bf-nav-item.is-active {
    color: var(--lv-ink);
    background: rgba(223,194,144,0.07);
  }
  .bf-nav-item.is-active .bf-nav-rule { height: 18px; }
  .bf-nav-bal { margin-left: auto; font-size: 12px; font-weight: 600; font-variant-numeric: tabular-nums; color: var(--lv-ink-2); }
  .bf-nav-bal.gold { color: var(--lv-accent); }
  .bf-logout {
    display: inline-flex; align-items: center; gap: 8px;
    background: none; border: none; color: var(--lv-ink-3);
    font-size: 13px; cursor: pointer; padding: 8px 12px; align-self: flex-start;
  }
  .bf-page-title {
    margin: 0 0 18px;
    font-family: var(--lv-font-serif);
    font-size: 28px; font-weight: 500;
  }
  .bf-card {
    border-radius: var(--lv-r-card);
    border: 1px solid var(--lv-line);
    background: rgba(255,255,255,0.02);
    padding: 6px 18px;
    margin-bottom: 14px;
  }
  .bf-avatar-row { display: flex; align-items: center; gap: 18px; padding: 18px; }
  .bf-card-head { color: var(--lv-ink-3); font-size: 12px; padding: 14px 0 8px; }
  .bf-pill {
    display: inline-flex; align-items: center; gap: 6px;
    height: 34px; padding: 0 14px; border-radius: 999px;
    border: 1px solid var(--lv-line-2); background: rgba(255,255,255,0.04);
    color: var(--lv-ink); font-size: 13px; cursor: pointer;
  }
  .bf-hint { font-size: 12px; color: var(--lv-ink-4); margin-top: 6px; }
  .bf-row-line {
    display: flex; align-items: center; justify-content: space-between;
    min-height: 48px; border-bottom: 1px solid var(--lv-line);
    font-size: 14px;
  }
  .bf-row-line.last { border-bottom: none; }
  .bf-row-label { color: var(--lv-ink-2); }
  .bf-row-right { display: inline-flex; align-items: center; gap: 10px; color: var(--lv-ink); }
  .bf-row-right .muted { color: var(--lv-ink-3); }

  .bf-glow {
    position: absolute; top: -40px; left: 40%; width: 420px; height: 280px;
    background: radial-gradient(ellipse 50% 50% at 50% 50%, rgba(223,194,144,0.08), transparent 70%);
    pointer-events: none;
  }
  .bf-hero-bal { margin-bottom: 20px; position: relative; }
  .bf-hero-label { font-size: 12px; color: var(--lv-ink-3); }
  .bf-hero-num {
    font-size: 44px; font-weight: 600; font-variant-numeric: tabular-nums;
    letter-spacing: -0.03em; margin: 4px 0 16px;
  }
  .bf-hero-num.gold { color: var(--lv-accent); }
  .bf-stats { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; max-width: 400px; }
  .bf-stat-l { font-size: 12px; color: var(--lv-ink-3); }
  .bf-stat-v { font-size: 15px; font-weight: 600; margin-top: 3px; font-variant-numeric: tabular-nums; }

  .bf-ledger, .af-ledger {
    border-radius: var(--lv-r-card);
    border: 1px solid var(--lv-line);
    background: rgba(255,255,255,0.015);
    overflow: hidden;
  }
  .bf-ledger-head, .af-ledger-head {
    display: flex; flex-direction: column; gap: 10px;
    padding: 14px 16px; border-bottom: 1px solid var(--lv-line);
  }
  .bf-ledger-head strong, .af-ledger-head strong { font-size: 15px; }
  .bf-filters, .af-filters { display: flex; flex-wrap: wrap; gap: 6px; }
  .bf-filters button, .af-filters button {
    height: 28px; padding: 0 12px; border-radius: 999px;
    border: 1px solid var(--lv-line); background: transparent;
    color: var(--lv-ink-3); font-size: 12px; cursor: pointer;
  }
  .bf-filters button.is-on {
    color: var(--lv-accent);
    border-color: rgba(223,194,144,0.35);
    background: rgba(223,194,144,0.08);
  }
  .af-filters button.is-on {
    color: var(--lv-ink);
    border-color: rgba(255,255,255,0.16);
    background: rgba(255,255,255,0.08);
  }
  .bf-date, .af-date {
    padding: 10px 16px 4px;
    font-size: 11px; color: var(--lv-ink-4);
    letter-spacing: 0.04em; text-transform: uppercase;
  }
  .bf-txn, .af-txn {
    display: flex; justify-content: space-between; gap: 16px;
    padding: 12px 16px; border-top: 1px solid rgba(255,255,255,0.04);
  }
  .bf-txn-t, .af-txn-t { font-size: 13px; font-weight: 500; }
  .bf-txn-m, .af-txn-m { font-size: 12px; color: var(--lv-ink-3); margin-top: 2px; }
  .bf-txn-n, .af-txn-n { font-size: 12px; color: var(--lv-ink-4); margin-top: 2px; }
  .bf-txn-side, .af-txn-side { text-align: right; flex-shrink: 0; }
  .bf-txn-d, .af-txn-d {
    font-size: 14px; font-weight: 600; font-variant-numeric: tabular-nums;
    font-family: var(--lv-font-mono);
  }
  .bf-txn-d.pos, .af-txn-d.pos { color: var(--lv-success); }
  .bf-txn-d.zero, .af-txn-d.zero { color: var(--lv-ink-3); font-size: 12px; font-weight: 500; }
  .bf-txn-b, .af-txn-b { font-size: 11px; color: var(--lv-ink-4); margin-top: 2px; font-variant-numeric: tabular-nums; }

  .bf-panel, .af-panel {
    max-width: 400px;
    margin: 0 auto;
    border-radius: 16px;
    border: 1px solid var(--lv-line-2);
    background: var(--lv-bg-1);
    overflow: hidden;
  }
  .bf-panel-head, .af-panel-head {
    display: flex; align-items: flex-start; justify-content: space-between;
    padding: 18px 18px 12px;
  }
  .bf-panel-head h2, .af-panel-head h2 {
    margin: 0; font-family: var(--lv-font-serif); font-size: 20px; font-weight: 500;
  }
  .bf-panel-head p, .af-panel-head p {
    margin: 4px 0 0; font-size: 12px; color: var(--lv-ink-3);
  }
  .bf-panel-mark {
    width: 34px; height: 34px; border-radius: 999px;
    display: grid; place-items: center;
  }
  .bf-panel-mark.gold {
    color: var(--lv-accent);
    background: rgba(223,194,144,0.08);
    border: 1px solid rgba(223,194,144,0.14);
  }
  .bf-tabs {
    display: flex; align-items: center; gap: 4px;
    padding: 0 12px 10px; border-bottom: 1px solid rgba(255,255,255,0.11);
  }
  .bf-tabs button {
    height: 30px; padding: 0 10px; border: none; border-radius: 999px;
    background: transparent; color: var(--lv-ink-2); font-size: 13px; font-weight: 600; cursor: pointer;
  }
  .bf-tabs button.is-on { color: var(--lv-ink); background: rgba(255,255,255,0.1); }
  .bf-count {
    min-width: 16px; height: 16px; padding: 0 5px; border-radius: 999px;
    background: var(--lv-badge); color: #fff; font-size: 11px;
    display: inline-flex; align-items: center; justify-content: center;
  }
  .bf-readall {
    margin-left: auto; font-size: 12px; color: var(--lv-ink-4) !important; font-weight: 400 !important;
  }
  .bf-readall.gold-hover:hover { color: var(--lv-accent) !important; }
  .bf-list, .af-list { padding: 6px; max-height: 360px; overflow: auto; }
  .bf-row, .af-row {
    position: relative;
    display: flex; gap: 11px; width: 100%; text-align: left;
    padding: 12px 12px 12px 16px;
    background: rgba(255,255,255,0.025); border: 1px solid transparent;
    border-radius: 10px; cursor: pointer; margin-bottom: 4px;
  }
  .bf-dot {
    position: absolute; left: 5px; top: 16px;
    width: 6px; height: 6px; border-radius: 50%;
  }
  .bf-dot.gold { background: var(--lv-accent); }
  .bf-ico, .af-ico {
    flex: 0 0 auto; width: 26px; height: 26px;
    display: grid; place-items: center; border-radius: 8px;
    color: var(--lv-ink-2); background: rgba(255,255,255,0.07); margin-top: 1px;
  }
  .af-ico.sm { width: 20px; height: 20px; border-radius: 6px; }
  .bf-body, .af-body { display: flex; flex-direction: column; gap: 3px; min-width: 0; }
  .bf-t, .af-t { font-size: 13px; font-weight: 500; color: var(--lv-ink); }
  .af-t.is-unread { font-weight: 600; }
  .bf-s, .af-s {
    font-size: 12px; color: var(--lv-ink-3); line-height: 1.45;
    display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
  }
  .bf-time, .af-time { font-size: 11px; color: var(--lv-ink-4); }

  .bf-fb, .af-fb { max-width: 460px; margin: 0 auto; display: flex; flex-direction: column; }
  .bf-cats { display: flex; gap: 8px; margin-bottom: 16px; }
  .bf-cat {
    flex: 1; height: 42px; border-radius: 999px;
    border: 1px solid var(--lv-line-2); background: transparent;
    color: var(--lv-ink-3); font-size: 13px; font-weight: 500; cursor: pointer;
    display: inline-flex; align-items: center; justify-content: center; gap: 7px;
  }
  .bf-cat.is-on { color: var(--lv-bg); background: var(--lv-ink); border-color: var(--lv-ink); }
  .bf-label, .af-field-label {
    color: var(--lv-ink-3); font-size: 12px; margin-bottom: 7px;
  }
  .bf-ta, .af-ta, .bf-input, .af-input {
    width: 100%;
    border-radius: var(--lv-r-input);
    border: 1px solid var(--lv-line-2);
    background: rgba(255,255,255,0.03);
    color: var(--lv-ink);
    padding: 10px 12px;
    font-size: 14px;
    outline: none;
    resize: vertical;
  }
  .bf-ta:focus, .af-ta:focus, .bf-input:focus, .af-input:focus {
    border-color: rgba(255,255,255,0.22);
  }
  .bf-upload {
    display: inline-flex; align-items: center; gap: 7px;
    height: 38px; padding: 0 15px; margin: 12px 0 16px; align-self: flex-start;
    border-radius: 999px; border: 1px dashed var(--lv-line-2);
    background: transparent; color: var(--lv-ink-3); font-size: 13px; cursor: pointer;
  }
  .bf-submit { width: 100%; justify-content: center; margin-top: 18px; }

  /* ── AFTER ── */
  .af-shell {
    display: grid;
    grid-template-columns: 220px 1fr;
    gap: 48px;
    align-items: start;
  }
  .af-rail { display: flex; flex-direction: column; gap: 22px; }
  .af-id { display: flex; align-items: center; gap: 12px; }
  .af-avatar {
    width: 48px; height: 48px; border-radius: 50%;
    display: grid; place-items: center;
    background: rgba(245,242,235,0.07);
    border: 1px solid var(--lv-line);
    font-weight: 500; font-size: 18px; color: var(--lv-ink);
  }
  .af-avatar.lg { width: 72px; height: 72px; font-size: 28px; font-family: var(--lv-font-serif); }
  .af-name { font-size: 15px; font-weight: 500; letter-spacing: -0.01em; }
  .af-email { font-size: 12px; color: var(--lv-ink-3); margin-top: 2px; }
  .af-nav { display: flex; flex-direction: column; gap: 2px; }
  .af-nav-item {
    display: flex; align-items: center; gap: 10px;
    height: 40px; padding: 0 12px;
    border-radius: 10px;
    color: var(--lv-ink-3); font-size: 13px;
  }
  .af-nav-item.is-active {
    color: var(--lv-ink);
    background: rgba(255,255,255,0.06);
  }
  .af-nav-bal {
    margin-left: auto;
    font-size: 12px; font-weight: 600;
    font-variant-numeric: tabular-nums;
    font-family: var(--lv-font-mono);
    color: var(--lv-ink-2);
  }
  .af-logout {
    display: inline-flex; align-items: center; gap: 8px;
    background: none; border: none; color: var(--lv-ink-4);
    font-size: 13px; cursor: pointer; padding: 8px 12px; align-self: flex-start;
  }
  .af-logout:hover { color: var(--lv-danger); }

  .af-main { min-width: 0; display: flex; flex-direction: column; gap: 14px; }
  .af-page-head { margin-bottom: 4px; }
  .af-page-head h2 {
    margin: 0;
    font-family: var(--lv-font-serif);
    font-size: 28px; font-weight: 500;
    letter-spacing: -0.02em;
  }
  .af-page-head p {
    margin: 6px 0 0;
    font-size: 13px; color: var(--lv-ink-3);
  }

  .af-card {
    border-radius: 14px;
    border: 1px solid var(--lv-line);
    background: rgba(255,255,255,0.018);
    padding: 4px 16px;
  }
  .af-identity {
    display: flex; align-items: center; gap: 18px;
    padding: 18px 16px;
  }
  .af-identity-name { font-size: 16px; font-weight: 500; }
  .af-identity-sub { font-size: 12px; color: var(--lv-ink-3); margin: 3px 0 10px; }
  .af-ghost-btn {
    display: inline-flex; align-items: center; gap: 6px;
    height: 32px; padding: 0 12px; border-radius: 999px;
    border: 1px solid var(--lv-line-2);
    background: transparent;
    color: var(--lv-ink-2); font-size: 12.5px; cursor: pointer;
  }
  .af-ghost-btn:hover {
    color: var(--lv-ink);
    background: rgba(255,255,255,0.04);
    border-color: rgba(255,255,255,0.16);
  }
  .af-section-label {
    font-size: 11px; color: var(--lv-ink-4);
    letter-spacing: 0.08em; text-transform: uppercase;
    padding: 14px 0 6px;
  }
  .af-row-line {
    display: flex; align-items: center; justify-content: space-between;
    min-height: 46px; border-bottom: 1px solid rgba(255,255,255,0.05);
    font-size: 14px;
  }
  .af-row-line.last { border-bottom: none; }
  .af-row-label { color: var(--lv-ink-2); }
  .af-row-right { display: inline-flex; align-items: center; gap: 12px; color: var(--lv-ink); }
  .af-row-right .muted { color: var(--lv-ink-3); }
  .af-row-action {
    color: var(--lv-ink-3); font-size: 12.5px;
    padding: 4px 0;
  }

  .af-wallet {
    display: flex; align-items: flex-end; justify-content: space-between;
    gap: 24px; flex-wrap: wrap;
    padding: 18px 4px 8px;
  }
  .af-wallet-label {
    font-size: 11px; color: var(--lv-ink-4);
    letter-spacing: 0.08em; text-transform: uppercase;
  }
  .af-wallet-num {
    margin-top: 6px;
    font-family: var(--lv-font-mono);
    font-size: 42px; font-weight: 500;
    font-variant-numeric: tabular-nums;
    letter-spacing: -0.04em;
    color: var(--lv-ink);
    line-height: 1;
  }
  .af-wallet-grid {
    display: grid; grid-template-columns: repeat(3, auto); gap: 28px;
  }
  .af-wallet-grid span {
    display: block; font-size: 11px; color: var(--lv-ink-4); margin-bottom: 4px;
  }
  .af-wallet-grid b {
    font-size: 15px; font-weight: 600;
    font-variant-numeric: tabular-nums;
    font-family: var(--lv-font-mono);
    color: var(--lv-ink-2);
  }

  .af-panel-head { align-items: center; }
  .af-text-btn {
    background: none; border: none;
    color: var(--lv-ink-3); font-size: 12px; cursor: pointer;
    padding: 6px 8px; border-radius: 8px;
  }
  .af-text-btn:hover { color: var(--lv-ink); background: rgba(255,255,255,0.05); }
  .af-seg {
    display: flex; gap: 4px;
    margin: 0 12px 10px; padding: 3px;
    border-radius: 10px;
    background: rgba(255,255,255,0.04);
    border: 1px solid var(--lv-line);
  }
  .af-seg.full { margin: 0 0 16px; }
  .af-seg button {
    flex: 1;
    height: 32px; border: none; border-radius: 8px;
    background: transparent; color: var(--lv-ink-3);
    font-size: 13px; font-weight: 500; cursor: pointer;
    display: inline-flex; align-items: center; justify-content: center; gap: 6px;
  }
  .af-seg button.is-on {
    background: rgba(255,255,255,0.09);
    color: var(--lv-ink);
  }
  .af-badge {
    min-width: 16px; height: 16px; padding: 0 5px; border-radius: 999px;
    background: var(--lv-badge); color: #fff; font-size: 11px;
    display: inline-flex; align-items: center; justify-content: center;
  }
  .af-dot {
    position: absolute; left: 6px; top: 17px;
    width: 6px; height: 6px; border-radius: 50%;
    background: var(--lv-badge);
  }
  .af-panel-foot {
    display: flex; align-items: center; gap: 8px;
    padding: 12px 16px 14px;
    border-top: 1px solid var(--lv-line);
  }

  .af-success-preview {
    display: flex; align-items: center; gap: 12px;
    margin-top: 22px; padding: 14px 14px;
    border-radius: 12px;
    border: 1px solid rgba(127,176,145,0.22);
    background: rgba(127,176,145,0.06);
  }
  .af-success-mark {
    width: 36px; height: 36px; border-radius: 50%;
    display: grid; place-items: center;
    background: rgba(127,176,145,0.16);
    color: var(--lv-success); flex-shrink: 0;
  }
  .af-success-preview strong { display: block; font-size: 13px; font-weight: 600; }
  .af-success-preview p { margin: 2px 0 0; font-size: 12px; color: var(--lv-ink-3); }
`;
