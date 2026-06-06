"use client";

import Link from "next/link";
import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useTranslations } from "next-intl";
import { ArrowRight, CheckCircle2, Loader2, MailWarning } from "lucide-react";

import { verifyEmail } from "@/lib/auth-api";
import { useAuthStore } from "@/stores/auth";

const REDIRECT_SECONDS = 5;
const HOME_PATH = "/";

function VerifyEmailInner() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const tp = useTranslations("verifyEmailPage");
  const token = searchParams.get("token") || "";
  const loadMe = useAuthStore((s) => s.loadMe);

  const [status, setStatus] = useState<"loading" | "done" | "error">("loading");
  const [message, setMessage] = useState<string | null>(null);
  const [seconds, setSeconds] = useState(REDIRECT_SECONDS);

  useEffect(() => {
    let alive = true;
    async function run() {
      if (!token) {
        setStatus("error");
        setMessage(tp("missingToken"));
        return;
      }
      try {
        await verifyEmail(token);
        await loadMe();
        if (!alive) return;
        setStatus("done");
      } catch (err) {
        if (!alive) return;
        setStatus("error");
        setMessage(err instanceof Error ? err.message : tp("failed"));
      }
    }
    void run();
    return () => {
      alive = false;
    };
  }, [loadMe, token, tp]);

  // 验证成功后倒计时自动跳首页（给用户明确的"成功了"反馈，而非瞬间跳走）。
  useEffect(() => {
    if (status !== "done") return;
    if (seconds <= 0) {
      router.replace(HOME_PATH);
      return;
    }
    const timer = window.setTimeout(() => setSeconds((s) => s - 1), 1000);
    return () => window.clearTimeout(timer);
  }, [status, seconds, router]);

  return (
    <main
      className="verify-page lv-theme"
      /* 关键布局内联，首屏即居中，不等 styled-jsx 注入（消除冷加载时"框先靠左"的 FOUC） */
      style={{ minHeight: "100dvh", display: "grid", justifyItems: "center", alignItems: "safe center" }}
    >
      <div className="verify-bg" aria-hidden />
      <section className="verify-card">
        <div className="verify-brand">
          <span className="verify-logo" aria-hidden>
            <svg viewBox="0 0 100 120" width="22" height="26" fill="none">
              <g stroke="var(--lv-ink)" strokeWidth="6.5" strokeLinecap="round">
                <path d="M 50 112 Q 50 84, 52 56 Q 54 32, 52 12" />
                <path d="M 51 84 Q 62 80, 76 70" />
                <path d="M 52 58 Q 40 52, 28 46" />
                <path d="M 52 28 Q 62 24, 72 18" />
                <path d="M 76 70 L 81 66" />
              </g>
            </svg>
          </span>
          <span className="lv-t-h3 verify-wordmark">InkWild</span>
        </div>

        <span className={`verify-icon ${status}`} aria-hidden>
          {status === "loading" ? (
            <Loader2 size={24} />
          ) : status === "done" ? (
            <CheckCircle2 size={24} />
          ) : (
            <MailWarning size={24} />
          )}
        </span>

        <h1 className="lv-t-h2 verify-title">
          {status === "loading" ? tp("loadingTitle") : status === "done" ? tp("doneTitle") : tp("errorTitle")}
        </h1>
        <p className="lv-t-body verify-body">
          {status === "loading" ? tp("loadingBody") : status === "done" ? tp("doneBody") : message}
        </p>

        {status === "done" && (
          <div className="verify-actions">
            <button type="button" className="verify-cta" onClick={() => router.replace(HOME_PATH)}>
              <span>{tp("enterNow")}</span>
              <ArrowRight size={16} />
            </button>
            <span className="lv-t-meta verify-countdown">{tp("autoRedirect", { seconds })}</span>
          </div>
        )}

        {status === "error" && (
          <div className="verify-actions">
            <Link href="/login?mode=register" className="verify-cta">
              {tp("backToRegister")}
            </Link>
            <Link href="/login" className="lv-t-meta verify-secondary-link">
              {tp("backToLogin")}
            </Link>
          </div>
        )}
      </section>

      <style jsx global>{`
        .verify-page {
          min-height: 100dvh;
          position: relative;
          overflow: hidden;
          display: grid;
          place-items: center;
          padding: calc(40px + env(safe-area-inset-top)) 16px calc(48px + env(safe-area-inset-bottom));
          background: var(--lv-bg);
          color: var(--lv-ink);
        }
        .verify-bg {
          position: absolute;
          inset: 0;
          z-index: 0;
          background:
            linear-gradient(135deg, rgba(255, 255, 255, 0.02) 0%, transparent 35%),
            linear-gradient(180deg, #0d1014 0%, #050507 100%);
        }
        .verify-card {
          position: relative;
          z-index: 1;
          width: min(420px, 100%);
          border: 1px solid rgba(255, 255, 255, 0.06);
          border-radius: var(--lv-r-card);
          background: rgba(5, 5, 7, 0.72);
          box-shadow: 0 40px 100px rgba(0, 0, 0, 0.65), inset 0 1px 0 rgba(255, 255, 255, 0.05);
          backdrop-filter: blur(24px) saturate(140%);
          -webkit-backdrop-filter: blur(24px) saturate(140%);
          padding: 36px 32px;
          display: flex;
          flex-direction: column;
          align-items: center;
          text-align: center;
          gap: 14px;
        }
        .verify-brand {
          display: inline-flex;
          align-items: center;
          gap: 10px;
          margin-bottom: 4px;
        }
        .verify-logo {
          width: 40px;
          height: 40px;
          border-radius: 11px;
          display: grid;
          place-items: center;
          background: #0a0a0c;
          border: 1px solid rgba(255, 255, 255, 0.08);
          box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.05);
        }
        .verify-wordmark {
          font-family: var(--lv-font-serif);
          font-weight: 500;
          letter-spacing: -0.01em;
          color: var(--lv-ink);
        }
        .verify-icon {
          width: 52px;
          height: 52px;
          border-radius: 50%;
          display: grid;
          place-items: center;
          border: 1px solid rgba(255, 255, 255, 0.08);
          background: rgba(255, 255, 255, 0.03);
          color: var(--lv-ink-2);
          margin-top: 4px;
        }
        .verify-icon.loading svg {
          animation: verifySpin 1s linear infinite;
        }
        .verify-icon.done {
          border-color: rgba(127, 176, 145, 0.28);
          background: rgba(127, 176, 145, 0.1);
          color: var(--lv-success);
        }
        .verify-icon.error {
          border-color: rgba(239, 130, 118, 0.24);
          background: rgba(239, 130, 118, 0.08);
          color: var(--lv-danger);
        }
        .verify-title {
          margin: 0;
          color: var(--lv-ink);
        }
        .verify-body {
          margin: 0;
          max-width: 320px;
          line-height: 1.6;
          color: var(--lv-ink-2);
        }
        .verify-actions {
          display: flex;
          flex-direction: column;
          align-items: center;
          gap: 12px;
          width: 100%;
          margin-top: 10px;
        }
        .verify-cta {
          width: 100%;
          height: 48px;
          border-radius: var(--lv-r-pill);
          background: rgba(245, 242, 235, 0.94);
          color: var(--lv-bg);
          border: none;
          display: inline-flex;
          align-items: center;
          justify-content: center;
          gap: 8px;
          font-family: var(--lv-font-sans);
          font-size: 15px;
          font-weight: 600;
          cursor: pointer;
          text-decoration: none;
          transition:
            background var(--lv-dur-fast) var(--lv-ease),
            transform var(--lv-dur-fast) var(--lv-ease),
            box-shadow var(--lv-dur-fast) var(--lv-ease);
          touch-action: manipulation;
        }
        .verify-cta:hover {
          background: rgba(245, 242, 235, 1);
          transform: translateY(-1px);
          box-shadow: 0 12px 30px rgba(0, 0, 0, 0.55);
        }
        .verify-cta:active {
          transform: translateY(0.5px);
        }
        .verify-countdown {
          color: var(--lv-ink-3);
          font-variant-numeric: tabular-nums;
        }
        .verify-secondary-link {
          color: var(--lv-ink-3);
          text-decoration: underline;
          text-underline-offset: 3px;
          transition: color var(--lv-dur-fast) var(--lv-ease);
        }
        .verify-secondary-link:hover {
          color: var(--lv-ink);
        }
        @keyframes verifySpin {
          to {
            transform: rotate(360deg);
          }
        }
      `}</style>
    </main>
  );
}

export default function VerifyEmailPage() {
  return (
    <Suspense fallback={null}>
      <VerifyEmailInner />
    </Suspense>
  );
}
