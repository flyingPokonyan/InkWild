"use client";

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

import { Modal } from "./Modal";

/* ============================================================================
 * Types
 * ============================================================================ */

export interface ConfirmOptions {
  title?: ReactNode;
  /** 主体文案，支持 string 或 ReactNode */
  message: ReactNode;
  confirmText?: string;
  cancelText?: string;
  /** 破坏性操作（红色按钮）。默认 false */
  danger?: boolean;
  /** 关闭按钮（X / 背景点击）是否可用。默认 true。danger 时建议传 false 强制选择 */
  dismissable?: boolean;
}

interface InternalState extends ConfirmOptions {
  open: boolean;
  resolver?: (ok: boolean) => void;
}

type ConfirmFn = (opts: ConfirmOptions) => Promise<boolean>;

/* ============================================================================
 * Context
 * ============================================================================ */

const ConfirmContext = createContext<ConfirmFn | null>(null);

/**
 * Promise-based 命令式 confirm dialog。
 * - 用法：const confirm = useConfirm(); const ok = await confirm({ message: '...' });
 * - 必须在 <ConfirmProvider> 子树内调用
 */
export function useConfirm(): ConfirmFn {
  const fn = useContext(ConfirmContext);
  if (!fn) {
    throw new Error("useConfirm 必须在 <ConfirmProvider> 子树内调用");
  }
  return fn;
}

/* ============================================================================
 * Provider（挂在 root layout，全局一个单例 dialog）
 * ============================================================================ */

export function ConfirmProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<InternalState>({ open: false, message: "" });
  const resolverRef = useRef<((ok: boolean) => void) | null>(null);

  const confirm = useCallback<ConfirmFn>((opts) => {
    return new Promise<boolean>((resolve) => {
      resolverRef.current = resolve;
      setState({ ...opts, open: true });
    });
  }, []);

  const settle = useCallback((ok: boolean) => {
    const r = resolverRef.current;
    resolverRef.current = null;
    setState((prev) => ({ ...prev, open: false }));
    if (r) r(ok);
  }, []);

  const value = useMemo(() => confirm, [confirm]);

  return (
    <ConfirmContext.Provider value={value}>
      {children}
      <ConfirmDialogView
        state={state}
        onConfirm={() => settle(true)}
        onCancel={() => settle(false)}
      />
    </ConfirmContext.Provider>
  );
}

/* ============================================================================
 * View
 * ============================================================================ */

interface ViewProps {
  state: InternalState;
  onConfirm: () => void;
  onCancel: () => void;
}

function ConfirmDialogView({ state, onConfirm, onCancel }: ViewProps) {
  const {
    open,
    title,
    message,
    confirmText = "确认",
    cancelText = "取消",
    danger = false,
    dismissable = true,
  } = state;

  return (
    <Modal
      open={open}
      onClose={onCancel}
      dismissable={dismissable}
      title={title}
      maxWidth={420}
      footer={
        <>
          <button
            type="button"
            className="lv-btn-confirm-cancel"
            onClick={onCancel}
          >
            {cancelText}
          </button>
          <button
            type="button"
            className={`lv-btn-confirm-primary${danger ? " is-danger" : ""}`}
            onClick={onConfirm}
            autoFocus
          >
            {confirmText}
          </button>
        </>
      }
    >
      {typeof message === "string" ? (
        <p style={{ margin: 0, color: "var(--lv-ink-2)" }}>{message}</p>
      ) : (
        message
      )}
    </Modal>
  );
}
