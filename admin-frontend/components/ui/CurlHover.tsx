"use client";

import { Check, Copy } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

interface Props {
  /** The fully-formed curl command to preview / copy. */
  curl: string;
  /** Optional title shown above the curl block, e.g. "POST /api/admin/...". */
  title?: string;
  /** Optional extra hint shown below (e.g. "需要 admin cookie"). */
  hint?: string;
  /** Anchor side. "right" aligns popover right edge to trigger's right edge —
   * best for table action buttons; "left" mirrors. */
  side?: "left" | "right";
  children: React.ReactNode;
}

/** Hover wrapper that reveals a popover with a copyable curl command.
 *
 * Renders the popover via React Portal at document.body so it escapes any
 * ``overflow: hidden`` ancestor (admin's ``.card`` clips otherwise). A small
 * close-delay lets the cursor cross the gap between trigger and popover
 * without dismissing it.
 */
export function CurlHover({ curl, title, hint, side = "right", children }: Props) {
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const [coords, setCoords] = useState<{ top: number; left: number } | null>(null);
  const triggerRef = useRef<HTMLSpanElement | null>(null);
  const closeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  const cancelClose = () => {
    if (closeTimer.current) {
      clearTimeout(closeTimer.current);
      closeTimer.current = null;
    }
  };
  const scheduleClose = () => {
    cancelClose();
    closeTimer.current = setTimeout(() => {
      setOpen(false);
      setCopied(false);
    }, 120);
  };

  const handleOpen = () => {
    cancelClose();
    const el = triggerRef.current;
    if (el) {
      const r = el.getBoundingClientRect();
      // POPOVER_WIDTH min ~ 380; align relative to trigger edge per `side`.
      const POPOVER_W = 420;
      const left = side === "right" ? r.right - POPOVER_W : r.left;
      setCoords({
        top: r.bottom + 6,
        left: Math.max(8, left),
      });
    }
    setOpen(true);
  };

  const handleCopy = async (e: React.MouseEvent) => {
    e.stopPropagation();
    e.preventDefault();
    try {
      await navigator.clipboard.writeText(curl);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // clipboard may be blocked; silent fail
    }
  };

  const popover =
    open && coords && mounted
      ? createPortal(
          <div
            role="tooltip"
            onMouseEnter={cancelClose}
            onMouseLeave={scheduleClose}
            onClick={(e) => e.stopPropagation()}
            style={{
              position: "fixed",
              top: coords.top,
              left: coords.left,
              zIndex: 1000,
              width: 420,
              maxWidth: "calc(100vw - 16px)",
              background: "var(--bg-elev)",
              border: "1px solid var(--border)",
              borderRadius: 8,
              boxShadow: "var(--shadow-lg)",
              padding: 10,
              color: "var(--fg)",
              fontSize: 12,
              lineHeight: 1.5,
              textAlign: "left",
            }}
          >
            {title && (
              <div
                className="mono"
                style={{
                  fontSize: 10.5,
                  marginBottom: 6,
                  textTransform: "uppercase",
                  letterSpacing: "0.05em",
                  color: "var(--fg-tertiary)",
                }}
              >
                {title}
              </div>
            )}
            <pre
              className="mono"
              style={{
                margin: 0,
                padding: "8px 10px",
                background: "var(--bg-subtle)",
                border: "1px solid var(--border)",
                borderRadius: 6,
                fontSize: 11,
                whiteSpace: "pre-wrap",
                wordBreak: "break-all",
                lineHeight: 1.6,
                maxHeight: 240,
                overflow: "auto",
                color: "var(--fg)",
              }}
            >
              {curl}
            </pre>
            <div
              style={{
                marginTop: 8,
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                gap: 8,
              }}
            >
              {hint ? (
                <span style={{ fontSize: 11, color: "var(--fg-tertiary)" }}>
                  {hint}
                </span>
              ) : (
                <span />
              )}
              <button
                type="button"
                onClick={handleCopy}
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 4,
                  background: copied ? "var(--accent-soft)" : "var(--bg-elev)",
                  border: "1px solid var(--border)",
                  borderRadius: 4,
                  color: copied ? "var(--accent)" : "var(--fg-secondary)",
                  padding: "4px 10px",
                  fontSize: 11,
                  cursor: "pointer",
                  transition: "background 120ms, color 120ms",
                }}
              >
                {copied ? <Check size={11} /> : <Copy size={11} />}
                {copied ? "已复制" : "复制"}
              </button>
            </div>
          </div>,
          document.body,
        )
      : null;

  return (
    <>
      <span
        ref={triggerRef}
        style={{ display: "inline-block", position: "relative" }}
        onMouseEnter={handleOpen}
        onMouseLeave={scheduleClose}
      >
        {children}
      </span>
      {popover}
    </>
  );
}
