"use client";

import Link from "next/link";
import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import { zodResolver } from "@hookform/resolvers/zod";
import { useTranslations } from "next-intl";
import { ArrowRight, CheckCircle2, Eye, EyeOff } from "lucide-react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { resetPassword } from "@/lib/auth-api";

type ResetValues = { password: string };

function ResetPasswordInner() {
  const searchParams = useSearchParams();
  const t = useTranslations("auth");
  const tp = useTranslations("resetPasswordPage");
  const token = searchParams.get("token") || "";

  const [busy, setBusy] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  const schema = z.object({
    password: z.string().min(8, t("passwordMin")),
  });

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<ResetValues>({
    resolver: zodResolver(schema),
    defaultValues: { password: "" },
  });

  const onSubmit = async (values: ResetValues) => {
    if (!token) return;
    setBusy(true);
    setError(null);
    try {
      await resetPassword({ token, newPassword: values.password });
      setDone(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : tp("failed"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <main
      className="reset-page lv-theme"
      /* 关键布局内联，首屏即居中，不等 styled-jsx 注入（消除冷加载时"框先靠左"的 FOUC） */
      style={{ minHeight: "100dvh", display: "grid", justifyItems: "center", alignItems: "safe center" }}
    >
      <div className="reset-bg" aria-hidden />
      <section className="reset-card">
        <div className="reset-brand">
          <span className="reset-logo" aria-hidden>
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
          <span className="lv-t-h3 reset-wordmark">InkWild</span>
        </div>

        {done && (
          <span className="reset-status-icon" aria-hidden>
            <CheckCircle2 size={24} />
          </span>
        )}

        <h1 className="lv-t-h2 reset-title">{done ? tp("doneTitle") : tp("title")}</h1>
        <p className="lv-t-body reset-body">
          {done ? tp("doneBody") : token ? tp("subtitle") : tp("missingToken")}
        </p>

        {done ? (
          <Link href="/login" className="reset-cta">
            <span>{tp("backToLogin")}</span>
            <ArrowRight size={16} />
          </Link>
        ) : (
          <form onSubmit={handleSubmit(onSubmit)} className="reset-form" noValidate>
            <div className="reset-field">
              <span className="lv-form-label">{tp("passwordLabel")}</span>
              <div className="reset-input-wrap">
                <input
                  type={showPassword ? "text" : "password"}
                  autoComplete="new-password"
                  disabled={busy || !token}
                  placeholder={tp("passwordPlaceholder")}
                  className={`reset-input ${errors.password ? "has-error" : ""}`}
                  {...register("password")}
                />
                <button
                  type="button"
                  className="reset-toggle"
                  onClick={() => setShowPassword((v) => !v)}
                  aria-label={showPassword ? tp("hidePassword") : tp("showPassword")}
                >
                  {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
              {errors.password?.message && <em className="reset-error">{errors.password.message}</em>}
            </div>
            {error && <p className="reset-error reset-error-block">{error}</p>}
            <button type="submit" className="reset-cta" disabled={busy || !token}>
              <span>{busy ? tp("submitting") : tp("submit")}</span>
              {!busy && <ArrowRight size={16} />}
            </button>
          </form>
        )}
      </section>

      <style jsx global>{`
        .reset-page {
          min-height: 100dvh;
          position: relative;
          overflow-x: hidden;
          display: grid;
          justify-items: center;
          align-items: safe center;
          padding: calc(28px + env(safe-area-inset-top)) 16px calc(28px + env(safe-area-inset-bottom));
          background: var(--lv-bg);
          color: var(--lv-ink);
        }
        .reset-bg {
          position: absolute;
          inset: 0;
          z-index: 0;
          background:
            linear-gradient(135deg, rgba(255, 255, 255, 0.02) 0%, transparent 35%),
            linear-gradient(180deg, #0d1014 0%, #050507 100%);
        }
        .reset-card {
          position: relative;
          z-index: 1;
          width: min(420px, 100%);
          border: 1px solid rgba(255, 255, 255, 0.06);
          border-radius: var(--lv-r-card);
          background: rgba(5, 5, 7, 0.72);
          box-shadow: 0 40px 100px rgba(0, 0, 0, 0.65), inset 0 1px 0 rgba(255, 255, 255, 0.05);
          backdrop-filter: blur(24px) saturate(140%);
          -webkit-backdrop-filter: blur(24px) saturate(140%);
          padding: 28px 28px;
          display: flex;
          flex-direction: column;
          align-items: center;
          text-align: center;
          gap: 14px;
        }
        .reset-brand {
          display: inline-flex;
          align-items: center;
          gap: 10px;
          margin-bottom: 2px;
        }
        .reset-logo {
          width: 40px;
          height: 40px;
          border-radius: 11px;
          display: grid;
          place-items: center;
          background: #0a0a0c;
          border: 1px solid rgba(255, 255, 255, 0.08);
          box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.05);
        }
        .reset-wordmark {
          font-family: var(--lv-font-serif);
          font-weight: 500;
          letter-spacing: -0.01em;
          color: var(--lv-ink);
        }
        .reset-status-icon {
          width: 52px;
          height: 52px;
          border-radius: 50%;
          display: grid;
          place-items: center;
          border: 1px solid rgba(127, 176, 145, 0.28);
          background: rgba(127, 176, 145, 0.1);
          color: var(--lv-success);
          margin-top: 2px;
        }
        .reset-title {
          margin: 0;
          color: var(--lv-ink);
        }
        .reset-body {
          margin: 0;
          max-width: 320px;
          line-height: 1.6;
          color: var(--lv-ink-2);
        }
        .reset-form {
          width: 100%;
          display: flex;
          flex-direction: column;
          gap: 14px;
          margin-top: 6px;
        }
        .reset-field {
          display: flex;
          flex-direction: column;
          gap: 6px;
          text-align: left;
        }
        .reset-field .lv-form-label {
          margin-bottom: 0;
          padding-left: 2px;
        }
        .reset-input-wrap {
          position: relative;
        }
        .reset-input {
          width: 100%;
          height: 46px;
          border-radius: var(--lv-r-pill);
          border: 1px solid rgba(255, 255, 255, 0.1);
          background: rgba(255, 255, 255, 0.045);
          color: var(--lv-ink);
          padding: 0 48px 0 18px;
          font-family: var(--lv-font-sans);
          font-size: 14px;
          outline: none;
          transition:
            border-color var(--lv-dur-fast) var(--lv-ease),
            background var(--lv-dur-fast) var(--lv-ease);
        }
        .reset-input::placeholder {
          color: var(--lv-ink-3);
        }
        .reset-input:focus {
          border-color: rgba(255, 255, 255, 0.22);
          background: rgba(255, 255, 255, 0.07);
        }
        .reset-input.has-error {
          border-color: rgba(239, 130, 118, 0.4);
        }
        .reset-toggle {
          position: absolute;
          top: 50%;
          right: 6px;
          transform: translateY(-50%);
          width: 36px;
          height: 36px;
          border: 0;
          border-radius: 50%;
          background: transparent;
          color: var(--lv-ink-3);
          display: grid;
          place-items: center;
          cursor: pointer;
          transition:
            color var(--lv-dur-fast) var(--lv-ease),
            background var(--lv-dur-fast) var(--lv-ease);
          touch-action: manipulation;
        }
        .reset-toggle:hover {
          color: var(--lv-ink);
          background: rgba(255, 255, 255, 0.06);
        }
        .reset-error {
          color: var(--lv-danger);
          font-size: 11px;
          font-style: normal;
          padding-left: 4px;
        }
        .reset-error-block {
          margin: 0;
          text-align: left;
        }
        .reset-cta {
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
          margin-top: 2px;
          transition:
            background var(--lv-dur-fast) var(--lv-ease),
            transform var(--lv-dur-fast) var(--lv-ease),
            box-shadow var(--lv-dur-fast) var(--lv-ease);
          touch-action: manipulation;
        }
        .reset-cta:hover:not(:disabled) {
          background: rgba(245, 242, 235, 1);
          transform: translateY(-1px);
          box-shadow: 0 12px 30px rgba(0, 0, 0, 0.55);
        }
        .reset-cta:active:not(:disabled) {
          transform: translateY(0.5px);
        }
        .reset-cta:disabled {
          opacity: 0.5;
          cursor: not-allowed;
        }
        @media (max-width: 900px) {
          .reset-card {
            padding: 26px 20px;
            box-shadow: 0 16px 40px rgba(0, 0, 0, 0.5);
          }
        }
      `}</style>
    </main>
  );
}

export default function ResetPasswordPage() {
  return (
    <Suspense fallback={null}>
      <ResetPasswordInner />
    </Suspense>
  );
}
