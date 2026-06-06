"use client";

import Link from "next/link";
import { Suspense, useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { zodResolver } from "@hookform/resolvers/zod";
import { useTranslations } from "next-intl";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { AlertCircle, ArrowLeft, ArrowRight, Eye, EyeOff, MailCheck } from "lucide-react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import {
  oauthStartUrl,
  registerWithPassword,
  requestPasswordReset,
  resendVerification,
  type AuthProvider,
} from "@/lib/auth-api";
import { resolveAuthNextPath } from "@/lib/auth-redirect";
import { pickFeaturedWorlds } from "@/lib/featured-worlds";
import { LV_EASE, lvStaggerContainer, lvStaggerItem } from "@/lib/motion";
import { useAuthStore } from "@/stores/auth";
import { useWorldList } from "@/lib/api/worlds";
import { ossThumb } from "@/lib/oss-image";
import type { WorldListItem } from "@/lib/types";

type AuthMode = "signin" | "register" | "forgot";
type AuthValues = { email: string; password: string; nickname: string };

// Google OAuth 暂未配置凭据（backend/.env 缺 GOOGLE_CLIENT_ID/SECRET）→ 按钮置灰。
// 配好后把这里改 true 即可放开。
const GOOGLE_OAUTH_ENABLED = false;

function GoogleMark() {
  return (
    <svg width="19" height="19" viewBox="0 0 18 18" aria-hidden style={{ flexShrink: 0 }}>
      <path fill="#4285F4" d="M17.64 9.2c0-.64-.06-1.25-.16-1.84H9v3.48h4.84a4.14 4.14 0 0 1-1.8 2.72v2.26h2.92c1.7-1.57 2.68-3.88 2.68-6.62Z" />
      <path fill="#34A853" d="M9 18c2.43 0 4.47-.8 5.96-2.18l-2.92-2.26c-.8.54-1.84.86-3.04.86-2.35 0-4.34-1.58-5.05-3.72H.94v2.33A9 9 0 0 0 9 18Z" />
      <path fill="#FBBC05" d="M3.95 10.7A5.4 5.4 0 0 1 3.66 9c0-.59.1-1.16.29-1.7V4.97H.94A9 9 0 0 0 0 9c0 1.45.34 2.82.94 4.03l3.01-2.33Z" />
      <path fill="#EA4335" d="M9 3.58c1.32 0 2.5.45 3.44 1.35l2.6-2.6A8.7 8.7 0 0 0 9 0 9 9 0 0 0 .94 4.97l3.01 2.33C4.66 5.16 6.65 3.58 9 3.58Z" />
    </svg>
  );
}

function LinuxDoMark() {
  // 官方 LinuxDo 标识矢量原件（圆形 + 顶部深色条 + 底部琥珀条），填满槽位、任意尺寸清晰。
  return (
    <svg width="20" height="20" viewBox="0 0 16 16" aria-hidden style={{ flexShrink: 0, display: "block" }}>
      <path
        d="m7.44,0s.09,0,.13,0c.09,0,.19,0,.28,0,.14,0,.29,0,.43,0,.09,0,.18,0,.27,0q.12,0,.25,0t.26.08c.15.03.29.06.44.08,1.97.38,3.78,1.47,4.95,3.11.04.06.09.12.13.18.67.96,1.15,2.11,1.3,3.28q0,.19.09.26c0,.15,0,.29,0,.44,0,.04,0,.09,0,.13,0,.09,0,.19,0,.28,0,.14,0,.29,0,.43,0,.09,0,.18,0,.27,0,.08,0,.17,0,.25q0,.19-.08.26c-.03.15-.06.29-.08.44-.38,1.97-1.47,3.78-3.11,4.95-.06.04-.12.09-.18.13-.96.67-2.11,1.15-3.28,1.3q-.19,0-.26.09c-.15,0-.29,0-.44,0-.04,0-.09,0-.13,0-.09,0-.19,0-.28,0-.14,0-.29,0-.43,0-.09,0-.18,0-.27,0-.08,0-.17,0-.25,0q-.19,0-.26-.08c-.15-.03-.29-.06-.44-.08-1.97-.38-3.78-1.47-4.95-3.11q-.07-.09-.13-.18c-.67-.96-1.15-2.11-1.3-3.28q0-.19-.09-.26c0-.15,0-.29,0-.44,0-.04,0-.09,0-.13,0-.09,0-.19,0-.28,0-.14,0-.29,0-.43,0-.09,0-.18,0-.27,0-.08,0-.17,0-.25q0-.19.08-.26c.03-.15.06-.29.08-.44.38-1.97,1.47-3.78,3.11-4.95.06-.04.12-.09.18-.13C4.42.73,5.57.26,6.74.1,7,.07,7.15,0,7.44,0Z"
        fill="#EFEFEF"
      />
      <path
        d="m1.27,11.33h13.45c-.94,1.89-2.51,3.21-4.51,3.88-1.99.59-3.96.37-5.8-.57-1.25-.7-2.67-1.9-3.14-3.3Z"
        fill="#FEB005"
      />
      <path
        d="m12.54,1.99c.87.7,1.82,1.59,2.18,2.68H1.27c.87-1.74,2.33-3.13,4.2-3.78,2.44-.79,5-.47,7.07,1.1Z"
        fill="#1D1D1F"
      />
    </svg>
  );
}

/**
 * 品牌墨枝标识（对齐 experiments/brand/ 正式规范）。
 * app-icon 处理：玄黑底圆角方块 + 完整 5 笔墨枝 ivory。
 * 入场一次性 draw-on「生长」+ 枝尖单点金色 bloom（唯一一处金，属品牌标识白名单）。
 */
const BRANCH_PATHS = [
  "M 50 112 Q 50 84, 52 56 Q 54 32, 52 12", // trunk
  "M 52 58 Q 40 52, 28 46", // b2
  "M 51 84 Q 62 80, 76 70", // b1
  "M 52 28 Q 62 24, 72 18", // b3
  "M 76 70 L 81 66", // tip
];

function AuthBrandMark() {
  const reduce = useReducedMotion();
  return (
    <svg viewBox="0 0 100 120" width="27" height="32" fill="none" role="img" aria-hidden style={{ display: "block" }}>
      <g stroke="var(--lv-ink)" strokeWidth="6.5" strokeLinecap="round" fill="none">
        {BRANCH_PATHS.map((d, i) => (
          <motion.path
            key={d}
            d={d}
            initial={reduce ? false : { pathLength: 0, opacity: 0 }}
            animate={{ pathLength: 1, opacity: 1 }}
            transition={{ duration: 0.6, delay: reduce ? 0 : 0.15 + i * 0.12, ease: LV_EASE }}
          />
        ))}
      </g>
      <motion.circle
        cx="81"
        cy="66"
        r="3.6"
        fill="var(--lv-accent)"
        initial={reduce ? false : { opacity: 0, scale: 0 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.5, delay: reduce ? 0 : 0.95, ease: LV_EASE }}
      />
    </svg>
  );
}

function buildSchema(
  mode: AuthMode,
  msg: { invalidEmail: string; passwordRequired: string; passwordMin: string },
) {
  return z.object({
    email: z.string().email(msg.invalidEmail),
    nickname: z.string(),
    password:
      mode === "forgot"
        ? z.string()
        : z.string().min(mode === "register" ? 8 : 1, mode === "register" ? msg.passwordMin : msg.passwordRequired),
  });
}

function LoginPageInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const t = useTranslations("auth");
  const tp = useTranslations("loginPage");

  const login = useAuthStore((s) => s.login);
  const isLoading = useAuthStore((s) => s.isLoading);
  const hasLoaded = useAuthStore((s) => s.hasLoaded);
  const user = useAuthStore((s) => s.user);

  // 左侧「本周精选」真实世界数据（甄嬛传置顶 + 按热度取 4），骨架兜底。
  const { data: worldsData, isLoading: worldsLoading } = useWorldList();
  const featuredWorlds = useMemo<WorldListItem[]>(() => pickFeaturedWorlds(worldsData, 4), [worldsData]);

  const [mode, setMode] = useState<AuthMode>(() => {
    const requested = searchParams.get("mode");
    return requested === "register" || requested === "forgot" ? requested : "signin";
  });
  const [busy, setBusy] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [apiError, setApiError] = useState<string | null>(null);
  // 发送验证/重置邮件成功后，整张卡换成「查收邮箱」确认面板（不再露空密码框）。
  const [sent, setSent] = useState<{ kind: "register" | "forgot"; email: string } | null>(null);
  const [resendBusy, setResendBusy] = useState(false);
  const [resendNote, setResendNote] = useState<string | null>(null);

  // 无 next/from 时默认回首页（用户拍板 2026-06-02）；有 next（如"登录后去玩 X"）则优先回那。
  const nextPath = resolveAuthNextPath(searchParams.get("next") || searchParams.get("from") || "/");
  const submitting = isLoading || busy;

  const schema = useMemo(
    () =>
      buildSchema(mode, {
        invalidEmail: t("invalidEmail"),
        passwordRequired: t("passwordRequired"),
        passwordMin: t("passwordMin"),
      }),
    [mode, t],
  );

  const {
    register,
    handleSubmit,
    formState: { errors },
    reset,
    clearErrors,
  } = useForm<AuthValues>({
    resolver: zodResolver(schema),
    defaultValues: { email: "", password: "", nickname: "" },
  });

  useEffect(() => {
    if (hasLoaded && user) {
      router.replace(nextPath);
    }
  }, [hasLoaded, user, nextPath, router]);

  const switchMode = (nextMode: AuthMode) => {
    setMode(nextMode);
    setApiError(null);
    setSent(null);
    setResendNote(null);
    clearErrors();
  };

  const onSubmit = async (values: AuthValues) => {
    setApiError(null);
    setBusy(true);
    try {
      if (mode === "signin") {
        await login(values.email, values.password);
        router.replace(nextPath);
        return;
      }
      if (mode === "register") {
        const result = await registerWithPassword({
          email: values.email,
          password: values.password,
          nickname: values.nickname.trim() || undefined,
        });
        reset({ email: result.email, password: "", nickname: values.nickname });
        setSent({ kind: "register", email: result.email });
        return;
      }
      await requestPasswordReset(values.email);
      reset({ email: values.email, password: "", nickname: "" });
      setSent({ kind: "forgot", email: values.email });
    } catch (err) {
      setApiError(err instanceof Error ? err.message : t("loginFailed"));
    } finally {
      setBusy(false);
    }
  };

  const handleResend = async () => {
    if (!sent || resendBusy) return;
    setResendBusy(true);
    setResendNote(null);
    try {
      if (sent.kind === "register") {
        await resendVerification(sent.email);
      } else {
        await requestPasswordReset(sent.email);
      }
      setResendNote(tp("resendDone"));
    } catch {
      setResendNote(tp("resendFailed"));
    } finally {
      setResendBusy(false);
    }
  };

  const startOAuth = (provider: AuthProvider) => {
    window.location.href = oauthStartUrl(provider, nextPath);
  };

  const submitLabel =
    mode === "register" ? tp("registerCta") : mode === "forgot" ? tp("forgotCta") : tp("submitCta");

  return (
    <main
      className="auth-page lv-theme"
      /* 关键布局内联，首屏即居中，不等 styled-jsx 注入（消除冷加载时"框先靠左"的 FOUC） */
      style={{ minHeight: "100dvh", display: "grid", justifyItems: "center", alignItems: "safe center" }}
    >
      {/* 极简深邃背景：纯黑系，用变量留口子（首页色调定后改这两行即可） */}
      <div className="auth-bg" aria-hidden />

      <section className="auth-shell">
        {/* 左侧：品牌叙事 + 本周精选世界（真实数据） */}
        <motion.div
          className="auth-copy"
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.55, ease: LV_EASE }}
        >
          <Link href="/" className="auth-back" aria-label={tp("backHome")}>
            <ArrowLeft size={15} />
            <span className="lv-t-meta">{tp("backHome")}</span>
          </Link>

          {/* 一行斜体衬线标语，给世界卡一个引子（克制，不撑高） */}
          <p className="auth-tagline">{tp("showcaseSlogan")}</p>

          <div className="auth-showcase-list">
            {worldsLoading && featuredWorlds.length === 0 ? (
              Array.from({ length: 4 }).map((_, i) => (
                <div key={i} className="showcase-card showcase-skeleton">
                  <div className="card-thumb lv-skel" style={{ borderRadius: "12px" }} />
                  <div className="card-content">
                    <div className="card-header-row">
                      <div className="lv-skel" style={{ height: "15px", width: "40%", borderRadius: "var(--lv-r-pill)" }} />
                      <div className="lv-skel" style={{ height: "15px", width: "25%", borderRadius: "var(--lv-r-pill)" }} />
                    </div>
                    <div className="lv-skel" style={{ height: "18px", width: "30%", borderRadius: "var(--lv-r-pill)", marginBottom: "6px" }} />
                    <div className="lv-skel" style={{ height: "14px", width: "85%", borderRadius: "var(--lv-r-pill)" }} />
                  </div>
                </div>
              ))
            ) : featuredWorlds.length > 0 ? (
              featuredWorlds.map((world, index) => {
                const cover = ossThumb(world.cover_image || world.hero_image, 240);
                const tag = [world.genre, world.era].filter(Boolean).join(" · ") || "未知时空";
                const thumbGradients = [
                  "linear-gradient(135deg, #1e293b 0%, #0f172a 100%)",
                  "linear-gradient(135deg, #14532d 0%, #022c22 100%)",
                  "linear-gradient(135deg, #4c1d95 0%, #1e1b4b 100%)",
                ];
                const radialGradients = [
                  "radial-gradient(circle at 70% 30%, rgba(56, 189, 248, 0.18), transparent 70%)",
                  "radial-gradient(circle at 30% 70%, rgba(34, 197, 94, 0.15), transparent 70%)",
                  "radial-gradient(circle at 50% 50%, rgba(168, 85, 247, 0.15), transparent 75%)",
                ];
                const modeLabel = world.has_script ? "剧本模式" : "自由探索";
                return (
                  <Link href={`/worlds/${world.id}`} key={world.id} className="showcase-card">
                    <div
                      className="card-thumb"
                      style={{
                        backgroundImage: cover ? `url(${cover})` : thumbGradients[index % 3],
                        backgroundSize: "cover",
                        backgroundPosition: "center",
                      }}
                    >
                      {!cover && (
                        <div
                          style={{
                            position: "absolute",
                            inset: 0,
                            background: radialGradients[index % 3],
                            borderRadius: "11px",
                          }}
                        />
                      )}
                    </div>
                    <div className="card-content">
                      <div className="card-header-row">
                        <span className="card-badge">{modeLabel}</span>
                        <span className="card-meta">{tag}</span>
                      </div>
                      <h3 className="lv-t-h3 card-title-text">{world.name}</h3>
                      {world.description && <p className="lv-t-meta card-desc-text">{world.description}</p>}
                    </div>
                  </Link>
                );
              })
            ) : (
              <>
                <div className="showcase-card">
                  <div className="card-thumb state-london" />
                  <div className="card-content">
                    <div className="card-header-row">
                      <span className="card-badge">剧本模式</span>
                      <span className="card-meta">悬疑推理 · 雾都</span>
                    </div>
                    <h3 className="lv-t-h3 card-title-text">雾中巷</h3>
                    <p className="lv-t-meta card-desc-text">
                      在连绵阴雨的伦敦深巷中收集日记残页与线索，拨开迷雾，推演钟楼密室的终极悬案。
                    </p>
                  </div>
                </div>

                <div className="showcase-card">
                  <div className="card-thumb state-jianghu" />
                  <div className="card-content">
                    <div className="card-header-row">
                      <span className="card-badge">自由探索</span>
                      <span className="card-meta">清冷武侠 · 宿命</span>
                    </div>
                    <h3 className="lv-t-h3 card-title-text">剑雨江湖</h3>
                    <p className="lv-t-meta card-desc-text">
                      清冷客栈，竹影微动。你作为解谜之人，每一次对话和抉择都将彻底重构这场江湖恩怨的走向。
                    </p>
                  </div>
                </div>

                <div className="showcase-card">
                  <div className="card-thumb state-wasteland" />
                  <div className="card-content">
                    <div className="card-header-row">
                      <span className="card-badge">剧本模式</span>
                      <span className="card-meta">末日生存 · 机械</span>
                    </div>
                    <h3 className="lv-t-h3 card-title-text">废土沙盒</h3>
                    <p className="lv-t-meta card-desc-text">狂风掠过废土遗迹。指挥并决策 AI 伴侣的行动，在废墟里活下去。</p>
                  </div>
                </div>
              </>
            )}
          </div>
        </motion.div>

        {/* 右侧：玻璃登录卡（表单优先 → OAuth 下沉） */}
        <motion.div
          layout="position"
          className="auth-card"
          initial={{ opacity: 0, y: 16, scale: 0.98 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          transition={{ duration: 0.55, ease: LV_EASE, delay: 0.05 }}
        >
          <div className="auth-card-head">
            <div className="auth-logo" aria-hidden>
              <AuthBrandMark />
            </div>
            <h2 className="lv-t-h2 auth-card-title">InkWild</h2>
          </div>

          {sent ? (
            /* 发送成功 → 整体换成「查收邮箱」确认面板（不再露空密码框） */
            <motion.div
              className="auth-sent"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.35, ease: LV_EASE }}
            >
              <span className="auth-sent-icon" aria-hidden>
                <MailCheck size={26} />
              </span>
              <h3 className="lv-t-h3 auth-sent-title">
                {sent.kind === "register" ? tp("sentVerifyTitle") : tp("sentResetTitle")}
              </h3>
              <p className="lv-t-body auth-sent-body">
                {sent.kind === "register"
                  ? tp("sentVerifyBody", { email: sent.email })
                  : tp("sentResetBody", { email: sent.email })}
              </p>
              <p className="lv-t-meta auth-sent-resend">
                {tp("checkSpam")}{" "}
                <button type="button" className="auth-link-btn" onClick={handleResend} disabled={resendBusy}>
                  {tp("resendCta")}
                </button>
              </p>
              {resendNote && <span className="lv-t-meta auth-sent-note">{resendNote}</span>}
              <button type="button" className="auth-submit-btn auth-sent-back" onClick={() => switchMode("signin")}>
                <span>{tp("backToSigninShort")}</span>
              </button>
            </motion.div>
          ) : (
          <motion.div variants={lvStaggerContainer} initial="hidden" animate="show" className="auth-content-group">
            {/* 反馈 alert（仅错误） */}
            <AnimatePresence mode="wait">
              {apiError && (
                <motion.div
                  key="error"
                  className="auth-status-alert is-error"
                  initial={{ opacity: 0, y: -6 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -6 }}
                  transition={{ duration: 0.2, ease: LV_EASE }}
                >
                  <AlertCircle size={14} style={{ flexShrink: 0, marginTop: 1 }} />
                  <span className="lv-t-meta">{apiError}</span>
                </motion.div>
              )}
            </AnimatePresence>

            {/* 表单（优先位） */}
            <form onSubmit={handleSubmit(onSubmit)} className="auth-form" noValidate>
              {mode === "register" && (
                <motion.div variants={lvStaggerItem} className="auth-field-wrapper">
                  <span className="lv-form-label">{tp("nicknameLabel")}</span>
                  <input
                    type="text"
                    autoComplete="nickname"
                    className="auth-input"
                    placeholder={tp("nicknamePlaceholder")}
                    disabled={submitting}
                    {...register("nickname")}
                  />
                </motion.div>
              )}

              <motion.div variants={lvStaggerItem} className="auth-field-wrapper">
                <span className="lv-form-label">{t("email")}</span>
                <input
                  type="email"
                  autoComplete="email"
                  className={`auth-input ${errors.email ? "has-error" : ""}`}
                  placeholder={t("emailPlaceholder")}
                  disabled={submitting}
                  {...register("email")}
                />
                {errors.email?.message && <em className="auth-error-msg">{errors.email.message}</em>}
              </motion.div>

              {mode !== "forgot" && (
                <motion.div variants={lvStaggerItem} className="auth-field-wrapper">
                  <div className="auth-label-row">
                    <span className="lv-form-label">{t("password")}</span>
                    {mode === "signin" && (
                      <button
                        type="button"
                        className="auth-forgot-trigger lv-t-meta"
                        onClick={() => switchMode("forgot")}
                      >
                        {tp("forgotLink")}
                      </button>
                    )}
                  </div>
                  <div className="auth-input-wrap">
                    <input
                      type={showPassword ? "text" : "password"}
                      autoComplete={mode === "register" ? "new-password" : "current-password"}
                      className={`auth-input has-action ${errors.password ? "has-error" : ""}`}
                      placeholder={mode === "register" ? tp("newPasswordPlaceholder") : t("passwordPlaceholder")}
                      disabled={submitting}
                      {...register("password")}
                    />
                    <button
                      type="button"
                      className="auth-password-toggle"
                      onClick={() => setShowPassword((v) => !v)}
                      aria-label={showPassword ? tp("hidePassword") : tp("showPassword")}
                    >
                      {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                    </button>
                  </div>
                  {errors.password?.message && <em className="auth-error-msg">{errors.password.message}</em>}
                </motion.div>
              )}

              <motion.div variants={lvStaggerItem} className="auth-submit-wrapper">
                <button type="submit" className="auth-submit-btn" disabled={submitting}>
                  <span>{submitting ? tp("submitting") : submitLabel}</span>
                  <ArrowRight size={16} />
                </button>
              </motion.div>
            </form>

            {/* 分隔 + OAuth（下沉位） */}
            <motion.div variants={lvStaggerItem} className="auth-divider" aria-hidden>
              <span className="auth-divider-line" />
              <em className="lv-t-micro">{t("orDivider")}</em>
              <span className="auth-divider-line" />
            </motion.div>

            <motion.div variants={lvStaggerItem} className="auth-oauth-stack">
              <button
                type="button"
                className="auth-oauth-btn"
                disabled={submitting || !GOOGLE_OAUTH_ENABLED}
                aria-disabled={!GOOGLE_OAUTH_ENABLED}
                onClick={() => GOOGLE_OAUTH_ENABLED && startOAuth("google")}
              >
                <GoogleMark />
                <span>{t("loginWithGoogle")}</span>
                {!GOOGLE_OAUTH_ENABLED && <span className="auth-oauth-soon">{tp("googleSoon")}</span>}
              </button>
              <button type="button" className="auth-oauth-btn" disabled={submitting} onClick={() => startOAuth("linuxdo")}>
                <LinuxDoMark />
                <span>{t("loginWithLinuxDo")}</span>
              </button>
            </motion.div>

            {/* 底部模式切换 */}
            <motion.div variants={lvStaggerItem} className="auth-footer-navigator">
              {mode === "forgot" ? (
                <button type="button" className="auth-footer-switcher" onClick={() => switchMode("signin")}>
                  {tp("backToSignin")}
                </button>
              ) : mode === "signin" ? (
                <div className="auth-switch-text lv-t-body">
                  <span>{tp("noAccountPrompt")}</span>
                  <button type="button" className="auth-footer-switcher" onClick={() => switchMode("register")}>
                    {tp("registerTab")}
                  </button>
                </div>
              ) : (
                <div className="auth-switch-text lv-t-body">
                  <span>{tp("haveAccountPrompt")}</span>
                  <button type="button" className="auth-footer-switcher" onClick={() => switchMode("signin")}>
                    {tp("signinTab")}
                  </button>
                </div>
              )}
              {searchParams.get("next") && (
                <span className="lv-t-meta auth-next-path-hint">{tp("nextHint", { path: nextPath })}</span>
              )}
            </motion.div>
          </motion.div>
          )}
        </motion.div>
      </section>

      <style jsx global>{`
        /* ─── 登录页：纯黑双栏，留色调口子 ─── */
        .auth-page {
          --login-canvas: #08080a;
          --login-canvas-deep: #050507;
          --login-bloom: rgba(255, 255, 255, 0.02);
          min-height: 100dvh;
          position: relative;
          overflow-x: hidden;
          color: var(--lv-ink);
          background: var(--login-canvas);
          display: grid;
          justify-items: center;
          align-items: safe center; /* 内容超高时从顶部排，不裁切表单（仍优先居中） */
          padding: calc(28px + env(safe-area-inset-top)) 16px calc(28px + env(safe-area-inset-bottom));
        }

        .auth-bg {
          position: absolute;
          inset: 0;
          background:
            linear-gradient(135deg, var(--login-bloom) 0%, transparent 35%),
            linear-gradient(315deg, rgba(255, 255, 255, 0.015) 0%, transparent 30%),
            linear-gradient(180deg, var(--login-canvas) 0%, var(--login-canvas-deep) 100%);
          z-index: 0;
        }
        .auth-bg::after {
          content: "";
          position: absolute;
          inset: 0;
          background-image: linear-gradient(rgba(255, 255, 255, 0.012) 1px, transparent 1px);
          background-size: 100% 36px;
          mask-image: linear-gradient(180deg, rgba(0, 0, 0, 0.5), transparent 75%);
        }

        .auth-shell {
          position: relative;
          z-index: 1;
          width: min(1140px, 100%);
          display: grid;
          grid-template-columns: minmax(0, 1.2fr) 420px;
          gap: clamp(40px, 6vw, 88px);
          align-items: center;
        }

        /* ─── 左侧展示栏：收紧节奏，列表上提 ─── */
        .auth-copy {
          display: flex;
          flex-direction: column;
          align-items: flex-start;
          gap: var(--lv-s-4);
          min-width: 0;
        }
        .auth-back {
          min-height: 36px;
          display: inline-flex;
          align-items: center;
          gap: 8px;
          color: var(--lv-ink-3);
          text-decoration: none;
          transition: color var(--lv-dur-fast) var(--lv-ease);
        }
        .auth-back:hover {
          color: var(--lv-ink);
        }
        /* 斜体衬线标语：editorial 口吻，一行，给世界卡作引子 */
        .auth-tagline {
          margin: 4px 0 0;
          max-width: 460px;
          font-family: var(--lv-font-serif);
          font-style: italic;
          font-size: var(--lv-t-narrative);
          line-height: 1.4;
          letter-spacing: 0.01em;
          color: var(--lv-ink-2);
        }

        .auth-showcase-list {
          display: flex;
          flex-direction: column;
          gap: 14px;
          width: 100%;
          max-width: 540px;
        }

        .showcase-card {
          display: flex;
          gap: 18px;
          padding: 18px;
          border-radius: var(--lv-r-card);
          border: var(--lv-card-border);
          background: var(--lv-card-bg);
          text-decoration: none;
          color: inherit;
          transition:
            border-color var(--lv-dur-fast) var(--lv-ease),
            background var(--lv-dur-fast) var(--lv-ease),
            transform var(--lv-dur-fast) var(--lv-ease),
            box-shadow var(--lv-dur-fast) var(--lv-ease);
        }
        .showcase-card:hover {
          border: var(--lv-card-border-hover);
          background: var(--lv-card-bg-hover);
          transform: translateY(-3px);
          box-shadow: var(--lv-card-shadow-hover);
        }
        .showcase-skeleton {
          pointer-events: none;
        }

        .card-thumb {
          width: 74px;
          height: 74px;
          border-radius: 12px;
          flex-shrink: 0;
          border: 1px solid rgba(255, 255, 255, 0.06);
          position: relative;
        }
        .state-london {
          background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
        }
        .state-london::after {
          content: "";
          position: absolute;
          inset: 0;
          background: radial-gradient(circle at 70% 30%, rgba(56, 189, 248, 0.18), transparent 70%);
          border-radius: 11px;
        }
        .state-jianghu {
          background: linear-gradient(135deg, #14532d 0%, #022c22 100%);
        }
        .state-jianghu::after {
          content: "";
          position: absolute;
          inset: 0;
          background: radial-gradient(circle at 30% 70%, rgba(34, 197, 94, 0.15), transparent 70%);
          border-radius: 11px;
        }
        .state-wasteland {
          background: linear-gradient(135deg, #4c1d95 0%, #1e1b4b 100%);
        }
        .state-wasteland::after {
          content: "";
          position: absolute;
          inset: 0;
          background: radial-gradient(circle at 50% 50%, rgba(168, 85, 247, 0.15), transparent 75%);
          border-radius: 11px;
        }

        .card-content {
          display: flex;
          flex-direction: column;
          justify-content: center;
          min-width: 0;
          flex: 1;
        }
        .card-header-row {
          display: flex;
          justify-content: space-between;
          align-items: center;
          gap: 8px;
          margin-bottom: 6px;
        }
        .card-badge {
          display: inline-flex;
          align-items: center;
          gap: 4px;
          color: var(--lv-ink-2);
          font-family: var(--lv-font-sans);
          font-size: 11px;
          font-weight: 500;
          background: rgba(255, 255, 255, 0.04);
          border: 1px solid rgba(255, 255, 255, 0.06);
          padding: 2px 8px;
          border-radius: var(--lv-r-pill);
        }
        .card-meta {
          color: var(--lv-ink-3);
          font-size: 11px;
          background: rgba(255, 255, 255, 0.02);
          padding: 2px 8px;
          border-radius: var(--lv-r-pill);
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
          max-width: 140px;
        }
        .card-title-text {
          margin: 0 0 4px 0;
          color: var(--lv-ink);
        }
        .card-desc-text {
          margin: 0;
          color: var(--lv-ink-3);
          line-height: 1.5;
          display: -webkit-box;
          -webkit-line-clamp: 2;
          -webkit-box-orient: vertical;
          overflow: hidden;
        }

        /* ─── 右侧登录卡 ─── */
        .auth-card {
          width: 100%;
          border-radius: var(--lv-r-card);
          border: 1px solid rgba(255, 255, 255, 0.06);
          background: rgba(5, 5, 7, 0.72);
          box-shadow: 0 40px 100px rgba(0, 0, 0, 0.65), inset 0 1px 0 rgba(255, 255, 255, 0.05);
          backdrop-filter: blur(24px) saturate(140%);
          -webkit-backdrop-filter: blur(24px) saturate(140%);
          padding: 28px 28px;
          display: flex;
          flex-direction: column;
          gap: 18px;
        }

        .auth-card-head {
          display: flex;
          flex-direction: column;
          align-items: center;
          text-align: center;
          gap: 10px;
        }
        /* 品牌 app-icon tile：玄黑圆角方块（对齐 experiments/brand 规范） */
        .auth-logo {
          width: 46px;
          height: 46px;
          border-radius: 12px;
          display: grid;
          place-items: center;
          background: #0a0a0c;
          border: 1px solid rgba(255, 255, 255, 0.08);
          box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.05), 0 10px 26px rgba(0, 0, 0, 0.5);
        }
        .auth-card-title {
          margin: 0;
          letter-spacing: -0.01em;
        }

        .auth-content-group {
          display: flex;
          flex-direction: column;
          gap: 16px;
        }

        /* alert */
        .auth-status-alert {
          display: flex;
          align-items: flex-start;
          gap: 8px;
          padding: 10px 14px;
          border-radius: var(--lv-r-card);
          line-height: 1.5;
        }
        .auth-status-alert.is-error {
          color: var(--lv-danger);
          border: 1px solid rgba(239, 130, 118, 0.16);
          background: rgba(239, 130, 118, 0.06);
        }
        .auth-status-alert.is-success {
          color: var(--lv-success);
          border: 1px solid rgba(127, 176, 145, 0.16);
          background: rgba(127, 176, 145, 0.06);
        }

        /* form */
        .auth-form {
          display: flex;
          flex-direction: column;
          gap: 16px;
        }
        .auth-field-wrapper {
          display: flex;
          flex-direction: column;
          gap: 6px;
        }
        .auth-label-row {
          display: flex;
          justify-content: space-between;
          align-items: center;
        }
        .auth-field-wrapper .lv-form-label {
          margin-bottom: 0;
          padding-left: 2px;
        }
        .auth-forgot-trigger {
          border: 0;
          background: transparent;
          color: var(--lv-ink-3);
          cursor: pointer;
          padding: 0;
          transition: color var(--lv-dur-fast) var(--lv-ease);
        }
        .auth-forgot-trigger:hover {
          color: var(--lv-ink-2);
        }

        /* input：对齐 start 页（胶囊 + 柔性填充 + 中性 focus，不沾金/白 ring 冲突） */
        .auth-input {
          width: 100%;
          height: 46px;
          border-radius: var(--lv-r-pill);
          border: 1px solid rgba(255, 255, 255, 0.1);
          background: rgba(255, 255, 255, 0.045);
          color: var(--lv-ink);
          padding: 0 18px;
          font-family: var(--lv-font-sans);
          font-size: 14px;
          outline: none;
          transition:
            border-color var(--lv-dur-fast) var(--lv-ease),
            background var(--lv-dur-fast) var(--lv-ease);
        }
        .auth-input::placeholder {
          color: var(--lv-ink-3);
        }
        .auth-input:focus {
          border-color: rgba(255, 255, 255, 0.22);
          background: rgba(255, 255, 255, 0.07);
        }
        .auth-input.has-error {
          border-color: rgba(239, 130, 118, 0.4);
        }
        .auth-input-wrap {
          position: relative;
          display: block;
        }
        .auth-input.has-action {
          padding-right: 48px;
        }
        .auth-password-toggle {
          position: absolute;
          right: 6px;
          top: 50%;
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
        .auth-password-toggle:hover {
          color: var(--lv-ink);
          background: rgba(255, 255, 255, 0.06);
        }
        .auth-error-msg {
          color: var(--lv-danger);
          font-size: 11px;
          font-style: normal;
          margin-top: 4px;
          padding-left: 4px;
        }

        /* 主 CTA：象牙实心胶囊（对齐 .lv-cta-ivory；颜色写在按钮本身，修复白字白底） */
        .auth-submit-wrapper {
          margin-top: 4px;
        }
        .auth-submit-btn {
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
          transition:
            background var(--lv-dur-fast) var(--lv-ease),
            transform var(--lv-dur-fast) var(--lv-ease),
            box-shadow var(--lv-dur-fast) var(--lv-ease);
          touch-action: manipulation;
        }
        .auth-submit-btn:hover:not(:disabled) {
          background: rgba(245, 242, 235, 1);
          transform: translateY(-1px);
          box-shadow: 0 12px 30px rgba(0, 0, 0, 0.55);
        }
        .auth-submit-btn:active:not(:disabled) {
          transform: translateY(0.5px);
        }
        .auth-submit-btn:disabled {
          opacity: 0.5;
          cursor: not-allowed;
        }

        /* divider */
        .auth-divider {
          display: flex;
          align-items: center;
          gap: 12px;
          text-transform: uppercase;
        }
        .auth-divider-line {
          flex: 1;
          height: 1px;
          background: rgba(255, 255, 255, 0.08);
        }
        .auth-divider em {
          font-style: normal;
          letter-spacing: 0.15em;
          color: var(--lv-ink-3);
        }

        /* OAuth：中性次级按钮（对齐 .lv-btn--on-black 的值，hover 不沾金） */
        .auth-oauth-stack {
          display: flex;
          flex-direction: column;
          gap: 10px;
        }
        .auth-oauth-btn {
          width: 100%;
          min-height: 46px;
          border-radius: var(--lv-r-pill);
          border: 1px solid rgba(255, 255, 255, 0.1);
          background: rgba(255, 255, 255, 0.04);
          box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.06);
          color: var(--lv-ink);
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 10px;
          cursor: pointer;
          font-family: var(--lv-font-sans);
          font-size: 14px;
          font-weight: 500;
          transition:
            background var(--lv-dur-fast) var(--lv-ease),
            border-color var(--lv-dur-fast) var(--lv-ease),
            transform var(--lv-dur-fast) var(--lv-ease);
          touch-action: manipulation;
        }
        .auth-oauth-btn:hover:not(:disabled) {
          background: rgba(255, 255, 255, 0.07);
          border-color: rgba(255, 255, 255, 0.18);
          transform: translateY(-1px);
        }
        .auth-oauth-btn:disabled {
          opacity: 0.5;
          cursor: not-allowed;
        }
        /* Google 暂未开放：右侧「即将开放」小标签 */
        .auth-oauth-soon {
          margin-left: 8px;
          padding: 1px 8px;
          border-radius: var(--lv-r-pill);
          background: rgba(255, 255, 255, 0.06);
          border: 1px solid rgba(255, 255, 255, 0.08);
          color: var(--lv-ink-3);
          font-family: var(--lv-font-mono);
          font-size: 10px;
          letter-spacing: 0.04em;
          white-space: nowrap;
        }

        /* 发送成功确认面板（查收邮箱） */
        .auth-sent {
          display: flex;
          flex-direction: column;
          align-items: center;
          text-align: center;
          gap: 12px;
        }
        .auth-sent-icon {
          width: 52px;
          height: 52px;
          border-radius: 50%;
          display: grid;
          place-items: center;
          border: 1px solid rgba(127, 176, 145, 0.28);
          background: rgba(127, 176, 145, 0.1);
          color: var(--lv-success);
        }
        .auth-sent-title {
          margin: 0;
          color: var(--lv-ink);
        }
        .auth-sent-body {
          margin: 0;
          max-width: 320px;
          line-height: 1.6;
          color: var(--lv-ink-2);
        }
        .auth-sent-resend {
          margin: 4px 0 0;
          color: var(--lv-ink-3);
        }
        .auth-link-btn {
          border: 0;
          background: transparent;
          padding: 0;
          color: var(--lv-ink-2);
          font: inherit;
          cursor: pointer;
          text-decoration: underline;
          text-underline-offset: 3px;
          transition: color var(--lv-dur-fast) var(--lv-ease);
        }
        .auth-link-btn:hover:not(:disabled) {
          color: var(--lv-ink);
        }
        .auth-link-btn:disabled {
          opacity: 0.5;
          cursor: not-allowed;
        }
        .auth-sent-note {
          color: var(--lv-success);
        }
        .auth-sent-back {
          margin-top: 8px;
        }

        /* footer switch */
        .auth-footer-navigator {
          display: flex;
          flex-direction: column;
          align-items: center;
          gap: 8px;
          text-align: center;
        }
        .auth-switch-text {
          color: var(--lv-ink-3);
          display: inline-flex;
          align-items: center;
          gap: 4px;
        }
        .auth-footer-switcher {
          border: 0;
          background: transparent;
          color: var(--lv-ink-2);
          cursor: pointer;
          padding: 0;
          font-family: var(--lv-font-sans);
          font-size: 15px;
          font-weight: 600;
          transition: color var(--lv-dur-fast) var(--lv-ease);
          text-decoration: underline;
          text-underline-offset: 3px;
        }
        .auth-footer-switcher:hover {
          color: var(--lv-ink);
        }
        .auth-next-path-hint {
          color: var(--lv-ink-4);
          font-size: 11px;
        }

        /* ─── 响应式：双栏 → 单栏极简（移动端只剩品牌 + 表单） ─── */
        /* ─── 移动端：单列极简，只剩品牌 + 表单（左侧世界卡整列隐藏） ─── */
        @media (max-width: 900px) {
          .auth-shell {
            grid-template-columns: 1fr;
            gap: 16px;
            max-width: 420px;
          }
          .auth-page {
            align-items: start;
            padding: calc(20px + env(safe-area-inset-top)) 16px calc(24px + env(safe-area-inset-bottom));
          }
          .auth-showcase-list {
            display: none;
          }
          .auth-card {
            padding: 26px 20px;
            box-shadow: 0 16px 40px rgba(0, 0, 0, 0.5);
          }
        }
      `}</style>
    </main>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={null}>
      <LoginPageInner />
    </Suspense>
  );
}
