"use client";

import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useTranslations } from "next-intl";
import { CheckCircle2, Eye, EyeOff } from "lucide-react";

import { changePassword } from "@/lib/auth-api";

type Values = { oldPassword: string; newPassword: string; confirmPassword: string };

/**
 * 共享的修改密码表单（桌面账户中心内联 + 移动端弹层都用）。
 * hasPassword=false（纯三方登录、未设密码）时只展示说明，不给表单。
 */
export function ChangePasswordForm({ hasPassword, onDone }: { hasPassword: boolean; onDone?: () => void }) {
  const t = useTranslations("account");
  const [busy, setBusy] = useState(false);
  const [apiError, setApiError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [show, setShow] = useState(false);

  const schema = z
    .object({
      oldPassword: z.string().min(1),
      newPassword: z.string().min(8, t("passwordMin")),
      confirmPassword: z.string().min(1),
    })
    .refine((v) => v.newPassword === v.confirmPassword, {
      path: ["confirmPassword"],
      message: t("passwordMismatch"),
    });

  const {
    register,
    handleSubmit,
    formState: { errors },
    reset,
  } = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { oldPassword: "", newPassword: "", confirmPassword: "" },
  });

  if (!hasPassword) {
    return <p className="cpf-note">{t("noPasswordSet")}</p>;
  }

  if (done) {
    return (
      <div className="cpf-done">
        <CheckCircle2 size={18} />
        <span>{t("changeSuccess")}</span>
        <button type="button" className="cpf-link" onClick={() => (onDone ? onDone() : setDone(false))}>
          {t("done")}
        </button>
        <CpfStyles />
      </div>
    );
  }

  const onSubmit = async (values: Values) => {
    setBusy(true);
    setApiError(null);
    try {
      await changePassword({ oldPassword: values.oldPassword, newPassword: values.newPassword });
      reset();
      setDone(true);
    } catch (err) {
      setApiError(err instanceof Error ? err.message : t("updateFailed"));
    } finally {
      setBusy(false);
    }
  };

  const fields: Array<{ key: keyof Values; label: string; autoComplete: string }> = [
    { key: "oldPassword", label: t("oldPassword"), autoComplete: "current-password" },
    { key: "newPassword", label: t("newPassword"), autoComplete: "new-password" },
    { key: "confirmPassword", label: t("confirmPassword"), autoComplete: "new-password" },
  ];

  return (
    <form className="cpf" onSubmit={handleSubmit(onSubmit)} noValidate>
      {fields.map((f) => (
        <label key={f.key} className="cpf-field">
          <span className="cpf-label">{f.label}</span>
          <span className="cpf-input-wrap">
            <input
              type={show ? "text" : "password"}
              autoComplete={f.autoComplete}
              disabled={busy}
              className={`cpf-input ${errors[f.key] ? "has-error" : ""}`}
              {...register(f.key)}
            />
            {f.key === "oldPassword" && (
              <button
                type="button"
                className="cpf-toggle"
                onClick={() => setShow((v) => !v)}
                aria-label={show ? t("hidePassword") : t("showPassword")}
              >
                {show ? <EyeOff size={15} /> : <Eye size={15} />}
              </button>
            )}
          </span>
          {errors[f.key]?.message && <em className="cpf-err">{errors[f.key]?.message}</em>}
        </label>
      ))}

      {apiError && <p className="cpf-api-err">{apiError}</p>}

      <button type="submit" className="cpf-submit" disabled={busy}>
        {busy ? t("changing") : t("changeCta")}
      </button>
      <CpfStyles />
    </form>
  );
}

function CpfStyles() {
  return (
    <style jsx global>{`
      .cpf {
        display: flex;
        flex-direction: column;
        gap: 12px;
      }
      .cpf-note {
        margin: 0;
        color: var(--lv-ink-3);
        font-size: var(--lv-t-compact);
        line-height: 1.6;
      }
      .cpf-field {
        display: flex;
        flex-direction: column;
        gap: 6px;
      }
      .cpf-label {
        color: var(--lv-ink-2);
        font-size: var(--lv-t-meta);
        padding-left: 2px;
      }
      .cpf-input-wrap {
        position: relative;
        display: block;
      }
      .cpf-input {
        width: 100%;
        height: 44px;
        border-radius: var(--lv-r-pill);
        border: 1px solid rgba(255, 255, 255, 0.1);
        background: rgba(255, 255, 255, 0.045);
        color: var(--lv-ink);
        padding: 0 44px 0 16px;
        font-family: var(--lv-font-sans);
        font-size: 13px;
        outline: none;
        transition: border-color var(--lv-dur-fast) var(--lv-ease), background var(--lv-dur-fast) var(--lv-ease);
      }
      .cpf-input::placeholder {
        color: var(--lv-ink-3);
      }
      .cpf-input:focus {
        border-color: rgba(255, 255, 255, 0.22);
        background: rgba(255, 255, 255, 0.07);
      }
      .cpf-input.has-error {
        border-color: rgba(239, 130, 118, 0.4);
      }
      .cpf-toggle {
        position: absolute;
        right: 6px;
        top: 50%;
        transform: translateY(-50%);
        width: 34px;
        height: 34px;
        border: 0;
        border-radius: 50%;
        background: transparent;
        color: var(--lv-ink-3);
        display: grid;
        place-items: center;
        cursor: pointer;
        touch-action: manipulation;
      }
      .cpf-toggle:hover {
        color: var(--lv-ink);
        background: rgba(255, 255, 255, 0.06);
      }
      .cpf-err,
      .cpf-api-err {
        color: var(--lv-danger);
        font-size: 11px;
        font-style: normal;
        margin: 0;
        padding-left: 4px;
      }
      .cpf-submit {
        height: 46px;
        margin-top: 2px;
        border-radius: var(--lv-r-pill);
        border: none;
        background: rgba(245, 242, 235, 0.94);
        color: var(--lv-bg);
        font-family: var(--lv-font-sans);
        font-size: 14px;
        font-weight: 600;
        cursor: pointer;
        transition: background var(--lv-dur-fast) var(--lv-ease), transform var(--lv-dur-fast) var(--lv-ease);
        touch-action: manipulation;
      }
      .cpf-submit:hover:not(:disabled) {
        background: rgba(245, 242, 235, 1);
        transform: translateY(-1px);
      }
      .cpf-submit:disabled {
        opacity: 0.5;
        cursor: not-allowed;
      }
      .cpf-done {
        display: flex;
        align-items: center;
        gap: 8px;
        color: var(--lv-success);
        font-size: var(--lv-t-compact);
      }
      .cpf-link {
        margin-left: auto;
        border: 0;
        background: transparent;
        color: var(--lv-ink-2);
        cursor: pointer;
        text-decoration: underline;
        text-underline-offset: 3px;
        font-size: var(--lv-t-meta);
      }
      .cpf-link:hover {
        color: var(--lv-ink);
      }
    `}</style>
  );
}
