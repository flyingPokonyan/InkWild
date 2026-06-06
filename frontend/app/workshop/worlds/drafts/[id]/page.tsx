"use client";

import { useParams } from "next/navigation";
import { useTranslations } from "next-intl";
import { useMemo } from "react";

import { DraftEditorShell } from "@/components/admin/editor/DraftEditorShell";
import { ImageField } from "@/components/admin/editor/fields/ImageField";
import { EditorSection } from "@/components/admin/editor/EditorSection";
import { ResearchPackSection } from "@/components/admin/editor/sections/ResearchPackSection";
import type { ResearchPackData } from "@/components/admin/editor/sections/ResearchPackSection";
import { LorePackSection } from "@/components/admin/editor/sections/LorePackSection";
import type { LorePackData } from "@/components/admin/editor/sections/LorePackSection";
import { SharedEventsSection } from "@/components/admin/editor/sections/SharedEventsSection";
import type { SharedEventsData } from "@/components/admin/editor/sections/SharedEventsSection";
import { EventsDataSection } from "@/components/admin/editor/sections/EventsDataSection";
import type { EventsDataList } from "@/components/admin/editor/sections/EventsDataSection";
import { RelationsPackSection } from "@/components/admin/editor/sections/RelationsPackSection";
import type { RelationsPackData } from "@/components/admin/editor/sections/RelationsPackSection";
import { RepeaterCard } from "@/components/admin/editor/RepeaterCard";
import { ChipsInput } from "@/components/admin/editor/fields/ChipsInput";
import { FocusExpandTextarea } from "@/components/admin/editor/fields/FocusExpandTextarea";
import { SelectField } from "@/components/admin/editor/fields/SelectField";
import { StarRating } from "@/components/admin/editor/fields/StarRating";
import { SchedulePicker } from "@/components/admin/editor/SchedulePicker";
import { WorldPreviewPane } from "@/components/admin/editor/preview/WorldPreviewPane";
import { FormField } from "@/components/ui/FormField";
import { emptyLocation, emptyNpc, emptyPlayable } from "@/lib/draft-schemas";
import type { AdminWorldDraftDetail, LocationDraft, WorldCharacterDraft, WorldDraftPayload } from "@/lib/types";

type Detail = AdminWorldDraftDetail;
type Payload = WorldDraftPayload;

export default function AdminWorldDraftPage() {
  const { id } = useParams<{ id: string }>();
  const t = useTranslations("admin.editor");
  const tw = useTranslations("admin.editor.world");

  const buildRail = useMemo(
    () => (payload: Payload) => [
      { id: "section-basic", label: tw("sections.basic") },
      { id: "section-setting", label: tw("sections.setting") },
      { id: "section-locations", label: tw("sections.locations"), count: payload.locations.length },
      {
        id: "section-characters",
        label: tw("sections.characters"),
        count: payload.world_characters.length,
      },
    ],
    [tw],
  );

  return (
    <DraftEditorShell<Payload, Detail>
      draftId={id}
      kind="world"
      backTo="/workshop"
      endpoints={{
        detail: (i) => `/api/workshop/world-drafts/${i}`,
        publish: (i) => `/api/workshop/world-drafts/${i}/save-private`,
        stream: (taskId, seq) =>
          `/api/workshop/generation-tasks/${taskId}/stream?after_seq=${seq}`,
        continueGeneration: (i) =>
          `/api/workshop/world-drafts/${i}/continue-generation`,
      }}
      selectPayload={(d) => d.payload}
      buildRail={buildRail}
      getTitle={(p) => p.name || t("preview.untitledWorld")}
      generationOperationLabel="世界生成中"
      generationSubjectLabel={(p) => (p.name ? `概念：${p.name}` : "AI 正在整理世界概念")}
      renderPreview={(p) => <WorldPreviewPane payload={p} />}
      renderBody={({ payload, setPayload, draftId, saveNow }) => (
        <WorldEditorBody
          payload={payload}
          setPayload={setPayload}
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
  draftId: string;
  saveNow: () => Promise<void>;
}

function WorldEditorBody({ payload, setPayload, draftId, saveNow }: BodyProps) {
  const tw = useTranslations("admin.editor.world");
  const tCovers = useTranslations("admin.editor.covers");

  const set = <K extends keyof Payload>(key: K, value: Payload[K]) =>
    setPayload((c) => ({ ...c, [key]: value }));

  const knownLocations = payload.locations.map((l) => l.name).filter(Boolean);

  // research_pack, lore_pack, shared_events, events_data, relations_pack are written by
  // the v2 world creator agent into intermediate_state, and will be included in
  // draft.payload once the backend normalizer is updated.
  // We read them defensively via an intersection cast.
  type ExtendedPayload = Payload & {
    research_pack?: ResearchPackData;
    lore_pack?: LorePackData;
    shared_events?: SharedEventsData;
    events_data?: EventsDataList;
    relations_pack?: RelationsPackData;
  };
  const ext = payload as ExtendedPayload;
  const researchPack = ext.research_pack;
  const lorePack = ext.lore_pack;
  const sharedEvents = ext.shared_events;
  const eventsData = ext.events_data;
  const relationsPack = ext.relations_pack;

  const hasIntermediate = Boolean(
    researchPack || lorePack || sharedEvents || eventsData || relationsPack,
  );

  return (
    <>
      <EditorSection
        id="section-basic"
        index={1}
        eyebrow="World"
        title={tw("sections.basic")}
      >
        <div
          className="world-draft-image-grid"
          style={{ display: "flex", gap: "var(--lv-s-3)", alignItems: "flex-start", width: "100%" }}
        >
          <div style={{ flex: "2.333 1 0", minWidth: 0 }}>
            <ImageField
              url={payload.hero_image}
              onChange={(u) => set("hero_image", u ?? "")}
              variant="cover"
              label={tCovers("hero")}
              aspectRatio="21 / 9"
              draftId={draftId}
              draftKind="world"
              regenTarget="hero"
              beforeRegenerate={saveNow}
            />
          </div>
          <div style={{ flex: "1.5 1 0", minWidth: 0 }}>
            <ImageField
              url={payload.cover_image}
              onChange={(u) => set("cover_image", u ?? "")}
              variant="cover"
              label={tCovers("cover")}
              aspectRatio="3 / 2"
              draftId={draftId}
              draftKind="world"
              regenTarget="cover"
              beforeRegenerate={saveNow}
            />
          </div>
        </div>
        <style jsx>{`
          @media (max-width: 767px) {
            .world-draft-image-grid {
              flex-direction: column;
            }

            .world-draft-image-grid > div {
              width: 100%;
              flex: none !important;
            }
          }
        `}</style>

        <div
          style={{
            display: "grid",
            gap: "var(--lv-s-4)",
            gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
          }}
        >
          <div style={{ gridColumn: "1 / -1" }}>
            <FormField
              label={tw("basic.name")}
              required
              value={payload.name}
              onChange={(e) => set("name", e.target.value)}
              placeholder={tw("basic.namePlaceholder")}
            />
          </div>
          <div style={{ gridColumn: "1 / -1" }}>
            <FormField
              label={tw("basic.summary")}
              multiline
              rows={2}
              value={payload.description}
              onChange={(e) => set("description", e.target.value)}
              placeholder={tw("basic.summaryPlaceholder")}
            />
          </div>
          <FormField
            label={tw("basic.genre")}
            value={payload.genre}
            onChange={(e) => set("genre", e.target.value)}
            placeholder={tw("basic.genrePlaceholder")}
          />
          <FormField
            label={tw("basic.era")}
            value={payload.era}
            onChange={(e) => set("era", e.target.value)}
            placeholder={tw("basic.eraPlaceholder")}
          />
          <FormField
            label={tw("basic.duration")}
            value={payload.estimated_time}
            onChange={(e) => set("estimated_time", e.target.value)}
            placeholder={tw("basic.durationPlaceholder")}
          />
          <StarRating
            label={tw("basic.difficulty")}
            value={payload.difficulty}
            onChange={(v) => set("difficulty", v)}
          />
        </div>
      </EditorSection>

      <EditorSection
        id="section-setting"
        index={2}
        eyebrow="World"
        title={tw("sections.setting")}
      >
        <FormField
          label={tw("setting.base")}
          multiline
          rows={6}
          value={payload.base_setting}
          onChange={(e) => set("base_setting", e.target.value)}
          placeholder={tw("setting.basePlaceholder")}
        />
        <FormField
          label={tw("setting.free")}
          help={tw("setting.freeHelp")}
          multiline
          rows={4}
          value={payload.free_setting}
          onChange={(e) => set("free_setting", e.target.value)}
          placeholder={tw("setting.freePlaceholder")}
        />
      </EditorSection>

      <EditorSection
        id="section-locations"
        index={3}
        eyebrow="World"
        title={tw("sections.locations")}
        meta={payload.locations.length}
        action={
          <button
            type="button"
            className="lv-btn lv-btn-sm"
            onClick={() =>
              setPayload((c) => ({ ...c, locations: [emptyLocation(), ...c.locations] }))
            }
          >
            {tw("locations.addCta")}
          </button>
        }
      >
        {payload.locations.length === 0 && <EmptyHint>{tw("locations.empty")}</EmptyHint>}
        {payload.locations.map((loc, index) => (
          <LocationRow
            key={`loc-${index}`}
            value={loc}
            onChange={(next) =>
              setPayload((c) => ({
                ...c,
                locations: c.locations.map((it, i) => (i === index ? next : it)),
              }))
            }
            onRemove={() =>
              setPayload((c) => ({
                ...c,
                locations: c.locations.filter((_, i) => i !== index),
              }))
            }
          />
        ))}
      </EditorSection>

      <EditorSection
        id="section-characters"
        index={4}
        eyebrow="World"
        title={tw("sections.characters")}
        meta={payload.world_characters.length}
        action={
          <div style={{ display: "flex", gap: "var(--lv-s-2)" }}>
            <button
              type="button"
              className="lv-btn lv-btn-sm"
              onClick={() =>
                setPayload((c) => ({
                  ...c,
                  world_characters: [...c.world_characters, emptyNpc()],
                }))
              }
            >
              {tw("characters.addNpcCta")}
            </button>
            <button
              type="button"
              className="lv-btn lv-btn-sm"
              onClick={() =>
                setPayload((c) => ({
                  ...c,
                  world_characters: [...c.world_characters, emptyPlayable()],
                }))
              }
            >
              {tw("characters.addPlayableCta")}
            </button>
          </div>
        }
      >
        {payload.world_characters.length === 0 && (
          <EmptyHint>{tw("characters.empty")}</EmptyHint>
        )}
        {sortedCharacters(payload.world_characters).map(({ char, originalIndex }) => (
          <WorldCharacterEditor
            key={`wc-${originalIndex}`}
            character={char}
            knownLocations={knownLocations}
            draftId={draftId}
            saveNow={saveNow}
            onChange={(next) =>
              setPayload((c) => ({
                ...c,
                world_characters: c.world_characters.map((it, i) =>
                  i === originalIndex ? next : it,
                ),
              }))
            }
            onRemove={() =>
              setPayload((c) => ({
                ...c,
                world_characters: c.world_characters.filter((_, i) => i !== originalIndex),
              }))
            }
          />
        ))}
      </EditorSection>

      {hasIntermediate && (
        <details
          style={{
            marginTop: "var(--lv-s-8)",
            borderTop: "1px solid var(--lv-line-2)",
            paddingTop: "var(--lv-s-6)",
          }}
        >
          <summary
            className="lv-t-caps"
            style={{
              cursor: "pointer",
              color: "var(--lv-ink-3)",
              listStyle: "none",
              display: "inline-flex",
              alignItems: "center",
              gap: "var(--lv-s-2)",
              minHeight: 44,
              userSelect: "none",
            }}
          >
            <span aria-hidden>▸</span>
            AI 生成中间产物（只读）
          </summary>
          <div
            style={{
              marginTop: "var(--lv-s-4)",
              display: "flex",
              flexDirection: "column",
              gap: "var(--lv-s-6)",
            }}
          >
            <ResearchPackSection researchPack={researchPack} />
            <LorePackSection lorePack={lorePack} />
            <SharedEventsSection sharedEvents={sharedEvents} />
            <EventsDataSection eventsData={eventsData} />
            <RelationsPackSection relationsPack={relationsPack} />
          </div>
        </details>
      )}
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

function sortedCharacters(list: WorldCharacterDraft[]) {
  return list
    .map((char, originalIndex) => ({ char, originalIndex }))
    .sort((a, b) => {
      if (a.char.playable && !b.char.playable) return -1;
      if (!a.char.playable && b.char.playable) return 1;
      return 0;
    });
}

interface LocationRowProps {
  value: LocationDraft;
  onChange: (next: LocationDraft) => void;
  onRemove: () => void;
}
function LocationRow({ value, onChange, onRemove }: LocationRowProps) {
  const tw = useTranslations("admin.editor.world.locations");
  return (
    <div
      style={{
        position: "relative",
        padding: "var(--lv-s-3) var(--lv-s-4)",
        paddingRight: 44,
        background: "var(--lv-bg-1)",
        border: "1px solid var(--lv-line)",
        borderRadius: "var(--lv-r-card)",
        transition: "border-color var(--lv-dur-fast) var(--lv-ease)",
      }}
    >
      <input
        className="lv-input lv-t-body"
        style={{
          height: 28,
          border: 0,
          background: "transparent",
          padding: 0,
          color: "var(--lv-ink)",
        }}
        value={value.name}
        placeholder={tw("namePlaceholder")}
        onChange={(e) => onChange({ ...value, name: e.target.value })}
      />
      <FocusExpandTextarea
        className="lv-input lv-t-body"
        style={{
          border: 0,
          background: "transparent",
          padding: 0,
          color: "var(--lv-ink-2)",
          width: "100%",
        }}
        value={value.description}
        placeholder={tw("descPlaceholder")}
        onChange={(e) => onChange({ ...value, description: e.target.value })}
      />
      <button
        type="button"
        onClick={onRemove}
        aria-label="删除"
        style={{
          position: "absolute",
          top: 6,
          right: 6,
          width: 32,
          height: 32,
          background: "transparent",
          border: 0,
          borderRadius: "var(--lv-r-pill)",
          color: "var(--lv-ink-4)",
          cursor: "pointer",
          fontSize: 16,
          lineHeight: 1,
          transition: "all var(--lv-dur-fast) var(--lv-ease)",
        }}
        onMouseEnter={(e) => {
          e.currentTarget.style.color = "var(--lv-danger)";
          e.currentTarget.style.background = "rgba(184,92,92,0.08)";
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.color = "var(--lv-ink-4)";
          e.currentTarget.style.background = "transparent";
        }}
      >
        ×
      </button>
    </div>
  );
}

interface WorldCharacterEditorProps {
  character: WorldCharacterDraft;
  knownLocations: string[];
  draftId: string;
  saveNow: () => Promise<void>;
  onChange: (next: WorldCharacterDraft) => void;
  onRemove: () => void;
}
function WorldCharacterEditor({
  character,
  knownLocations,
  draftId,
  saveNow,
  onChange,
  onRemove,
}: WorldCharacterEditorProps) {
  const tc = useTranslations("admin.editor.world.characters");
  const tSection = useTranslations("admin.editor.section");

  const personalityFallback = tc("personalityFallback");
  const subtitle = character.personality?.trim() || personalityFallback;

  return (
    <RepeaterCard
      title={character.name || tc("untitled")}
      subtitle={subtitle}
      badges={
        <button
          type="button"
          onClick={() => onChange({ ...character, playable: !character.playable })}
          aria-label={character.playable ? tc("unsetPlayable") : tc("setPlayable")}
          aria-pressed={character.playable}
          className="lv-t-caps"
          style={{
            padding: "4px 10px",
            borderRadius: "var(--lv-r-pill)",
            cursor: "pointer",
            transition: "all var(--lv-dur-fast) var(--lv-ease)",
            background: character.playable ? "var(--lv-accent-soft)" : "transparent",
            color: character.playable ? "var(--lv-accent)" : "var(--lv-ink-3)",
            border: character.playable
              ? "1px solid var(--lv-accent)"
              : "1px solid var(--lv-line-2)",
            whiteSpace: "nowrap",
            minHeight: 28,
            display: "inline-flex",
            alignItems: "center",
          }}
        >
          {character.playable ? `◆ ${tc("playableTag")}` : `+ ${tc("setPlayable")}`}
        </button>
      }
      leading={
        <div
          style={{
            width: 36,
            height: 36,
            borderRadius: "50%",
            background: "var(--lv-bg-2)",
            border: character.playable
              ? "2px solid var(--lv-accent)"
              : "1px solid var(--lv-line)",
            overflow: "hidden",
            display: "grid",
            placeItems: "center",
            transition: "border-color var(--lv-dur-fast) var(--lv-ease)",
          }}
        >
          {character.avatar ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={character.avatar}
              alt={character.name}
              style={{ width: "100%", height: "100%", objectFit: "cover" }}
            />
          ) : (
            <span className="lv-t-caps" style={{ color: "var(--lv-ink-4)" }}>
              {character.name ? character.name.slice(0, 1) : "?"}
            </span>
          )}
        </div>
      }
      onRemove={onRemove}
      removeLabel={tSection("removeOne")}
    >
      <div
        style={{
          display: "grid",
          gap: "var(--lv-s-4)",
          gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
        }}
      >
        <FormField
          label={tc("name")}
          value={character.name}
          onChange={(e) => onChange({ ...character, name: e.target.value })}
          placeholder={tc("namePlaceholder")}
        />
        <SelectField
          label={tc("initialLocation")}
          value={character.initial_location}
          onChange={(next) => onChange({ ...character, initial_location: next })}
          options={knownLocations.map((l) => ({ value: l, label: l }))}
          allowCustom
          placeholder={tc("initialLocationPlaceholder")}
        />
        <div style={{ gridColumn: "1 / -1" }}>
          <div className="lv-form-label">{tc("avatar")}</div>
          <div style={{ marginTop: "var(--lv-s-2)" }}>
            <ImageField
              url={character.avatar}
              onChange={(u) => onChange({ ...character, avatar: u })}
              variant="avatar"
              draftId={draftId}
              draftKind="world"
              regenTarget={`avatar:${character.name}`}
              beforeRegenerate={saveNow}
            />
          </div>
        </div>
      </div>

      <FormField
        label={tc("personality")}
        multiline
        rows={3}
        value={character.personality}
        onChange={(e) => onChange({ ...character, personality: e.target.value })}
        placeholder={tc("personalityPlaceholder")}
      />
      <FormField
        label={tc("secret")}
        multiline
        rows={3}
        value={character.secret ?? ""}
        onChange={(e) => onChange({ ...character, secret: e.target.value || null })}
        placeholder={tc("secretPlaceholder")}
      />

      <ChipsInput
        label={tc("knowledge")}
        help={tc("knowledgeHelp")}
        value={character.knowledge}
        onChange={(next) => onChange({ ...character, knowledge: next })}
        placeholder={tc("knowledgePlaceholder")}
      />

      <div>
        <div className="lv-form-label">{tc("schedule")}</div>
        <p className="lv-form-help" style={{ marginTop: 0, marginBottom: "var(--lv-s-2)" }}>
          {tc("scheduleHelp")}
        </p>
        <SchedulePicker
          schedule={character.schedule}
          knownLocations={knownLocations}
          onChange={(next) => onChange({ ...character, schedule: next })}
        />
      </div>

      <FormField
        label={tc("blurb")}
        multiline
        rows={3}
        value={character.description ?? ""}
        onChange={(e) => onChange({ ...character, description: e.target.value || null })}
        placeholder={tc("blurbPlaceholder")}
      />
      <ChipsInput
        label={tc("abilities")}
        value={character.abilities}
        onChange={(next) => onChange({ ...character, abilities: next })}
        placeholder={tc("abilitiesPlaceholder")}
      />
      <ChipsInput
        label={tc("inventory")}
        value={character.starting_inventory}
        onChange={(next) => onChange({ ...character, starting_inventory: next })}
        placeholder={tc("inventoryPlaceholder")}
      />
    </RepeaterCard>
  );
}
