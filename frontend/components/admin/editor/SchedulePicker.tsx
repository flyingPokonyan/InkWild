"use client";

import { useTranslations } from "next-intl";

import { TIME_SLOTS } from "@/lib/draft-schemas";

import { SelectField } from "./fields/SelectField";

interface SchedulePickerProps {
  schedule: Record<string, string>;
  knownLocations: string[];
  onChange: (next: Record<string, string>) => void;
}

/**
 * 日常时间表：5 时段 × 一个地点。地点优先从已有 locations 选，允许自定义。
 */
export function SchedulePicker({ schedule, knownLocations, onChange }: SchedulePickerProps) {
  const t = useTranslations("admin.editor.schedule");

  const setSlot = (slot: string, value: string) => {
    onChange({ ...schedule, [slot]: value });
  };

  return (
    <div
      style={{
        display: "grid",
        gap: "var(--lv-s-3)",
        gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
      }}
    >
      {TIME_SLOTS.map((slot) => (
        <div key={slot} style={{ display: "flex", flexDirection: "column", gap: "var(--lv-s-2)" }}>
          <span className="lv-t-caps" style={{ color: "var(--lv-ink-3)" }}>
            {t(slot)}
          </span>
          <SelectField
            value={schedule[slot] ?? ""}
            onChange={(next) => setSlot(slot, next)}
            options={knownLocations.map((l) => ({ value: l, label: l }))}
            allowCustom
            placeholder={t("placeholder")}
          />
        </div>
      ))}
    </div>
  );
}
