"use client";

import { useLocale } from "next-intl";
import { useRouter } from "next/navigation";
import { useTransition } from "react";

type Locale = "zh" | "en";

const COOKIE_MAX_AGE = 60 * 60 * 24 * 365;

export function LangChip() {
  const locale = useLocale() as Locale;
  const router = useRouter();
  const [isPending, startTransition] = useTransition();

  const toggle = () => {
    if (isPending) return;
    const next: Locale = locale === "zh" ? "en" : "zh";
    document.cookie = `NEXT_LOCALE=${next}; path=/; max-age=${COOKIE_MAX_AGE}; SameSite=Lax`;
    startTransition(() => {
      router.refresh();
    });
  };

  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={locale === "zh" ? "Switch to English" : "切换到中文"}
      disabled={isPending}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 4,
        padding: "6px 11px",
        minHeight: 32,
        border: "1px solid rgba(255,255,255,0.18)",
        borderRadius: 9999,
        background: "rgba(255,255,255,0.06)",
        backdropFilter: "blur(12px)",
        WebkitBackdropFilter: "blur(12px)",
        color: "var(--lv-ink)",
        fontFamily: "var(--lv-font-mono)",
        fontSize: 10,
        letterSpacing: "0.04em",
        cursor: isPending ? "wait" : "pointer",
        opacity: isPending ? 0.6 : 1,
        transition: "opacity 200ms ease",
      }}
    >
      <span style={{ opacity: locale === "zh" ? 1 : 0.45 }}>中</span>
      <span style={{ opacity: 0.35 }}> / </span>
      <span style={{ opacity: locale === "en" ? 1 : 0.45 }}>EN</span>
    </button>
  );
}
