"use client";

import type { MouseEvent } from "react";

import { useConfirm } from "@/components/ui/ConfirmDialog";

interface Props {
  onDelete: () => void;
  /** 用于二次确认文案 + a11y aria-label */
  label: string;
}

/**
 * 卡片右上角的删除按钮。
 * - 默认在移动端半透明可见（移动没有 hover），桌面 hover 时变亮
 * - 点击 stopPropagation 避免触发卡片本身的进入逻辑
 * - 二次确认走站内 ConfirmDialog（破坏性 danger 模式）
 */
export function WorkshopCardDeleteButton({ onDelete, label }: Props) {
  const confirm = useConfirm();

  const handleClick = async (e: MouseEvent<HTMLButtonElement>) => {
    e.stopPropagation();
    e.preventDefault();
    const ok = await confirm({
      title: "删除确认",
      message: `确认删除「${label}」？此操作不可恢复。`,
      confirmText: "删除",
      cancelText: "取消",
      danger: true,
    });
    if (ok) onDelete();
  };

  return (
    <button
      type="button"
      className="workshop-card-delete"
      onClick={handleClick}
      aria-label={`删除 ${label}`}
      title="删除"
    >
      <svg
        width="16"
        height="16"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden
      >
        <polyline points="3 6 5 6 21 6" />
        <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
        <path d="M10 11v6" />
        <path d="M14 11v6" />
        <path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" />
      </svg>
    </button>
  );
}
