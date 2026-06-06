"use client";

import { useParams } from "next/navigation";
import { useTranslations } from "next-intl";
import { useCallback, useMemo } from "react";

import { CluesEditor } from "@/components/admin/editor/CluesEditor";
import { DraftEditorShell } from "@/components/admin/editor/DraftEditorShell";
import { ImageField } from "@/components/admin/editor/fields/ImageField";
import { EditorSection } from "@/components/admin/editor/EditorSection";
import { JsonField } from "@/components/admin/editor/JsonField";
import { RepeaterCard } from "@/components/admin/editor/RepeaterCard";
import { CharacterPicker } from "@/components/admin/editor/fields/CharacterPicker";
import { SegmentedControl } from "@/components/admin/editor/fields/SegmentedControl";
import { StarRating } from "@/components/admin/editor/fields/StarRating";
import { StructuredEffectsField } from "@/components/admin/editor/StructuredEffectsField";
import { StructuredTriggerField } from "@/components/admin/editor/StructuredTriggerField";
import { ScriptPreviewPane } from "@/components/admin/editor/preview/ScriptPreviewPane";
import { FormField } from "@/components/ui/FormField";
import {
  ENDING_TYPES,
  emptyEnding,
  emptyEvent,
  isKnownEndingType,
} from "@/lib/draft-schemas";
import type {
  AdminScriptDraftDetail,
  EndingDraft,
  EventDraft,
  ScriptDraftPayload,
  WorldPlayableCharacterRef,
} from "@/lib/types";

type Detail = AdminScriptDraftDetail;
type Payload = ScriptDraftPayload;

export default function AdminScriptDraftPage() {
  const { id } = useParams<{ id: string }>();
  const t = useTranslations("admin.editor");
  const ts = useTranslations("admin.editor.script");

  const buildRail = useCallback(
    (payload: Payload) => [
      { id: "section-basic", label: ts("sections.basic") },
      {
        id: "section-playable",
        label: ts("sections.playable"),
        count: payload.playable_character_ids?.length ?? 0,
      },
      { id: "section-truth", label: ts("sections.truth") },
      { id: "section-events", label: ts("sections.events"), count: payload.events.length },
      {
        id: "section-clues",
        label: ts("sections.clues"),
        count: Object.keys(payload.clues).length,
      },
      { id: "section-endings", label: ts("sections.endings"), count: payload.endings.length },
    ],
    [ts],
  );

  return (
    <DraftEditorShell<Payload, Detail>
      draftId={id}
      kind="script"
      modeGlyph="◆"
      backTo="/workshop"
      endpoints={{
        detail: (i) => `/api/workshop/script-drafts/${i}`,
        publish: (i) => `/api/workshop/script-drafts/${i}/save-private`,
        stream: (taskId, seq) =>
          `/api/workshop/generation-tasks/${taskId}/stream?after_seq=${seq}`,
      }}
      selectPayload={(d) => d.payload}
      buildRail={buildRail}
      getTitle={(p) => p.name || t("preview.untitledScript")}
      generationOperationLabel="剧本生成中"
      generationSubjectLabel={(p) => (p.name ? `《${p.name}》` : "AI 自动构思中")}
      renderPreview={(p) => <ScriptPreviewPane payload={p} />}
      renderBody={({ payload, setPayload, detail, draftId, saveNow }) => (
        <ScriptEditorBody
          payload={payload}
          setPayload={setPayload}
          worldCharacters={detail.world_playable_characters}
          draftId={draftId}
          saveNow={saveNow}
        />
      )}
    />
  );
}

interface BodyProps {
  payload: Payload;
  setPayload: (updater: (current: Payload) => Payload) => void;
  worldCharacters: WorldPlayableCharacterRef[];
  draftId: string;
  saveNow: () => Promise<void>;
}

function ScriptEditorBody({ payload, setPayload, worldCharacters, draftId, saveNow }: BodyProps) {
  const ts = useTranslations("admin.editor.script");
  const tSection = useTranslations("admin.editor.section");
  const tCovers = useTranslations("admin.editor.covers");

  // 推断"已知"列表，给结构化字段填补 dropdown
  const knownClueIds = useMemo(() => Object.keys(payload.clues), [payload.clues]);
  // events / endings 不知道 world locations / npcs；服务端没把世界数据塞进 script detail。
  // 因此 location / npc 只允许自定义文本，dropdown 留空但仍可输入。
  const knownLocations: string[] = [];
  const knownNpcs: string[] = [];

  const set = <K extends keyof Payload>(key: K, value: Payload[K]) =>
    setPayload((c) => ({ ...c, [key]: value }));

  return (
    <>
      <EditorSection
        id="section-basic"
        index={1}
        eyebrow="Script"
        title={ts("sections.basic")}
      >
        <div style={{ maxWidth: 480 }}>
          <ImageField
            url={payload.cover_image}
            onChange={(u) => set("cover_image", u)}
            variant="cover"
            label={tCovers("cover")}
            aspectRatio="3 / 2"
            draftId={draftId}
            draftKind="script"
            regenTarget="cover"
            beforeRegenerate={saveNow}
          />
        </div>
        <FormField
          label={ts("basic.name")}
          required
          value={payload.name}
          onChange={(e) => set("name", e.target.value)}
          placeholder={ts("basic.namePlaceholder")}
        />
        <FormField
          label={ts("basic.summary")}
          multiline
          rows={3}
          value={payload.description}
          onChange={(e) => set("description", e.target.value)}
          placeholder={ts("basic.summaryPlaceholder")}
        />
        <div
          style={{
            display: "grid",
            gap: "var(--lv-s-4)",
            gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
          }}
        >
          <FormField
            label={ts("basic.duration")}
            value={payload.estimated_time}
            onChange={(e) => set("estimated_time", e.target.value)}
          />
          <StarRating
            label={ts("basic.difficulty")}
            value={payload.difficulty}
            onChange={(v) => set("difficulty", v)}
          />
        </div>
      </EditorSection>

      <EditorSection
        id="section-playable"
        index={2}
        eyebrow="Script"
        title={ts("sections.playable")}
        meta={payload.playable_character_ids?.length ?? 0}
      >
        <p className="lv-t-meta" style={{ color: "var(--lv-ink-3)", margin: 0 }}>
          {ts("playable.hint")}
        </p>
        <CharacterPicker
          characters={worldCharacters}
          selectedIds={payload.playable_character_ids ?? []}
          onChange={(ids) => set("playable_character_ids", ids)}
          emptyHint={ts("playable.empty")}
        />
      </EditorSection>

      <EditorSection
        id="section-truth"
        index={3}
        eyebrow="Script"
        title={ts("sections.truth")}
      >
        <FormField
          label={ts("truth.label")}
          multiline
          rows={8}
          value={payload.script_setting}
          onChange={(e) => set("script_setting", e.target.value)}
          placeholder={ts("truth.placeholder")}
        />
      </EditorSection>

      <EditorSection
        id="section-events"
        index={4}
        eyebrow="Script"
        title={ts("sections.events")}
        meta={payload.events.length}
        action={
          <button
            type="button"
            className="lv-btn lv-btn-sm"
            onClick={() => setPayload((c) => ({ ...c, events: [emptyEvent(), ...c.events] }))}
          >
            {ts("events.addCta")}
          </button>
        }
      >
        {payload.events.length === 0 && <EmptyHint>{ts("events.empty")}</EmptyHint>}
        {payload.events.map((event, index) => (
          <EventEditor
            key={`evt-${index}`}
            event={event}
            knownClueIds={knownClueIds}
            knownLocations={knownLocations}
            knownNpcs={knownNpcs}
            removeLabel={tSection("removeOne")}
            onChange={(next) =>
              setPayload((c) => ({
                ...c,
                events: c.events.map((it, i) => (i === index ? next : it)),
              }))
            }
            onRemove={() =>
              setPayload((c) => ({
                ...c,
                events: c.events.filter((_, i) => i !== index),
              }))
            }
          />
        ))}
      </EditorSection>

      <EditorSection
        id="section-clues"
        index={5}
        eyebrow="Script"
        title={ts("sections.clues")}
        meta={Object.keys(payload.clues).length}
      >
        <CluesEditor clues={payload.clues} onChange={(next) => set("clues", next)} />
      </EditorSection>

      <EditorSection
        id="section-endings"
        index={6}
        eyebrow="Script"
        title={ts("sections.endings")}
        meta={payload.endings.length}
        action={
          <button
            type="button"
            className="lv-btn lv-btn-sm"
            onClick={() =>
              setPayload((c) => ({ ...c, endings: [emptyEnding(), ...c.endings] }))
            }
          >
            {ts("endings.addCta")}
          </button>
        }
      >
        {payload.endings.length === 0 && <EmptyHint>{ts("endings.empty")}</EmptyHint>}
        {payload.endings.map((ending, index) => (
          <EndingEditor
            key={`end-${index}`}
            ending={ending}
            removeLabel={tSection("removeOne")}
            onChange={(next) =>
              setPayload((c) => ({
                ...c,
                endings: c.endings.map((it, i) => (i === index ? next : it)),
              }))
            }
            onRemove={() =>
              setPayload((c) => ({
                ...c,
                endings: c.endings.filter((_, i) => i !== index),
              }))
            }
          />
        ))}
      </EditorSection>
    </>
  );
}

function EmptyHint({ children }: { children: React.ReactNode }) {
  return (
    <div
      className="lv-t-meta"
      style={{
        padding: "var(--lv-s-8) var(--lv-s-4)",
        border: "1px dashed var(--lv-line)",
        borderRadius: "var(--lv-r-card)",
        color: "var(--lv-ink-3)",
        textAlign: "center",
      }}
    >
      {children}
    </div>
  );
}

interface EventEditorProps {
  event: EventDraft;
  knownClueIds: string[];
  knownLocations: string[];
  knownNpcs: string[];
  removeLabel: string;
  onChange: (next: EventDraft) => void;
  onRemove: () => void;
}

function EventEditor({
  event,
  knownClueIds,
  knownLocations,
  knownNpcs,
  removeLabel,
  onChange,
  onRemove,
}: EventEditorProps) {
  const ts = useTranslations("admin.editor.script.events");
  const tt = useTranslations("admin.editor.script.trigger");

  const triggerLabel = (() => {
    try {
      return tt(event.trigger_type);
    } catch {
      return event.trigger_type;
    }
  })();

  return (
    <RepeaterCard
      title={event.name || ts("untitled")}
      subtitle={event.description?.trim() || ts("descFallback")}
      badges={
        <span
          className="lv-t-caps"
          style={{
            padding: "2px 8px",
            borderRadius: "var(--lv-r-pill)",
            border: "1px solid var(--lv-line)",
            color: "var(--lv-ink-3)",
          }}
        >
          {triggerLabel}
        </span>
      }
      trailingMeta={event.priority ? `p${event.priority}` : undefined}
      onRemove={onRemove}
      removeLabel={removeLabel}
    >
      <FormField
        label={ts("name")}
        value={event.name}
        onChange={(e) => onChange({ ...event, name: e.target.value })}
        placeholder={ts("namePlaceholder")}
      />
      <FormField
        label={ts("description")}
        multiline
        rows={3}
        value={event.description}
        onChange={(e) => onChange({ ...event, description: e.target.value })}
        placeholder={ts("descriptionPlaceholder")}
      />

      <div>
        <div className="lv-form-label">{ts("triggerType")}</div>
        <StructuredTriggerField
          triggerType={event.trigger_type}
          triggerCondition={event.trigger_condition}
          knownClueIds={knownClueIds}
          knownLocations={knownLocations}
          onChange={({ trigger_type, trigger_condition }) =>
            onChange({ ...event, trigger_type, trigger_condition })
          }
        />
      </div>

      <div>
        <div className="lv-form-label">{ts("effects")}</div>
        <StructuredEffectsField
          effects={event.effects}
          knownClueIds={knownClueIds}
          knownLocations={knownLocations}
          knownNpcs={knownNpcs}
          onChange={(next) => onChange({ ...event, effects: next })}
        />
      </div>

      <FormField
        label={ts("priority")}
        help={ts("priorityHelp")}
        type="number"
        value={event.priority ?? 0}
        onChange={(e) => onChange({ ...event, priority: Number(e.target.value || 0) })}
      />
    </RepeaterCard>
  );
}

interface EndingEditorProps {
  ending: EndingDraft;
  removeLabel: string;
  onChange: (next: EndingDraft) => void;
  onRemove: () => void;
}

function EndingEditor({ ending, removeLabel, onChange, onRemove }: EndingEditorProps) {
  const ts = useTranslations("admin.editor.script.endings");
  const tEndType = useTranslations("admin.editor.script.endingType");

  const typeLabel = isKnownEndingType(ending.ending_type)
    ? tEndType(ending.ending_type)
    : ending.ending_type;

  return (
    <RepeaterCard
      title={ending.title || ts("untitled")}
      badges={
        <span
          className="lv-t-caps"
          style={{
            padding: "2px 8px",
            borderRadius: "var(--lv-r-pill)",
            border: "1px solid var(--lv-line)",
            color: "var(--lv-ink-3)",
          }}
        >
          {typeLabel}
        </span>
      }
      trailingMeta={ending.priority ? `p${ending.priority}` : undefined}
      onRemove={onRemove}
      removeLabel={removeLabel}
    >
      <div
        style={{
          display: "grid",
          gap: "var(--lv-s-4)",
          gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
        }}
      >
        <FormField
          label={ts("title")}
          value={ending.title}
          onChange={(e) => onChange({ ...ending, title: e.target.value })}
          placeholder={ts("titlePlaceholder")}
        />
        <SegmentedControl
          label={ts("type")}
          value={ending.ending_type}
          options={ENDING_TYPES.map((tp) => ({ value: tp, label: tEndType(tp) }))}
          onChange={(next) => onChange({ ...ending, ending_type: next })}
        />
      </div>
      <FormField
        label={ts("description")}
        multiline
        rows={4}
        value={ending.description}
        onChange={(e) => onChange({ ...ending, description: e.target.value })}
        placeholder={ts("descriptionPlaceholder")}
      />

      <div
        style={{
          display: "grid",
          gap: "var(--lv-s-4)",
          gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
        }}
      >
        <FormField
          label={ts("softCondition")}
          value={ending.soft_conditions ?? ""}
          onChange={(e) => onChange({ ...ending, soft_conditions: e.target.value })}
          placeholder={ts("softConditionPlaceholder")}
        />
        <JsonField<Record<string, unknown> | null>
          label={ts("hardCondition")}
          value={ending.hard_conditions ?? null}
          onChange={(next) => onChange({ ...ending, hard_conditions: next })}
          rows={4}
        />
      </div>
      <FormField
        label={ts("priority")}
        type="number"
        value={ending.priority ?? 0}
        onChange={(e) => onChange({ ...ending, priority: Number(e.target.value || 0) })}
      />
    </RepeaterCard>
  );
}
