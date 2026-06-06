"use client";

import { X } from "lucide-react";
import { useEffect } from "react";

interface Props {
  open: boolean;
  onClose: () => void;
  title: React.ReactNode;
  sub?: React.ReactNode;
  children: React.ReactNode;
}

export function Drawer({ open, onClose, title, sub, children }: Props) {
  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;
  return (
    <>
      <div className="drawer-backdrop" onClick={onClose} />
      <aside className="drawer" role="dialog" aria-modal="true">
        <div className="drawer-hd">
          <div>
            <h3>{title}</h3>
            {sub && <div className="drawer-hd-sub">{sub}</div>}
          </div>
          <button
            type="button"
            className="topbar-ibtn"
            onClick={onClose}
            aria-label="关闭"
          >
            <X size={14} />
          </button>
        </div>
        <div className="drawer-bd">{children}</div>
      </aside>
    </>
  );
}
