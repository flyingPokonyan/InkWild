"use client";

import Link from "next/link";
import { Suspense, useEffect, useId, useMemo, useRef, useState } from "react";
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
import { LV_EASE, lvStaggerContainer, lvStaggerItem } from "@/lib/motion";
import { useAuthStore } from "@/stores/auth";

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
  const videoRef = useRef<HTMLVideoElement>(null);
  const emailId = useId();
  const passwordId = useId();
  const nicknameId = useId();

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;

    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
    const compactViewport = window.matchMedia("(max-width: 900px)");
    const applyMotionPreference = () => {
      video.playbackRate = 0.5;
      if (reduceMotion.matches || compactViewport.matches) {
        video.pause();
      } else {
        void video.play().catch(() => {});
      }
    };

    applyMotionPreference();
    reduceMotion.addEventListener("change", applyMotionPreference);
    compactViewport.addEventListener("change", applyMotionPreference);
    return () => {
      reduceMotion.removeEventListener("change", applyMotionPreference);
      compactViewport.removeEventListener("change", applyMotionPreference);
    };
  }, []);
  const searchParams = useSearchParams();
  const t = useTranslations("auth");
  const tp = useTranslations("loginPage");

  const login = useAuthStore((s) => s.login);
  const isLoading = useAuthStore((s) => s.isLoading);
  const hasLoaded = useAuthStore((s) => s.hasLoaded);
  const user = useAuthStore((s) => s.user);



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

  // OAuth 注册被放量闸门拦截时回跳带 ?error=signup_closed
  useEffect(() => {
    if (searchParams.get("error") === "signup_closed") {
      setApiError(tp("signupClosed"));
    }
  }, [searchParams, tp]);

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
      style={{ minHeight: "100dvh" }}
    >
      <div className="auth-split-layout">
        {/* 全屏底层画卷（支持视频播放） */}
        <div className="auth-visual-bg" aria-hidden>
          <video
            ref={videoRef}
            loop
            muted
            playsInline
            preload="metadata"
            poster="/hero-sky-poster.jpg"
            className="auth-visual-video"
          >
            <source src="/hero-sky-1440.mp4" type="video/mp4" />
          </video>
        </div>

        {/* 左侧：仅仅作为占位和文字容器，背景透明 */}
        <section className="auth-split-visual">
          <div className="auth-visual-content">
             <div className="auth-logo-large">
               <AuthBrandMark />
             </div>
             <h1 className="lv-t-h1 auth-visual-title">InkWild</h1>
             <p className="auth-tagline">{tp("visualTagline")}</p>
          </div>
        </section>

        {/* 右侧：通顶深色毛玻璃，盖在画卷上方 */}
        <section className="auth-split-form">
          <div className="auth-form-container">
            <div className="auth-header-actions">
              <Link href="/" className="auth-back" aria-label={tp("backHome")}>
                <ArrowLeft size={15} />
                <span className="lv-t-meta">{tp("backHome")}</span>
              </Link>
            </div>

            <div className="auth-mobile-brand">
              <div className="auth-logo-mobile" aria-hidden>
                <AuthBrandMark />
              </div>
              <h1 className="lv-t-h2 auth-mobile-title">InkWild</h1>
              <p className="auth-mobile-tagline">{tp("visualTagline")}</p>
            </div>

            <motion.div
              layout="position"
              className="auth-form-body"
              initial={{ opacity: 0, x: 16 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.55, ease: LV_EASE, delay: 0.05 }}
            >

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
                  <label className="lv-form-label" htmlFor={nicknameId}>
                    {tp("nicknameLabel")}
                  </label>
                  <input
                    id={nicknameId}
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
                <label className="lv-form-label" htmlFor={emailId}>
                  {t("email")}
                </label>
                <input
                  id={emailId}
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
                    <label className="lv-form-label" htmlFor={passwordId}>
                      {t("password")}
                    </label>
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
                      id={passwordId}
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
          </div>
        </section>
      </div>

      <style jsx global>{`
        /* ─── 登录页：居中单卡 + 氛围底（非纯黑） ─── */
        .auth-page {
          --login-canvas: #08080a;
          min-height: 100dvh;
          position: relative;
          overflow-x: hidden;
          color: var(--lv-ink);
          display: flex;
          flex-direction: column;
        }

        .auth-split-layout {
          display: flex;
          width: 100%;
          min-height: 100dvh;
          position: relative;
        }

        /* 全屏底层画卷 */
        .auth-visual-bg {
          position: absolute;
          inset: 0;
          z-index: 0;
          background: #000;
        }
        .auth-visual-video {
          width: 100%;
          height: 100%;
          object-fit: cover;
        }
        /* 给全屏画卷加一层暗色遮罩，保证整体暗黑调性 */
        .auth-visual-bg::after {
          content: "";
          position: absolute;
          inset: 0;
          background: rgba(0, 0, 0, 0.2);
        }

        /* 左侧品牌视觉区 (透明，只作为容器) */
        .auth-split-visual {
          flex: 1;
          position: relative;
          z-index: 1;
          display: flex;
          align-items: center;
          justify-content: center;
          background: transparent;
        }
        .auth-visual-content {
          display: flex;
          flex-direction: column;
          align-items: center;
          text-align: center;
          gap: 16px;
        }
        .auth-logo-large {
          width: 64px;
          height: 64px;
          border-radius: 16px;
          display: grid;
          place-items: center;
          background: rgba(10, 10, 12, 0.8);
          backdrop-filter: blur(20px);
          border: 1px solid rgba(255, 255, 255, 0.15);
          box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.1), 0 16px 32px rgba(0, 0, 0, 0.5);
          margin-bottom: 8px;
        }
        .auth-visual-title {
          margin: 0;
          letter-spacing: 0;
          color: #fff;
          text-shadow: 0 4px 12px rgba(0,0,0,0.5);
        }
        .auth-tagline {
          margin: 0;
          max-width: 420px;
          font-family: var(--lv-font-serif);
          font-style: italic;
          font-size: var(--lv-t-h3);
          color: rgba(255, 255, 255, 0.8);
          letter-spacing: 0;
          text-shadow: 0 2px 8px rgba(0,0,0,0.5);
        }

        /* 右侧通顶毛玻璃表单区 - 带有无缝渐现遮罩 */
        .auth-split-form {
          flex: 0 0 clamp(460px, 34vw, 560px);
          position: relative;
          z-index: 2;
          display: flex;
          align-items: center;
          justify-content: center;
          /* 左侧 padding 留出 60px，确保表单内容完全处于 40px 渐变区之后（即完全毛玻璃的区域） */
          padding: calc(24px + env(safe-area-inset-top)) 40px calc(24px + env(safe-area-inset-bottom)) 60px;
        }

        .auth-split-form::before {
          content: "";
          position: absolute;
          inset: 0;
          z-index: -1;
          background: rgba(5, 5, 7, 0.85);
          backdrop-filter: blur(16px) saturate(120%);
          -webkit-backdrop-filter: blur(16px) saturate(120%);
          /* 从左至右仅 40px 的平滑渐显，避免影响到输入框 */
          -webkit-mask-image: linear-gradient(to right, transparent, black 40px);
          mask-image: linear-gradient(to right, transparent, black 40px);
        }

        .auth-form-container {
          width: 100%;
          max-width: 400px;
          display: flex;
          flex-direction: column;
          gap: 40px;
        }

        .auth-header-actions {
          display: flex;
          justify-content: flex-start;
        }
        .auth-back {
          min-height: 36px;
          display: inline-flex;
          align-items: center;
          gap: 8px;
          color: rgba(255, 255, 255, 0.5);
          text-decoration: none;
          transition: color var(--lv-dur-fast) var(--lv-ease);
        }
        .auth-back:hover {
          color: rgba(255, 255, 255, 0.9);
        }

        .auth-mobile-brand {
          display: none;
        }

        .auth-form-body {
          display: flex;
          flex-direction: column;
          gap: 20px;
          width: 100%;
        }

        .auth-content-group {
          display: flex;
          flex-direction: column;
          gap: 24px;
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

        /* ─── 移动端适配 ─── */
        @media (max-width: 900px) {
          .auth-page {
            display: grid;
            place-items: center;
            background: var(--login-canvas);
            padding: calc(20px + env(safe-area-inset-top)) 16px calc(24px + env(safe-area-inset-bottom));
          }
          .auth-split-layout {
            display: block;
            width: min(420px, 100%);
            min-height: auto;
          }
          .auth-visual-bg {
            position: fixed;
            background:
              linear-gradient(135deg, rgba(255, 255, 255, 0.02) 0%, transparent 35%),
              linear-gradient(180deg, #08080a 0%, #050507 100%);
          }
          .auth-visual-video {
            display: none;
          }
          .auth-visual-bg::after {
            background-image: linear-gradient(rgba(255, 255, 255, 0.012) 1px, transparent 1px);
            background-size: 100% 36px;
            mask-image: linear-gradient(180deg, rgba(0, 0, 0, 0.5), transparent 75%);
          }
          .auth-split-visual {
            display: none;
          }
          .auth-split-form {
            width: 100%;
            display: block;
            flex: none;
            padding: 0;
          }
          .auth-split-form::before {
            border-radius: var(--lv-r-card);
            border: 1px solid rgba(255, 255, 255, 0.06);
            background: rgba(5, 5, 7, 0.72);
            box-shadow: 0 16px 40px rgba(0, 0, 0, 0.5), inset 0 1px 0 rgba(255, 255, 255, 0.05);
            backdrop-filter: blur(24px) saturate(140%);
            -webkit-backdrop-filter: blur(24px) saturate(140%);
            -webkit-mask-image: none;
            mask-image: none;
          }
          .auth-form-container {
            max-width: none;
            gap: 18px;
            padding: 26px 20px;
          }
          .auth-mobile-brand {
            display: flex;
            flex-direction: column;
            align-items: center;
            text-align: center;
            gap: 8px;
          }
          .auth-logo-mobile {
            width: 46px;
            height: 46px;
            border-radius: 12px;
            display: grid;
            place-items: center;
            background: #0a0a0c;
            border: 1px solid rgba(255, 255, 255, 0.08);
            box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.05), 0 10px 26px rgba(0, 0, 0, 0.5);
          }
          .auth-mobile-title {
            margin: 0;
            letter-spacing: 0;
          }
          .auth-mobile-tagline {
            margin: 0;
            max-width: 280px;
            color: var(--lv-ink-2);
            font-family: var(--lv-font-serif);
            font-style: italic;
            font-size: 14px;
            line-height: 1.45;
            letter-spacing: 0;
          }
          .auth-form-body {
            gap: 18px;
          }
          .auth-content-group {
            gap: 16px;
          }
          .auth-form {
            gap: 14px;
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
