"use client";

import { useId, type ReactNode } from "react";

interface SelectOption {
  value: string;
  label: string;
}

interface SelectFieldProps {
  label?: ReactNode;
  required?: boolean;
  help?: ReactNode;
  error?: ReactNode;
  value: string;
  onChange: (next: string) => void;
  options: SelectOption[];
  placeholder?: string;
  /** 允许填没有出现在 options 里的自定义值（额外 input） */
  allowCustom?: boolean;
  customPlaceholder?: string;
}

/**
 * 下拉选择，规整成 .lv-input。
 * 选项 + 兜底自定义文本（用于 location 这种"列表里没有就允许自填"场景）。
 */
export function SelectField({
  label,
  required,
  help,
  error,
  value,
  onChange,
  options,
  placeholder,
  allowCustom = false,
  customPlaceholder,
}: SelectFieldProps) {
  const id = useId();
  const labelClass = `lv-form-label${required ? " lv-form-label--required" : ""}`;

  const isCustom = allowCustom && value !== "" && !options.some((o) => o.value === value);
  const selectValue = isCustom ? "__custom__" : value;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--lv-s-2)" }}>
      {label && (
        <label htmlFor={id} className={labelClass}>
          {label}
        </label>
      )}
      <select
        id={id}
        className="lv-input"
        value={selectValue}
        onChange={(e) => {
          if (e.target.value === "__custom__") {
            onChange(value || "");
          } else {
            onChange(e.target.value);
          }
        }}
      >
        {placeholder && <option value="">{placeholder}</option>}
        {options.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
        {allowCustom && <option value="__custom__">自定义…</option>}
      </select>
      {(isCustom || (allowCustom && selectValue === "__custom__")) && (
        <input
          className="lv-input"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={customPlaceholder}
        />
      )}
      {error ? (
        <span className="lv-form-error" role="alert">
          {error}
        </span>
      ) : help ? (
        <span className="lv-form-help">{help}</span>
      ) : null}
    </div>
  );
}
