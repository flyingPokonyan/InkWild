"use client";

import { useTranslations } from "next-intl";

import { FormField } from "@/components/ui/FormField";
import {
  TIME_SLOTS,
  TRIGGER_TYPES,
  defaultTriggerCondition,
  isKnownTriggerType,
  type TriggerType,
} from "@/lib/draft-schemas";

import { SegmentedControl } from "./fields/SegmentedControl";
import { SelectField } from "./fields/SelectField";
import { JsonField } from "./JsonField";

interface StructuredTriggerFieldProps {
  triggerType: string;
  triggerCondition: Record<string, unknown>;
  /** 世界中已知的地点列表，用于 location 触发器的下拉 */
  knownLocations: string[];
  /** 当前剧本的 clue id 列表，用于 clue 触发器的下拉 */
  knownClueIds: string[];
  onChange: (next: { trigger_type: string; trigger_condition: Record<string, unknown> }) => void;
}

export function StructuredTriggerField({
  triggerType,
  triggerCondition,
  knownLocations,
  knownClueIds,
  onChange,
}: StructuredTriggerFieldProps) {
  const t = useTranslations("admin.editor.script.trigger");

  const setType = (next: string) => {
    onChange({ trigger_type: next, trigger_condition: defaultTriggerCondition(next) });
  };

  const setCondition = (next: Record<string, unknown>) => {
    onChange({ trigger_type: triggerType, trigger_condition: next });
  };

  const patch = (partial: Record<string, unknown>) => {
    setCondition({ ...triggerCondition, ...partial });
  };

  const known = isKnownTriggerType(triggerType);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--lv-s-4)" }}>
      <SegmentedControl
        label={t.raw("triggerType") as string | undefined ?? "Trigger"}
        value={triggerType}
        onChange={setType}
        options={TRIGGER_TYPES.map((tt) => ({ value: tt, label: t(tt) }))}
      />

      {known && (
        <div style={{ display: "grid", gap: "var(--lv-s-3)", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))" }}>
          {renderKnownInputs(triggerType as TriggerType, triggerCondition, patch, t, knownLocations, knownClueIds)}
        </div>
      )}

      <JsonField<Record<string, unknown>>
        value={triggerCondition}
        onChange={(next) => setCondition(next ?? {})}
        rows={5}
        collapsible
        defaultOpen={!known}
        summary={t("advanced")}
        summaryOpen={t("advancedHelp")}
      />
    </div>
  );
}

type Tt = ReturnType<typeof useTranslations>;

function renderKnownInputs(
  type: TriggerType,
  cond: Record<string, unknown>,
  patch: (p: Record<string, unknown>) => void,
  t: Tt,
  knownLocations: string[],
  knownClueIds: string[],
) {
  switch (type) {
    case "time": {
      const day = typeof cond.day === "number" ? cond.day : Number(cond.day) || 1;
      const slot = typeof cond.slot === "string" ? cond.slot : TIME_SLOTS[0];
      return (
        <>
          <FormField
            label={t("timeDay")}
            type="number"
            min={1}
            value={day}
            onChange={(e) => patch({ day: Math.max(1, Number(e.target.value || 1)) })}
          />
          <SelectField
            label={t("timeSlot")}
            value={slot}
            onChange={(next) => patch({ slot: next })}
            options={TIME_SLOTS.map((s) => ({ value: s, label: s }))}
          />
        </>
      );
    }
    case "clue": {
      const clueId = typeof cond.clue_id === "string" ? cond.clue_id : "";
      return (
        <SelectField
          label={t("clueId")}
          help={t("clueIdHelp")}
          value={clueId}
          onChange={(next) => patch({ clue_id: next })}
          allowCustom
          options={knownClueIds.map((c) => ({ value: c, label: c }))}
          placeholder={knownClueIds.length === 0 ? t("clueIdHelp") : undefined}
        />
      );
    }
    case "location": {
      const loc = typeof cond.location === "string" ? cond.location : "";
      return (
        <SelectField
          label={t("locationName")}
          help={t("locationFromList")}
          value={loc}
          onChange={(next) => patch({ location: next })}
          allowCustom
          options={knownLocations.map((l) => ({ value: l, label: l }))}
          placeholder={knownLocations.length === 0 ? t("locationFromList") : undefined}
        />
      );
    }
    case "clue_count": {
      const count = typeof cond.count === "number" ? cond.count : Number(cond.count) || 1;
      return (
        <FormField
          label={t("clueCountThreshold")}
          type="number"
          min={1}
          value={count}
          onChange={(e) => patch({ count: Math.max(1, Number(e.target.value || 1)) })}
        />
      );
    }
    case "rounds_without_progress": {
      const rounds = typeof cond.rounds === "number" ? cond.rounds : Number(cond.rounds) || 3;
      return (
        <FormField
          label={t("roundsThreshold")}
          type="number"
          min={1}
          value={rounds}
          onChange={(e) => patch({ rounds: Math.max(1, Number(e.target.value || 3)) })}
        />
      );
    }
  }
}
