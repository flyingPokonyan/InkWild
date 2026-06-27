"use client";

import { useState, type ReactNode } from "react";
import { useTranslations } from "next-intl";
import { Bug, Check, ImagePlus, Lightbulb, X } from "lucide-react";

import { MobileSheet } from "@/components/ui/MobileSheet";
import { Modal } from "@/components/ui/Modal";
import { readAsDataUrl } from "@/lib/avatar";
import { useSubmitFeedback, type FeedbackCategory } from "@/lib/feedback";
import { useIsMobile } from "@/lib/use-viewport";

const IMAGE_MAX_BYTES = 4 * 1024 * 1024;
const IMAGE_TYPES = ["image/png", "image/jpeg", "image/webp"];

export function FeedbackDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const t = useTranslations("feedback");
  const isMobile = useIsMobile();

  const body = <FeedbackForm onClose={onClose} key={open ? "open" : "closed"} />;

  if (isMobile) {
    return (
      <MobileSheet open={open} onClose={onClose} title={t("title")} tone="deep">
        {body}
      </MobileSheet>
    );
  }
  return (
    <Modal open={open} onClose={onClose} title={t("title")} maxWidth={460} tone="deep">
      {body}
    </Modal>
  );
}

function FeedbackForm({ onClose }: { onClose: () => void }) {
  const t = useTranslations("feedback");
  const submit = useSubmitFeedback();
  const [category, setCategory] = useState<FeedbackCategory>("bug");
  const [content, setContent] = useState("");
  const [image, setImage] = useState<string | null>(null);
  const [contact, setContact] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  async function handleFile(file: File | undefined) {
    if (!file) return;
    if (!IMAGE_TYPES.includes(file.type)) return setErr(t("imageType"));
    if (file.size > IMAGE_MAX_BYTES) return setErr(t("imageTooLarge"));
    setErr(null);
    setImage(await readAsDataUrl(file));
  }

  function handleSubmit() {
    setErr(null);
    submit.mutate(
      {
        category,
        content: content.trim(),
        image,
        page_url: typeof window !== "undefined" ? window.location.pathname : null,
        contact: contact.trim() || null,
      },
      {
        onSuccess: () => setDone(true),
        onError: (e) => setErr(e instanceof Error ? e.message : t("errorGeneric")),
      },
    );
  }

  if (done) {
    return (
      <div className="fb-done">
        <span className="fb-done-mark"><Check size={22} strokeWidth={2.4} /></span>
        <h3>{t("successTitle")}</h3>
        <p>{t("successBody")}</p>
        <button type="button" className="lv-btn lv-btn-primary lv-btn-lg fb-block" onClick={onClose}>
          {t("close")}
        </button>
        <style jsx global>{FB_CSS}</style>
      </div>
    );
  }

  return (
    <div className="fb-form">
      <div className="fb-cats">
        <CatButton active={category === "bug"} onClick={() => setCategory("bug")} icon={<Bug size={15} />} label={t("catBug")} />
        <CatButton active={category === "suggestion"} onClick={() => setCategory("suggestion")} icon={<Lightbulb size={15} />} label={t("catSuggestion")} />
      </div>

      <label className="fb-label">{t("contentLabel")}</label>
      <textarea
        className="lv-input lv-input--textarea fb-textarea"
        rows={5}
        value={content}
        maxLength={4000}
        placeholder={t("contentPlaceholder")}
        onChange={(e) => setContent(e.target.value)}
      />

      <div className="fb-imgrow">
        {image ? (
          <div className="fb-img-preview">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={image} alt="" />
            <button type="button" onClick={() => setImage(null)} aria-label={t("removeImage")}><X size={13} /></button>
          </div>
        ) : (
          <label className="fb-upload">
            <ImagePlus size={15} strokeWidth={1.8} />
            {t("screenshot")}
            <input
              type="file"
              accept="image/png,image/jpeg,image/webp"
              hidden
              onChange={(e) => { void handleFile(e.target.files?.[0]); e.target.value = ""; }}
            />
          </label>
        )}
      </div>

      <label className="fb-label">{t("contactLabel")}</label>
      <input
        className="lv-input"
        value={contact}
        maxLength={200}
        placeholder={t("contactPlaceholder")}
        onChange={(e) => setContact(e.target.value)}
      />

      {err && <p className="fb-err">{err}</p>}

      <button
        type="button"
        className="lv-btn lv-btn-primary lv-btn-lg fb-block fb-submit"
        disabled={submit.isPending || content.trim().length === 0}
        onClick={handleSubmit}
      >
        {submit.isPending ? t("submitting") : t("submit")}
      </button>

      <style jsx global>{FB_CSS}</style>
    </div>
  );
}

function CatButton({ active, onClick, icon, label }: { active: boolean; onClick: () => void; icon: ReactNode; label: string }) {
  return (
    <button type="button" className="fb-cat" data-active={active} onClick={onClick}>
      {icon}
      {label}
    </button>
  );
}

const FB_CSS = `
  .fb-form { display: flex; flex-direction: column; }
  .fb-cats { display: flex; gap: 8px; margin-bottom: 18px; }
  .fb-cat {
    flex: 1; display: inline-flex; align-items: center; justify-content: center; gap: 7px;
    height: 42px; border-radius: var(--lv-r-pill); border: 1px solid var(--lv-line-2);
    background: transparent; color: var(--lv-ink-3); font-size: 13px; font-weight: 500;
    cursor: pointer; transition: color 180ms var(--lv-ease), background 180ms var(--lv-ease), border-color 180ms var(--lv-ease);
  }
  .fb-cat:hover { color: var(--lv-ink-2); border-color: var(--lv-line-2); background: rgba(255,255,255,0.03); }
  .fb-cat[data-active="true"] { color: var(--lv-bg); background: var(--lv-ink); border-color: var(--lv-ink); }
  .fb-label { color: var(--lv-ink-3); font-size: 12px; margin-bottom: 7px; letter-spacing: 0.01em; }
  .fb-textarea { font-size: 14px; }
  .fb-imgrow { margin: 13px 0 18px; }
  .fb-upload {
    display: inline-flex; align-items: center; gap: 7px; height: 38px; padding: 0 15px;
    border-radius: var(--lv-r-pill); border: 1px dashed var(--lv-line-2); color: var(--lv-ink-3);
    font-size: 13px; cursor: pointer; transition: color 180ms var(--lv-ease), border-color 180ms var(--lv-ease);
  }
  .fb-upload:hover { color: var(--lv-ink-2); border-color: var(--lv-ink-4); }
  .fb-img-preview { position: relative; width: 96px; height: 96px; }
  .fb-img-preview img { width: 100%; height: 100%; object-fit: cover; border-radius: var(--lv-r-input); border: 1px solid var(--lv-line); }
  .fb-img-preview button {
    position: absolute; top: -7px; right: -7px; width: 22px; height: 22px; display: grid; place-items: center;
    border-radius: 50%; background: var(--lv-bg-2); border: 1px solid var(--lv-line-2); color: var(--lv-ink-2); cursor: pointer;
  }
  .fb-err { color: var(--lv-danger); font-size: 12px; margin: 4px 0 0; }
  .fb-block { width: 100%; justify-content: center; }
  .fb-submit { margin-top: 20px; }
  .fb-done { display: flex; flex-direction: column; align-items: center; text-align: center; padding: 14px 8px 6px; }
  .fb-done-mark { display: grid; place-items: center; width: 52px; height: 52px; border-radius: 50%; background: rgba(127,176,145,0.14); color: var(--lv-success); margin-bottom: 15px; }
  .fb-done h3 { margin: 0 0 7px; color: var(--lv-ink); font-family: var(--lv-font-serif); font-size: 20px; font-weight: 500; }
  .fb-done p { margin: 0 0 22px; color: var(--lv-ink-3); font-size: 13px; }
`;
