import type { WorldExperiencePanelModel } from "@/lib/world-entry";

interface WorldExperiencePanelProps {
  panel: WorldExperiencePanelModel;
}

/**
 * 世界体验摘要面板。叙述当前体验线索，用 v2.2 lv-* tokens。
 */
export function WorldExperiencePanel({ panel }: WorldExperiencePanelProps) {
  return (
    <section
      style={{
        background: "var(--lv-bg-1)",
        border: "1px solid var(--lv-line)",
        borderRadius: "var(--lv-r-card)",
        padding: "var(--lv-s-6)",
      }}
    >
      <div className="lv-t-caps">{panel.eyebrow}</div>
      <h2 className="lv-t-h2" style={{ marginTop: "var(--lv-s-3)" }}>
        {panel.title}
      </h2>
      <p
        className="lv-t-narrative"
        style={{ marginTop: "var(--lv-s-3)", maxWidth: "var(--lv-max-w-read)", color: "var(--lv-ink-2)" }}
      >
        {panel.description}
      </p>
      {panel.items.length > 0 && (
        <div
          style={{
            marginTop: "var(--lv-s-4)",
            display: "grid",
            gap: "var(--lv-s-3)",
            gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
          }}
        >
          {panel.items.map((item) => (
            <div
              key={item}
              className="lv-t-body"
              style={{
                border: "1px solid var(--lv-line)",
                background: "rgba(255,255,255,0.02)",
                borderRadius: "var(--lv-r-card)",
                padding: "var(--lv-s-3) var(--lv-s-4)",
                color: "var(--lv-ink-2)",
              }}
            >
              {item}
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
