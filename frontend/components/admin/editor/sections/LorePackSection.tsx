"use client";

type ContentBlock = { heading: string; body: string };

type LoreDimension = {
  key: string;
  name: string;
  content_blocks?: ContentBlock[];
};

export type LorePackData = {
  dimensions?: LoreDimension[];
  generated_at?: string;
};

type Props = {
  lorePack?: LorePackData | null;
};

export function LorePackSection({ lorePack }: Props) {
  if (!lorePack || !lorePack.dimensions || lorePack.dimensions.length === 0) return null;

  const dims = lorePack.dimensions;

  return (
    <section
      aria-labelledby="lore-pack-heading"
      style={{
        borderRadius: "var(--lv-r-card)",
        border: "1px solid var(--lv-line-2)",
        background: "var(--lv-bg-1)",
        padding: "var(--lv-s-6)",
        display: "flex",
        flexDirection: "column",
        gap: "var(--lv-s-4)",
      }}
    >
      <header
        style={{
          display: "flex",
          alignItems: "baseline",
          justifyContent: "space-between",
          gap: "var(--lv-s-2)",
        }}
      >
        <h2
          id="lore-pack-heading"
          className="lv-t-h2"
          style={{ margin: 0, color: "var(--lv-ink)" }}
        >
          世界规则
        </h2>
        <span className="lv-t-caps" style={{ color: "var(--lv-ink-4)" }}>
          READ-ONLY · {dims.length} 个维度
        </span>
      </header>

      <ul
        style={{
          padding: 0,
          listStyle: "none",
          display: "flex",
          flexDirection: "column",
          gap: "var(--lv-s-3)",
        }}
      >
        {dims.map((dim) => (
          <li
            key={dim.key}
            style={{
              borderRadius: "var(--lv-r-card)",
              border: "1px solid var(--lv-line)",
              overflow: "hidden",
            }}
          >
            <details>
              <summary
                className="lv-t-h3"
                style={{
                  cursor: "pointer",
                  padding: "var(--lv-s-3) var(--lv-s-4)",
                  color: "var(--lv-ink)",
                  display: "flex",
                  alignItems: "center",
                  gap: "var(--lv-s-2)",
                  listStyle: "none",
                  userSelect: "none",
                }}
              >
                <span
                  className="lv-t-meta"
                  style={{ color: "var(--lv-ink-4)", minWidth: 12 }}
                  aria-hidden
                >
                  ▶
                </span>
                {dim.name}
                <span className="lv-t-meta" style={{ color: "var(--lv-ink-3)", marginLeft: "auto" }}>
                  {dim.content_blocks?.length ?? 0} 块
                </span>
              </summary>

              <div
                style={{
                  padding: "var(--lv-s-3) var(--lv-s-4)",
                  borderTop: "1px solid var(--lv-line)",
                  display: "flex",
                  flexDirection: "column",
                  gap: "var(--lv-s-3)",
                  background: "var(--lv-bg-0)",
                }}
              >
                {(dim.content_blocks ?? []).length === 0 && (
                  <p className="lv-t-meta" style={{ margin: 0, color: "var(--lv-ink-4)" }}>
                    （生成失败或为空）
                  </p>
                )}
                {(dim.content_blocks ?? []).map((block, idx) => (
                  <div key={idx}>
                    <div
                      className="lv-t-body"
                      style={{ fontWeight: 600, color: "var(--lv-ink)" }}
                    >
                      {block.heading}
                    </div>
                    <p
                      className="lv-t-body"
                      style={{
                        margin: "var(--lv-s-1) 0 0",
                        whiteSpace: "pre-wrap",
                        color: "var(--lv-ink-2)",
                      }}
                    >
                      {block.body}
                    </p>
                  </div>
                ))}
              </div>
            </details>
          </li>
        ))}
      </ul>

      {lorePack.generated_at && (
        <p className="lv-t-meta" style={{ margin: 0, color: "var(--lv-ink-4)" }}>
          生成于 {lorePack.generated_at}
        </p>
      )}
    </section>
  );
}
