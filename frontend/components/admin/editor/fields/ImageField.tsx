"use client";

import * as Popover from "@radix-ui/react-popover";
import { Link2, Loader2, Pencil, Sparkles, Upload } from "lucide-react";
import { useTranslations } from "next-intl";
import { type CSSProperties, type ReactNode, useEffect, useId, useRef, useState } from "react";

import { MobileSheet } from "@/components/ui/MobileSheet";
import { AVATAR_TYPES, readAsDataUrl } from "@/lib/avatar";
import { useIsMobile } from "@/lib/use-viewport";
import {
  getScriptDraftImagePrompt,
  getWorldDraftImagePrompt,
  regenerateScriptDraftImage,
  regenerateWorldDraftImage,
  uploadWorkshopImage,
} from "@/lib/workshop-api";

const COVER_MAX_BYTES = 5 * 1024 * 1024;
const AVATAR_MAX_BYTES = 2 * 1024 * 1024;

export interface ImageFieldProps {
  url: string | null | undefined;
  onChange: (url: string | null) => void;
  /** cover = 矩形展示框；avatar = 小方缩览 */
  variant: "cover" | "avatar";
  /** cover 下方 caps 标签 */
  label?: string;
  /** cover 比例，如 "21 / 9" / "3 / 2"。默认 3 / 2 */
  aspectRatio?: string;
  draftId: string;
  draftKind: "world" | "script";
  /** world: "hero" | "cover" | "avatar:<角色名>"；script 忽略（恒 cover） */
  regenTarget: string;
  /** 重抽前先 flush 自动保存，确保后端读到最新字段 */
  beforeRegenerate?: () => Promise<void>;
}

/**
 * 草稿图片控件：静息态保持干净（封面框 / 头像缩览），右下角一个极克制的常驻入口；
 * 点开后桌面用 Popover、移动用 MobileSheet 唤出动作层（上传 / 重抽 / 粘贴链接）。
 * 样式全部走 .lv-theme 下的局部 <style jsx global>，对齐全站 token 与 start 页输入框。
 */
export function ImageField(props: ImageFieldProps) {
  const { url, variant, label, aspectRatio = "3 / 2" } = props;
  const t = useTranslations("admin.editor.image");
  const isMobile = useIsMobile();
  const [open, setOpen] = useState(false);

  // mobile: badge 自带 onClick 开 sheet。desktop: Popover.Trigger 负责开合，
  // badge 不能再 setOpen，否则两个 handler 打架（Radix Slot 会合并）。
  const renderBadge = (onClick?: () => void) => (
    <button type="button" aria-label={t("edit")} onClick={onClick} className="lv-imgfield-badge">
      <Pencil size={13} strokeWidth={2} />
    </button>
  );

  const badge = isMobile ? (
    renderBadge(() => setOpen(true))
  ) : (
    <Popover.Trigger asChild>{renderBadge()}</Popover.Trigger>
  );

  const frame =
    variant === "cover" ? (
      <figure style={{ display: "flex", flexDirection: "column", gap: 6, margin: 0, minWidth: 0 }}>
        <div style={{ ...coverFrameStyle, aspectRatio }}>
          <ImagePreview url={url} alt={label ?? ""} noImageLabel={t("noImage")} />
          {badge}
        </div>
        {label ? (
          <figcaption className="lv-t-caps" style={{ color: "var(--lv-ink-3)", textAlign: "center" }}>
            {label}
          </figcaption>
        ) : null}
      </figure>
    ) : (
      <div style={{ position: "relative", width: 76, height: 76 }}>
        <div style={avatarFrameStyle}>
          <ImagePreview url={url} alt={label ?? ""} noImageLabel="" />
        </div>
        {badge}
      </div>
    );

  if (isMobile) {
    return (
      <>
        {frame}
        <MobileSheet open={open} onClose={() => setOpen(false)} title={t("title")}>
          <div style={{ padding: "4px 20px 24px" }}>
            <ActionPanel {...props} onDone={() => setOpen(false)} />
          </div>
        </MobileSheet>
        <ImageFieldStyles />
      </>
    );
  }

  return (
    <Popover.Root open={open} onOpenChange={setOpen}>
      {frame}
      <Popover.Portal>
        <Popover.Content
          align="end"
          sideOffset={8}
          className="lv-imgfield-pop"
          onOpenAutoFocus={(e) => e.preventDefault()}
        >
          <ActionPanel {...props} onDone={() => setOpen(false)} />
        </Popover.Content>
      </Popover.Portal>
      <ImageFieldStyles />
    </Popover.Root>
  );
}

function ImagePreview({
  url,
  alt,
  noImageLabel,
}: {
  url: string | null | undefined;
  alt: string;
  noImageLabel: string;
}) {
  if (url) {
    return (
      // eslint-disable-next-line @next/next/no-img-element
      <img
        src={url}
        alt={alt}
        style={{ width: "100%", height: "100%", objectFit: "cover", display: "block" }}
      />
    );
  }
  return (
    <div
      className="lv-t-caps"
      style={{ position: "absolute", inset: 0, display: "grid", placeItems: "center", color: "var(--lv-ink-4)" }}
    >
      {noImageLabel}
    </div>
  );
}

type Mode = "menu" | "regen" | "link";
type Busy = null | "upload" | "regen";

function ActionPanel({
  url,
  onChange,
  variant,
  draftId,
  draftKind,
  regenTarget,
  beforeRegenerate,
  onDone,
}: ImageFieldProps & { onDone: () => void }) {
  const t = useTranslations("admin.editor.image");
  const [mode, setMode] = useState<Mode>("menu");
  const [busy, setBusy] = useState<Busy>(null);
  const [error, setError] = useState<string | null>(null);
  const [prompt, setPrompt] = useState("");
  const [promptLoading, setPromptLoading] = useState(false);
  const [link, setLink] = useState(url ?? "");
  const fileRef = useRef<HTMLInputElement>(null);
  const fileInputId = useId();

  useEffect(() => {
    if (mode !== "regen" || prompt) return;
    let cancelled = false;
    setPromptLoading(true);
    setError(null);
    void (async () => {
      try {
        if (beforeRegenerate) await beforeRegenerate();
        const next =
          draftKind === "world"
            ? await getWorldDraftImagePrompt(draftId, regenTarget)
            : await getScriptDraftImagePrompt(draftId);
        if (!cancelled) setPrompt(next);
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : t("promptLoadFailed"));
        }
      } finally {
        if (!cancelled) setPromptLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [beforeRegenerate, draftId, draftKind, mode, prompt, regenTarget, t]);

  const onPickFile = async (file: File | undefined) => {
    if (!file) return;
    setError(null);
    if (!AVATAR_TYPES.includes(file.type)) {
      setError(t("errorType"));
      return;
    }
    const maxBytes = variant === "avatar" ? AVATAR_MAX_BYTES : COVER_MAX_BYTES;
    if (file.size > maxBytes) {
      setError(t(variant === "avatar" ? "errorSizeAvatar" : "errorSizeCover"));
      return;
    }
    setBusy("upload");
    try {
      const dataUrl = await readAsDataUrl(file);
      const next = await uploadWorkshopImage(dataUrl, variant === "avatar" ? "avatar" : "cover");
      onChange(next);
      onDone();
    } catch (e) {
      setError(e instanceof Error ? e.message : t("errorGeneric"));
    } finally {
      setBusy(null);
    }
  };

  const doRegen = async () => {
    setError(null);
    setBusy("regen");
    try {
      if (beforeRegenerate) await beforeRegenerate();
      const next =
        draftKind === "world"
          ? await regenerateWorldDraftImage(draftId, regenTarget, prompt.trim())
          : await regenerateScriptDraftImage(draftId, prompt.trim());
      onChange(next);
      onDone();
    } catch (e) {
      setError(e instanceof Error ? e.message : t("errorGeneric"));
    } finally {
      setBusy(null);
    }
  };

  const applyLink = () => {
    onChange(link.trim() || null);
    onDone();
  };

  const disabled = busy !== null;
  const regenDisabled = disabled || promptLoading;

  return (
    <div className="lv-imgfield-body">
      {busy ? (
        <div className="lv-imgfield-busy">
          <Loader2 size={20} style={{ animation: "lv-spin 1.2s linear infinite" }} />
          <span className="lv-t-meta">{t(busy === "upload" ? "uploading" : "regenerating")}</span>
        </div>
      ) : null}

      <input
        ref={fileRef}
        id={fileInputId}
        type="file"
        accept="image/png,image/jpeg,image/webp"
        hidden
        onChange={(e) => void onPickFile(e.target.files?.[0])}
      />

      {mode === "menu" ? (
        <>
          <ActionRow icon={<Upload size={16} strokeWidth={1.75} />} label={t("upload")} onClick={() => fileRef.current?.click()} disabled={disabled} />
          <ActionRow icon={<Sparkles size={16} strokeWidth={1.75} />} label={t("regenerate")} onClick={() => setMode("regen")} disabled={disabled} accent />
          <ActionRow icon={<Link2 size={16} strokeWidth={1.75} />} label={t("pasteLink")} onClick={() => setMode("link")} disabled={disabled} muted />
        </>
      ) : null}

      {mode === "regen" ? (
        <>
          <div className="lv-t-caps" style={{ color: "var(--lv-ink-3)", padding: "2px 2px 0" }}>
            {t("promptLabel")}
          </div>
          <textarea
            className="lv-imgfield-textarea"
            rows={7}
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            placeholder={promptLoading ? t("promptLoading") : t("regeneratePromptPlaceholder")}
          />
          <div className="lv-imgfield-actions">
            <button type="button" className="lv-imgfield-ghost" onClick={() => setMode("menu")} disabled={disabled}>
              {t("back")}
            </button>
            <button type="button" className="lv-imgfield-cta" onClick={() => void doRegen()} disabled={regenDisabled}>
              {t("regenerateCta")}
            </button>
          </div>
        </>
      ) : null}

      {mode === "link" ? (
        <>
          <input
            className="lv-imgfield-input"
            value={link}
            onChange={(e) => setLink(e.target.value)}
            placeholder={t("pasteLinkPlaceholder")}
          />
          <div className="lv-imgfield-actions">
            <button type="button" className="lv-imgfield-ghost" onClick={() => setMode("menu")} disabled={disabled}>
              {t("back")}
            </button>
            <button type="button" className="lv-imgfield-cta" onClick={applyLink} disabled={disabled}>
              {t("confirm")}
            </button>
          </div>
        </>
      ) : null}

      {error ? (
        <p className="lv-t-meta lv-imgfield-error" role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}

function ActionRow({
  icon,
  label,
  onClick,
  disabled,
  muted,
  accent,
}: {
  icon: ReactNode;
  label: string;
  onClick: () => void;
  disabled?: boolean;
  muted?: boolean;
  accent?: boolean;
}) {
  const cls = ["lv-imgfield-row", muted ? "is-muted" : "", accent ? "is-accent" : ""]
    .filter(Boolean)
    .join(" ");
  return (
    <button type="button" onClick={onClick} disabled={disabled} className={cls}>
      <span className="lv-imgfield-row-icon">{icon}</span>
      {label}
    </button>
  );
}

// ---------------------------------------------------------------------------
// frame styles (mirror CoverFrame) — kept inline; everything else via <style jsx>
// ---------------------------------------------------------------------------

const coverFrameStyle: CSSProperties = {
  width: "100%",
  background: "var(--lv-bg-stage)",
  border: "1px solid rgba(245, 242, 235, 0.08)",
  boxShadow: "inset 0 1px 0 rgba(245, 242, 235, 0.04)",
  borderRadius: "var(--lv-r-card)",
  overflow: "hidden",
  position: "relative",
};

const avatarFrameStyle: CSSProperties = {
  width: 76,
  height: 76,
  background: "var(--lv-bg-stage)",
  border: "1px solid rgba(245, 242, 235, 0.08)",
  boxShadow: "inset 0 1px 0 rgba(245, 242, 235, 0.04)",
  borderRadius: "var(--lv-r-card)",
  overflow: "hidden",
  position: "relative",
};

function ImageFieldStyles() {
  return (
    <style jsx global>{`
      .lv-theme .lv-imgfield-badge {
        position: absolute;
        bottom: 8px;
        right: 8px;
        width: 40px;
        height: 40px;
        display: grid;
        place-items: center;
        background: rgba(8, 8, 10, 0.62);
        color: var(--lv-ink-2);
        border: 1px solid rgba(255, 255, 255, 0.14);
        border-radius: var(--lv-r-pill);
        cursor: pointer;
        backdrop-filter: blur(6px);
        -webkit-backdrop-filter: blur(6px);
        transition: background var(--lv-dur-fast) var(--lv-ease),
          border-color var(--lv-dur-fast) var(--lv-ease), color var(--lv-dur-fast) var(--lv-ease);
      }
      .lv-theme .lv-imgfield-badge:hover {
        background: rgba(8, 8, 10, 0.85);
        border-color: rgba(255, 255, 255, 0.28);
        color: var(--lv-ink);
      }
      .lv-theme .lv-imgfield-badge:focus-visible {
        outline: 2px solid var(--lv-accent);
        outline-offset: 2px;
      }

      .lv-theme .lv-imgfield-pop {
        width: 420px;
        max-width: calc(100vw - 32px);
        background: rgba(5, 5, 7, 0.94);
        border: 1px solid rgba(245, 242, 235, 0.10);
        border-radius: var(--lv-r-card);
        box-shadow: 0 20px 56px rgba(0, 0, 0, 0.6);
        padding: 8px;
        z-index: var(--lv-z-modal);
        backdrop-filter: blur(14px);
        -webkit-backdrop-filter: blur(14px);
      }

      .lv-theme .lv-imgfield-body {
        position: relative;
        display: flex;
        flex-direction: column;
        gap: 6px;
      }

      .lv-theme .lv-imgfield-row {
        display: flex;
        align-items: center;
        gap: 12px;
        width: 100%;
        min-height: 46px;
        padding: 0 12px;
        background: transparent;
        border: 0;
        border-radius: var(--lv-r-card);
        color: var(--lv-ink);
        font-family: var(--lv-font-sans);
        font-size: 14px;
        text-align: left;
        cursor: pointer;
        transition: background var(--lv-dur-fast) var(--lv-ease);
      }
      .lv-theme .lv-imgfield-row:hover:not(:disabled) {
        background: rgba(245, 242, 235, 0.045);
      }
      .lv-theme .lv-imgfield-row:disabled {
        opacity: 0.5;
        cursor: default;
      }
      .lv-theme .lv-imgfield-row.is-muted {
        color: var(--lv-ink-3);
      }
      .lv-theme .lv-imgfield-row-icon {
        display: inline-flex;
        color: var(--lv-ink-3);
      }
      /* AI 重抽是品牌动作 —— 图标用香槟金（白名单：品牌语义位） */
      .lv-theme .lv-imgfield-row.is-accent .lv-imgfield-row-icon {
        color: var(--lv-accent);
      }

      .lv-theme .lv-imgfield-input,
      .lv-theme .lv-imgfield-textarea {
        width: 100%;
        border: 1px solid rgba(245, 242, 235, 0.11);
        background: rgba(5, 5, 7, 0.72);
        color: var(--lv-ink);
        font-family: var(--lv-font-sans);
        font-size: 13px;
        outline: none;
        box-shadow:
          inset 0 1px 0 rgba(245, 242, 235, 0.04),
          0 1px 0 rgba(0, 0, 0, 0.35);
        transition: border-color var(--lv-dur-fast) var(--lv-ease),
          background var(--lv-dur-fast) var(--lv-ease),
          box-shadow var(--lv-dur-fast) var(--lv-ease);
      }
      .lv-theme .lv-imgfield-input {
        height: 44px;
        padding: 0 16px;
        border-radius: var(--lv-r-pill);
      }
      .lv-theme .lv-imgfield-textarea {
        padding: 12px 14px;
        border-radius: var(--lv-r-card);
        line-height: 1.6;
        resize: none;
      }
      .lv-theme .lv-imgfield-input::placeholder,
      .lv-theme .lv-imgfield-textarea::placeholder {
        color: var(--lv-ink-4);
      }
      .lv-theme .lv-imgfield-input:focus,
      .lv-theme .lv-imgfield-textarea:focus {
        border-color: rgba(245, 242, 235, 0.24);
        background: rgba(5, 5, 7, 0.90);
        box-shadow:
          inset 0 1px 0 rgba(245, 242, 235, 0.06),
          0 0 0 1px rgba(245, 242, 235, 0.03);
      }

      .lv-theme .lv-imgfield-actions {
        display: flex;
        gap: 8px;
        justify-content: flex-end;
      }
      .lv-theme .lv-imgfield-cta,
      .lv-theme .lv-imgfield-ghost {
        height: 38px;
        padding: 0 16px;
        border-radius: var(--lv-r-pill);
        font-family: var(--lv-font-sans);
        font-size: 13px;
        font-weight: 600;
        cursor: pointer;
        transition: background var(--lv-dur-fast) var(--lv-ease),
          border-color var(--lv-dur-fast) var(--lv-ease), transform var(--lv-dur-fast) var(--lv-ease);
      }
      .lv-theme .lv-imgfield-cta {
        background: rgba(245, 242, 235, 0.94);
        color: var(--lv-bg);
        border: 1px solid rgba(245, 242, 235, 0.94);
      }
      .lv-theme .lv-imgfield-cta:hover:not(:disabled) {
        background: rgba(245, 242, 235, 1);
        transform: translateY(-1px);
      }
      .lv-theme .lv-imgfield-ghost {
        background: transparent;
        color: var(--lv-ink-2);
        border: 1px solid rgba(255, 255, 255, 0.12);
      }
      .lv-theme .lv-imgfield-ghost:hover:not(:disabled) {
        border-color: rgba(255, 255, 255, 0.24);
        color: var(--lv-ink);
      }
      .lv-theme .lv-imgfield-cta:disabled,
      .lv-theme .lv-imgfield-ghost:disabled {
        opacity: 0.5;
        cursor: default;
      }

      .lv-theme .lv-imgfield-busy {
        position: absolute;
        inset: 0;
        z-index: 1;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        gap: 8px;
        background: rgba(13, 16, 20, 0.82);
        border-radius: var(--lv-r-card);
        color: var(--lv-ink-2);
      }
      .lv-theme .lv-imgfield-error {
        margin: 4px 0 0;
        color: var(--lv-danger);
      }
    `}</style>
  );
}
