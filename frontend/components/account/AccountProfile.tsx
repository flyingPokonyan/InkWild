"use client";

import { useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { Camera, Check, ChevronRight, Loader2, Pencil, X } from "lucide-react";

import { ChangePasswordForm } from "@/components/account/ChangePasswordForm";
import { Modal } from "@/components/ui/Modal";
import { updateProfile, uploadAvatar } from "@/lib/auth-api";
import { readAsDataUrl, validateImageFile } from "@/lib/avatar";
import { useAuthStore } from "@/stores/auth";

const KNOWN_PROVIDERS = new Set(["password", "email", "linuxdo", "phone", "google", "github"]);

/**
 * PC 账户中心「账户」内容：资料（头像/昵称可编辑，邮箱/登录方式只读）+ 安全（改密码）。
 */
export function AccountProfile() {
  const t = useTranslations("account");
  const user = useAuthStore((s) => s.user);
  const setUser = useAuthStore((s) => s.setUser);

  const fileRef = useRef<HTMLInputElement>(null);
  const [avatarBusy, setAvatarBusy] = useState(false);
  const [avatarError, setAvatarError] = useState<string | null>(null);

  const [editingNick, setEditingNick] = useState(false);
  const [nickDraft, setNickDraft] = useState("");
  const [nickBusy, setNickBusy] = useState(false);
  const [nickError, setNickError] = useState<string | null>(null);
  const [pwOpen, setPwOpen] = useState(false);

  const nickname = user?.nickname?.trim() || "";
  const email = user?.identities.find((i) => i.email)?.email ?? t("empty");
  const providers = user?.identities ?? [];
  const hasPassword = providers.some((i) => i.provider === "password");
  const loginMethods =
    providers.length > 0
      ? providers.map((i) => (KNOWN_PROVIDERS.has(i.provider) ? t(`provider.${i.provider}`) : i.provider)).join(" · ")
      : t("empty");
  const initial = (nickname || email)[0]?.toUpperCase() ?? "玩";

  const onPickAvatar = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = ""; // 允许重复选同一张
    if (!file) return;
    const bad = validateImageFile(file);
    if (bad) {
      setAvatarError(bad === "size" ? t("avatarTooLarge") : t("avatarBadType"));
      return;
    }
    setAvatarBusy(true);
    setAvatarError(null);
    try {
      const dataUrl = await readAsDataUrl(file);
      const dto = await uploadAvatar(dataUrl);
      setUser(dto);
    } catch (err) {
      setAvatarError(err instanceof Error ? err.message : t("updateFailed"));
    } finally {
      setAvatarBusy(false);
    }
  };

  const startEditNick = () => {
    setNickDraft(nickname);
    setNickError(null);
    setEditingNick(true);
  };

  const saveNick = async () => {
    const value = nickDraft.trim();
    if (value.length < 1 || value.length > 50) {
      setNickError(t("nicknameInvalid"));
      return;
    }
    if (value === nickname) {
      setEditingNick(false);
      return;
    }
    setNickBusy(true);
    setNickError(null);
    try {
      const dto = await updateProfile({ nickname: value });
      setUser(dto);
      setEditingNick(false);
    } catch (err) {
      setNickError(err instanceof Error ? err.message : t("updateFailed"));
    } finally {
      setNickBusy(false);
    }
  };

  return (
    <div className="apf">
      <h1 className="apf-title">{t("title")}</h1>

      {/* 头像 */}
      <div className="apf-card apf-avatar-card">
        <div className="apf-avatar" aria-hidden>
          {user?.avatar_url ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={user.avatar_url} alt="" />
          ) : (
            <span>{initial}</span>
          )}
          {avatarBusy && (
            <span className="apf-avatar-busy">
              <Loader2 size={18} />
            </span>
          )}
        </div>
        <div className="apf-avatar-meta">
          <button type="button" className="apf-avatar-btn" onClick={() => fileRef.current?.click()} disabled={avatarBusy}>
            <Camera size={14} />
            {avatarBusy ? t("uploading") : t("editAvatar")}
          </button>
          {avatarError ? (
            <span className="apf-avatar-err">{avatarError}</span>
          ) : (
            <span className="apf-avatar-hint">{t("avatarHint")}</span>
          )}
        </div>
        <input
          ref={fileRef}
          type="file"
          accept="image/png,image/jpeg,image/webp"
          hidden
          onChange={(e) => void onPickAvatar(e)}
        />
      </div>

      {/* 资料 */}
      <div className="apf-card">
        <div className="lv-t-caps apf-card-head">{t("profileCard")}</div>

        <div className="apf-row">
          <span className="apf-row-label">{t("nickname")}</span>
          {editingNick ? (
            <span className="apf-edit">
              <input
                className="apf-edit-input"
                value={nickDraft}
                autoFocus
                maxLength={50}
                disabled={nickBusy}
                placeholder={t("nicknamePlaceholder")}
                onChange={(e) => setNickDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") void saveNick();
                  if (e.key === "Escape") setEditingNick(false);
                }}
              />
              <button
                type="button"
                className="apf-icon-btn"
                onClick={() => void saveNick()}
                disabled={nickBusy}
                aria-label={t("save")}
              >
                {nickBusy ? <Loader2 size={15} className="apf-spin" /> : <Check size={15} />}
              </button>
              <button
                type="button"
                className="apf-icon-btn"
                onClick={() => setEditingNick(false)}
                disabled={nickBusy}
                aria-label={t("cancel")}
              >
                <X size={15} />
              </button>
            </span>
          ) : (
            <span className="apf-row-edit">
              <span className="apf-row-value">{nickname || t("empty")}</span>
              <button type="button" className="apf-icon-btn" onClick={startEditNick} aria-label={t("edit")}>
                <Pencil size={14} />
              </button>
            </span>
          )}
        </div>
        {nickError && (
          <div className="apf-row-error-line">
            <span className="apf-inline-err">{nickError}</span>
          </div>
        )}

        <Row label={t("email")} value={email} />
        <Row label={t("loginMethods")} value={loginMethods} last />
      </div>

      {/* 安全 */}
      <div className="apf-card">
        <div className="lv-t-caps apf-card-head">{t("securityCard")}</div>
        {hasPassword ? (
          <button type="button" className="apf-row apf-row-action" onClick={() => setPwOpen(true)}>
            <span className="apf-row-label">{t("changePassword")}</span>
            <ChevronRight size={16} className="apf-row-chevron" />
          </button>
        ) : (
          // 第三方登录（无密码身份）：只给提示，不展示密码表单
          <div className="apf-row">
            <span className="apf-row-label">{t("changePassword")}</span>
            <span className="apf-row-hint">{t("noPasswordSet")}</span>
          </div>
        )}
        <Row label={t("deleteAccount")} soon={t("soon")} last />
      </div>

      <Modal open={pwOpen} onClose={() => setPwOpen(false)} title={t("changePassword")} maxWidth={420}>
        <ChangePasswordForm hasPassword={hasPassword} onDone={() => setPwOpen(false)} />
      </Modal>

      <style jsx global>{`
        .apf {
          display: flex;
          flex-direction: column;
          gap: 22px;
        }
        .apf-title {
          margin: 0;
          font-family: var(--lv-font-serif);
          font-size: clamp(26px, 3vw, 32px);
          font-weight: 500;
          letter-spacing: -0.01em;
          color: var(--lv-ink);
        }
        .apf-card {
          border-radius: var(--lv-r-card);
          border: 1px solid var(--lv-line);
          background: rgba(255, 255, 255, 0.02);
          padding: 6px 18px;
        }
        .apf-card-head {
          color: var(--lv-ink-3);
          padding: 16px 0 10px;
        }
        .apf-avatar-card {
          display: flex;
          align-items: center;
          gap: 18px;
          padding: 18px;
        }
        .apf-avatar {
          position: relative;
          width: 64px;
          height: 64px;
          border-radius: 50%;
          overflow: hidden;
          flex-shrink: 0;
          display: grid;
          place-items: center;
          background: rgba(245, 242, 235, 0.08);
          border: 1px solid var(--lv-line-2);
        }
        .apf-avatar img {
          width: 100%;
          height: 100%;
          object-fit: cover;
        }
        .apf-avatar span {
          font-family: var(--lv-font-serif);
          font-size: 26px;
          font-weight: 500;
          color: var(--lv-ink);
        }
        .apf-avatar-busy {
          position: absolute;
          inset: 0;
          display: grid;
          place-items: center;
          background: rgba(5, 5, 7, 0.55);
          color: var(--lv-ink);
        }
        .apf-avatar-busy svg {
          animation: apf-spin 1s linear infinite;
        }
        .apf-avatar-meta {
          display: flex;
          flex-direction: column;
          gap: 6px;
          min-width: 0;
        }
        .apf-avatar-btn {
          display: inline-flex;
          align-items: center;
          gap: 7px;
          align-self: flex-start;
          height: 36px;
          padding: 0 14px;
          border-radius: var(--lv-r-pill);
          border: 1px solid var(--lv-line-2);
          background: rgba(255, 255, 255, 0.04);
          color: var(--lv-ink);
          font-size: var(--lv-t-compact);
          font-weight: 500;
          cursor: pointer;
          transition: background var(--lv-dur-fast) var(--lv-ease), border-color var(--lv-dur-fast) var(--lv-ease);
        }
        .apf-avatar-btn:hover:not(:disabled) {
          background: rgba(255, 255, 255, 0.07);
          border-color: rgba(255, 255, 255, 0.18);
        }
        .apf-avatar-btn:disabled {
          opacity: 0.6;
          cursor: not-allowed;
        }
        .apf-avatar-hint {
          color: var(--lv-ink-4);
          font-size: var(--lv-t-meta);
        }
        .apf-avatar-err {
          color: var(--lv-danger);
          font-size: var(--lv-t-meta);
        }
        .apf-row {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 16px;
          padding: 15px 0;
          border-top: 1px solid var(--lv-line);
          min-height: 56px;
        }
        .apf-row-label {
          color: var(--lv-ink-3);
          font-size: var(--lv-t-compact);
          flex-shrink: 0;
        }
        .apf-row-edit {
          display: inline-flex;
          align-items: center;
          gap: 8px;
          min-width: 0;
        }
        .apf-row-value {
          color: var(--lv-ink);
          font-size: var(--lv-t-compact);
          text-align: right;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }
        .apf-row-soon {
          font-family: var(--lv-font-mono);
          font-size: 10px;
          letter-spacing: 0.1em;
          color: var(--lv-ink-4);
        }
        .apf-edit {
          display: inline-flex;
          align-items: center;
          gap: 6px;
        }
        .apf-edit-input {
          height: 40px;
          width: 200px;
          max-width: 48vw;
          border-radius: var(--lv-r-pill);
          border: 1px solid rgba(255, 255, 255, 0.10);
          background: rgba(255, 255, 255, 0.045);
          color: var(--lv-ink);
          padding: 0 16px;
          font-family: var(--lv-font-sans);
          font-size: 13px;
          outline: none;
          transition:
            border-color var(--lv-dur-fast) var(--lv-ease),
            background var(--lv-dur-fast) var(--lv-ease);
        }
        .apf-edit-input::placeholder {
          color: var(--lv-ink-3);
        }
        .apf-edit-input:focus {
          border-color: rgba(255, 255, 255, 0.22);
          background: rgba(255, 255, 255, 0.07);
        }
        .apf-icon-btn {
          width: 32px;
          height: 32px;
          flex-shrink: 0;
          border: 1px solid var(--lv-line-2);
          border-radius: 50%;
          background: rgba(255, 255, 255, 0.04);
          color: var(--lv-ink-2);
          display: grid;
          place-items: center;
          cursor: pointer;
          transition: color var(--lv-dur-fast) var(--lv-ease), background var(--lv-dur-fast) var(--lv-ease);
        }
        .apf-icon-btn:hover:not(:disabled) {
          color: var(--lv-ink);
          background: rgba(255, 255, 255, 0.08);
        }
        .apf-icon-btn:disabled {
          opacity: 0.5;
          cursor: not-allowed;
        }
        .apf-spin {
          animation: apf-spin 1s linear infinite;
        }
        .apf-row-error-line {
          display: flex;
          justify-content: flex-end;
          padding-bottom: 8px;
        }
        .apf-inline-err {
          color: var(--lv-danger);
          font-size: 11px;
        }
        /* 修改密码：一行入口（点开弹层），不再内联铺密码框 */
        .apf-row-action {
          width: 100%;
          background: transparent;
          border: 0;
          border-top: 1px solid var(--lv-line);
          color: inherit;
          font: inherit;
          text-align: left;
          cursor: pointer;
        }
        .apf-row-chevron {
          color: var(--lv-ink-3);
          flex-shrink: 0;
          transition: color var(--lv-dur-fast) var(--lv-ease), transform var(--lv-dur-fast) var(--lv-ease);
        }
        .apf-row-action:hover .apf-row-chevron {
          color: var(--lv-ink);
          transform: translateX(2px);
        }
        .apf-row-hint {
          color: var(--lv-ink-3);
          font-size: var(--lv-t-meta);
          text-align: right;
          line-height: 1.5;
          max-width: 62%;
        }
        @keyframes apf-spin {
          to {
            transform: rotate(360deg);
          }
        }
      `}</style>
    </div>
  );
}

function Row({ label, value, soon, last }: { label: string; value?: string; soon?: string; last?: boolean }) {
  return (
    <div className="apf-row" style={last ? { paddingBottom: 16 } : undefined}>
      <span className="apf-row-label">{label}</span>
      {soon ? <span className="apf-row-soon">{soon}</span> : <span className="apf-row-value">{value}</span>}
    </div>
  );
}
