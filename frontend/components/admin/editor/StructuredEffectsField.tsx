"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { FormField } from "@/components/ui/FormField";
import { KNOWN_EFFECT_KEYS, type EffectKey } from "@/lib/draft-schemas";

import { SelectField } from "./fields/SelectField";
import { JsonField } from "./JsonField";

interface StructuredEffectsFieldProps {
  effects: Record<string, unknown>;
  knownLocations: string[];
  knownClueIds: string[];
  knownNpcs: string[];
  onChange: (next: Record<string, unknown>) => void;
}

/**
 * 事件 effects 结构化编辑器。
 * 已知 key 渲染对应字段；未识别 key 进入"高级 JSON"，在 details 里全 raw。
 */
export function StructuredEffectsField({
  effects,
  knownLocations,
  knownClueIds,
  knownNpcs,
  onChange,
}: StructuredEffectsFieldProps) {
  const t = useTranslations("admin.editor.script.effect");
  const [pickerKey, setPickerKey] = useState<string>("give_clue");

  const knownEntries = KNOWN_EFFECT_KEYS.filter((k) => k in effects);
  const unknownEntries = Object.keys(effects).filter(
    (k) => !(KNOWN_EFFECT_KEYS as readonly string[]).includes(k),
  );

  const setKey = (key: string, value: unknown) => {
    onChange({ ...effects, [key]: value });
  };
  const removeKey = (key: string) => {
    const next = { ...effects };
    delete next[key];
    onChange(next);
  };

  const addRow = () => {
    if (pickerKey in effects) return;
    setKey(pickerKey, defaultEffectValue(pickerKey as EffectKey));
  };

  const availableToAdd = KNOWN_EFFECT_KEYS.filter((k) => !(k in effects));

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--lv-s-4)" }}>
      {knownEntries.map((key) => (
        <EffectRow
          key={key}
          effectKey={key}
          value={effects[key]}
          knownLocations={knownLocations}
          knownClueIds={knownClueIds}
          knownNpcs={knownNpcs}
          onChange={(v) => setKey(key, v)}
          onRemove={() => removeKey(key)}
        />
      ))}

      {availableToAdd.length > 0 && (
        <div
          style={{
            display: "flex",
            gap: "var(--lv-s-2)",
            alignItems: "flex-end",
            flexWrap: "wrap",
          }}
        >
          <div style={{ minWidth: 200, flex: 1 }}>
            <SelectField
              value={pickerKey}
              onChange={setPickerKey}
              options={availableToAdd.map((k) => ({ value: k, label: t(k) }))}
            />
          </div>
          <button type="button" className="lv-btn lv-btn-sm" onClick={addRow}>
            {t("addRow")}
          </button>
        </div>
      )}

      <JsonField<Record<string, unknown>>
        value={onlyUnknown(effects, unknownEntries)}
        onChange={(next) => {
          // merge: keep known entries, replace unknown bucket
          const known: Record<string, unknown> = {};
          for (const k of knownEntries) known[k] = effects[k];
          onChange({ ...known, ...(next ?? {}) });
        }}
        rows={4}
        collapsible
        defaultOpen={unknownEntries.length > 0}
        summary={t("advanced")}
      />
    </div>
  );
}

function onlyUnknown(effects: Record<string, unknown>, unknownKeys: string[]) {
  const out: Record<string, unknown> = {};
  for (const k of unknownKeys) out[k] = effects[k];
  return out;
}

function defaultEffectValue(key: EffectKey): unknown {
  switch (key) {
    case "give_clue":
      return { clue_id: "" };
    case "move_npc":
      return { npc: "", to: "" };
    case "unlock_location":
      return { location: "" };
    case "set_flag":
      return { name: "", value: true };
  }
}

interface EffectRowProps {
  effectKey: EffectKey;
  value: unknown;
  knownLocations: string[];
  knownClueIds: string[];
  knownNpcs: string[];
  onChange: (next: unknown) => void;
  onRemove: () => void;
}

function EffectRow({
  effectKey,
  value,
  knownLocations,
  knownClueIds,
  knownNpcs,
  onChange,
  onRemove,
}: EffectRowProps) {
  const t = useTranslations("admin.editor.script.effect");
  const obj = (value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {});

  const inner = (() => {
    switch (effectKey) {
      case "give_clue":
        return (
          <SelectField
            value={(obj.clue_id as string) ?? ""}
            onChange={(next) => onChange({ ...obj, clue_id: next })}
            options={knownClueIds.map((c) => ({ value: c, label: c }))}
            allowCustom
            placeholder={knownClueIds.length === 0 ? t("valuePlaceholder") : undefined}
          />
        );
      case "move_npc":
        return (
          <div style={{ display: "grid", gap: "var(--lv-s-2)", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))" }}>
            <SelectField
              value={(obj.npc as string) ?? ""}
              onChange={(next) => onChange({ ...obj, npc: next })}
              options={knownNpcs.map((n) => ({ value: n, label: n }))}
              allowCustom
            />
            <SelectField
              value={(obj.to as string) ?? ""}
              onChange={(next) => onChange({ ...obj, to: next })}
              options={knownLocations.map((l) => ({ value: l, label: l }))}
              allowCustom
            />
          </div>
        );
      case "unlock_location":
        return (
          <SelectField
            value={(obj.location as string) ?? ""}
            onChange={(next) => onChange({ ...obj, location: next })}
            options={knownLocations.map((l) => ({ value: l, label: l }))}
            allowCustom
          />
        );
      case "set_flag":
        return (
          <div style={{ display: "grid", gap: "var(--lv-s-2)", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))" }}>
            <FormField
              value={(obj.name as string) ?? ""}
              onChange={(e) => onChange({ ...obj, name: e.target.value })}
              placeholder="flag_name"
            />
            <FormField
              value={String(obj.value ?? "")}
              onChange={(e) => onChange({ ...obj, value: parseFlagValue(e.target.value) })}
              placeholder={t("valuePlaceholder")}
            />
          </div>
        );
    }
  })();

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "var(--lv-s-2)",
        padding: "var(--lv-s-3)",
        border: "1px solid var(--lv-line)",
        borderRadius: "var(--lv-r-card)",
        background: "rgba(255,255,255,0.02)",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "var(--lv-s-2)" }}>
        <span className="lv-t-caps" style={{ color: "var(--lv-ink-2)" }}>
          {t(effectKey)}
        </span>
        <button
          type="button"
          onClick={onRemove}
          className="lv-t-meta"
          style={{
            background: "transparent",
            border: 0,
            color: "var(--lv-ink-3)",
            cursor: "pointer",
            minHeight: 32,
            padding: "0 var(--lv-s-2)",
          }}
        >
          ×
        </button>
      </div>
      {inner}
    </div>
  );
}

function parseFlagValue(text: string): boolean | string | number {
  const trimmed = text.trim();
  if (trimmed === "true") return true;
  if (trimmed === "false") return false;
  const num = Number(trimmed);
  if (!Number.isNaN(num) && trimmed !== "") return num;
  return trimmed;
}
