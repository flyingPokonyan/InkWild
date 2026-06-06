"use client";

import type { WorldPlayableCharacterRef } from "@/lib/types";

interface CharacterPickerProps {
  label?: string;
  /** 候选可玩角色（来自所属世界）。 */
  characters: WorldPlayableCharacterRef[];
  /** 已选中的 WorldCharacter id。 */
  selectedIds: string[];
  onChange: (next: string[]) => void;
  emptyHint?: string;
}

/**
 * 剧本可玩角色多选清单：头像 + 名字网格，点选 toggle。
 * 不选 = 放行世界全部可玩角色。touch ≥ 44px，选中态走 ink 不用 accent。
 */
export function CharacterPicker({
  label,
  characters,
  selectedIds,
  onChange,
  emptyHint,
}: CharacterPickerProps) {
  const selected = new Set(selectedIds);

  const toggle = (id: string) => {
    const next = new Set(selected);
    if (next.has(id)) {
      next.delete(id);
    } else {
      next.add(id);
    }
    // 维持候选顺序，输出稳定。
    onChange(characters.filter((c) => next.has(c.id)).map((c) => c.id));
  };

  if (characters.length === 0) {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: "var(--lv-s-2)" }}>
        {label && <span className="lv-form-label">{label}</span>}
        <div
          className="lv-t-meta"
          style={{
            padding: "var(--lv-s-6) var(--lv-s-4)",
            border: "1px dashed var(--lv-line)",
            borderRadius: "var(--lv-r-card)",
            color: "var(--lv-ink-3)",
            textAlign: "center",
          }}
        >
          {emptyHint ?? "该世界暂无可玩角色"}
        </div>
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--lv-s-2)" }}>
      {label && <span className="lv-form-label">{label}</span>}
      <div
        role="group"
        aria-label={label}
        style={{
          display: "grid",
          gap: 8,
          gridTemplateColumns: "repeat(auto-fill, minmax(140px, 1fr))",
        }}
      >
        {characters.map((character) => {
          const isOn = selected.has(character.id);
          return (
            <button
              key={character.id}
              type="button"
              role="checkbox"
              aria-checked={isOn}
              onClick={() => toggle(character.id)}
              className="lv-t-meta"
              style={{
                display: "flex",
                alignItems: "center",
                gap: 10,
                minHeight: 44,
                padding: "8px 12px",
                borderRadius: "var(--lv-r-card)",
                border: "1px solid",
                borderColor: isOn ? "var(--lv-line-2)" : "var(--lv-line)",
                background: isOn ? "rgba(255,255,255,0.07)" : "transparent",
                color: isOn ? "var(--lv-ink)" : "var(--lv-ink-3)",
                cursor: "pointer",
                transition: "all var(--lv-dur-fast) var(--lv-ease)",
                textAlign: "left",
              }}
            >
              <Avatar avatar={character.avatar} name={character.name} dim={!isOn} />
              <span
                style={{
                  flex: 1,
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "nowrap",
                }}
              >
                {character.name}
              </span>
              <span aria-hidden style={{ opacity: isOn ? 1 : 0.25 }}>
                {isOn ? "✓" : "+"}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}

function Avatar({ avatar, name, dim }: { avatar: string | null; name: string; dim: boolean }) {
  const size = 28;
  if (avatar) {
    return (
      // eslint-disable-next-line @next/next/no-img-element
      <img
        src={avatar}
        alt=""
        width={size}
        height={size}
        style={{
          width: size,
          height: size,
          borderRadius: "var(--lv-r-pill)",
          objectFit: "cover",
          flexShrink: 0,
          opacity: dim ? 0.7 : 1,
        }}
      />
    );
  }
  return (
    <span
      aria-hidden
      style={{
        width: size,
        height: size,
        borderRadius: "var(--lv-r-pill)",
        flexShrink: 0,
        display: "grid",
        placeItems: "center",
        background: "rgba(255,255,255,0.06)",
        border: "1px solid var(--lv-line)",
        fontSize: 12,
      }}
    >
      {name.slice(0, 1)}
    </span>
  );
}
