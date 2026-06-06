"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { FormField } from "@/components/ui/FormField";

import { JsonField } from "./JsonField";

interface CluesEditorProps {
  clues: Record<string, unknown>;
  onChange: (next: Record<string, unknown>) => void;
}

/**
 * key→value 线索编辑器。常见形态：value 是 string（情报内容）。
 * 复杂结构（嵌套对象 / 数组）时自动跳到高级 JSON 模式，避免乱解。
 */
export function CluesEditor({ clues, onChange }: CluesEditorProps) {
  const t = useTranslations("admin.editor.script.clues");
  const [draftId, setDraftId] = useState("");

  const entries = Object.entries(clues);
  const allSimple = entries.every(([, v]) => typeof v === "string");

  const setEntry = (key: string, value: string) => {
    onChange({ ...clues, [key]: value });
  };
  const removeEntry = (key: string) => {
    const next = { ...clues };
    delete next[key];
    onChange(next);
  };
  const renameEntry = (oldKey: string, newKey: string) => {
    if (!newKey || newKey === oldKey) return;
    const next: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(clues)) {
      next[k === oldKey ? newKey : k] = v;
    }
    onChange(next);
  };
  const addEntry = () => {
    const id = draftId.trim();
    if (!id || id in clues) return;
    onChange({ ...clues, [id]: "" });
    setDraftId("");
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--lv-s-4)" }}>
      {allSimple && entries.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--lv-s-3)" }}>
          {entries.map(([key, value]) => (
            <div
              key={key}
              style={{
                display: "grid",
                gap: "var(--lv-s-3)",
                gridTemplateColumns: "200px 1fr auto",
                alignItems: "flex-start",
              }}
              className="clues-row"
            >
              <div style={{ display: "flex", flexDirection: "column", gap: "var(--lv-s-2)" }}>
                <label className="lv-form-label">{t("id")}</label>
                <input
                  className="lv-input"
                  defaultValue={key}
                  onBlur={(e) => renameEntry(key, e.target.value)}
                />
              </div>
              <FormField
                label={t("content")}
                multiline
                rows={2}
                value={typeof value === "string" ? value : ""}
                onChange={(e) => setEntry(key, e.target.value)}
                placeholder={t("contentPlaceholder")}
              />
              <button
                type="button"
                onClick={() => removeEntry(key)}
                className="lv-btn lv-btn-sm"
                style={{
                  marginTop: 22,
                  color: "var(--lv-danger)",
                  borderColor: "rgba(184,92,92,0.3)",
                }}
              >
                ×
              </button>
            </div>
          ))}
        </div>
      )}

      {!allSimple && entries.length > 0 && (
        <p className="lv-form-help" style={{ margin: 0 }}>
          {t("structuredOnly")}
        </p>
      )}

      {entries.length === 0 && (
        <div
          className="lv-t-meta"
          style={{
            padding: "var(--lv-s-6)",
            color: "var(--lv-ink-3)",
            border: "1px dashed var(--lv-line)",
            borderRadius: "var(--lv-r-card)",
            textAlign: "center",
          }}
        >
          {t("empty")}
        </div>
      )}

      {allSimple && (
        <div
          style={{
            display: "flex",
            gap: "var(--lv-s-2)",
            alignItems: "flex-end",
            flexWrap: "wrap",
          }}
        >
          <div style={{ flex: 1, minWidth: 200 }}>
            <FormField
              label={t("id")}
              value={draftId}
              onChange={(e) => setDraftId(e.target.value)}
              placeholder={t("idPlaceholder")}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  addEntry();
                }
              }}
            />
          </div>
          <button type="button" className="lv-btn lv-btn-sm" onClick={addEntry}>
            {t("addCta")}
          </button>
        </div>
      )}

      <JsonField<Record<string, unknown>>
        value={clues}
        onChange={(next) => onChange(next ?? {})}
        rows={8}
        collapsible
        defaultOpen={!allSimple}
        summary={t("advanced")}
      />
    </div>
  );
}
