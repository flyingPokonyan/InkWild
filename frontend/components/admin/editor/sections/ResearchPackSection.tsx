"use client";

import { useState } from "react";

type Passage = {
  id: string;
  text: string;
  tags: string[];
  source: "tavily" | "ip_probe" | "admin_note";
};

type IPCanon = {
  title_guesses?: string[];
  canonical_names?: string[];
  canonical_places?: string[];
  iconic_objects?: string[];
  lingo?: string[];
  notable_events?: string[];
};

export type ResearchPackData = {
  summary?: string;
  passages?: Passage[];
  ip_canon?: IPCanon;
};

type Props = {
  researchPack?: ResearchPackData | null;
};

const SOURCE_LABELS: Record<Passage["source"], string> = {
  admin_note: "Admin 素材",
  tavily: "联网检索",
  ip_probe: "LLM 自查",
};

export function ResearchPackSection({ researchPack }: Props) {
  const [expanded, setExpanded] = useState(false);

  if (!researchPack) return null;

  const passages = researchPack.passages ?? [];
  const canon = researchPack.ip_canon ?? {};
  const summary = (researchPack.summary ?? "").trim();

  return (
    <section
      aria-labelledby="research-pack-heading"
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
          id="research-pack-heading"
          className="lv-t-h2"
          style={{ margin: 0, color: "var(--lv-ink)" }}
        >
          研究包
        </h2>
        <span className="lv-t-caps" style={{ color: "var(--lv-ink-4)" }}>
          READ-ONLY
        </span>
      </header>

      {summary && (
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--lv-s-2)" }}>
          <h3 className="lv-t-h3" style={{ margin: 0, color: "var(--lv-ink)" }}>
            摘要
          </h3>
          <p
            className="lv-t-body"
            style={{
              margin: 0,
              whiteSpace: "pre-wrap",
              color: "var(--lv-ink-2)",
            }}
          >
            {summary}
          </p>
        </div>
      )}

      <div style={{ display: "flex", flexDirection: "column", gap: "var(--lv-s-2)" }}>
        <h3 className="lv-t-h3" style={{ margin: 0, color: "var(--lv-ink)" }}>
          IP Canon
        </h3>
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--lv-s-1)" }}>
          {canonRow("候选作品", canon.title_guesses)}
          {canonRow("人名", canon.canonical_names)}
          {canonRow("地名", canon.canonical_places)}
          {canonRow("标志物件", canon.iconic_objects)}
          {canonRow("语气 / 称谓", canon.lingo)}
          {canonRow("著名事件", canon.notable_events)}
          {!hasAnyCanon(canon) && (
            <span className="lv-t-meta" style={{ color: "var(--lv-ink-4)" }}>
              暂无
            </span>
          )}
        </div>
      </div>

      <div>
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="lv-t-body"
          style={{
            background: "transparent",
            border: 0,
            padding: 0,
            cursor: "pointer",
            color: "var(--lv-accent)",
            minHeight: 44,
            display: "inline-flex",
            alignItems: "center",
          }}
        >
          {expanded ? "收起" : "展开"}原文片段（{passages.length} 条）
        </button>

        {expanded && passages.length === 0 && (
          <p className="lv-t-meta" style={{ marginTop: "var(--lv-s-2)", color: "var(--lv-ink-4)" }}>
            无
          </p>
        )}

        {expanded && passages.length > 0 && (
          <ul
            style={{
              marginTop: "var(--lv-s-3)",
              padding: 0,
              listStyle: "none",
              display: "flex",
              flexDirection: "column",
              gap: "var(--lv-s-3)",
            }}
          >
            {passages.map((p) => (
              <li
                key={p.id}
                style={{
                  borderRadius: "var(--lv-r-card)",
                  border: "1px solid var(--lv-line)",
                  padding: "var(--lv-s-3) var(--lv-s-4)",
                }}
              >
                <div
                  className="lv-t-meta"
                  style={{
                    marginBottom: "var(--lv-s-1)",
                    display: "flex",
                    alignItems: "center",
                    gap: "var(--lv-s-2)",
                    color: "var(--lv-ink-3)",
                  }}
                >
                  <span>{SOURCE_LABELS[p.source] ?? p.source}</span>
                  <span aria-hidden>·</span>
                  <span style={{ fontFamily: "var(--lv-font-mono)" }}>{p.id}</span>
                </div>
                <p
                  className="lv-t-body"
                  style={{ margin: 0, whiteSpace: "pre-wrap" }}
                >
                  {p.text}
                </p>
                {p.tags.length > 0 && (
                  <div
                    className="lv-t-meta"
                    style={{
                      marginTop: "var(--lv-s-2)",
                      display: "flex",
                      flexWrap: "wrap",
                      gap: "var(--lv-s-1)",
                      color: "var(--lv-ink-3)",
                    }}
                  >
                    {p.tags.map((tag) => (
                      <span
                        key={tag}
                        style={{
                          borderRadius: "var(--lv-r-pill)",
                          background: "var(--lv-bg-2)",
                          padding: "2px 8px",
                        }}
                      >
                        {tag}
                      </span>
                    ))}
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}

function canonRow(label: string, items: string[] | undefined) {
  const list = (items ?? []).filter((s) => s && s.trim());
  if (list.length === 0) return null;
  return (
    <div className="lv-t-body">
      <span style={{ color: "var(--lv-ink-3)" }}>{label}：</span>
      <span style={{ color: "var(--lv-ink)" }}>{list.join("、")}</span>
    </div>
  );
}

function hasAnyCanon(canon: IPCanon): boolean {
  return [
    canon.title_guesses,
    canon.canonical_names,
    canon.canonical_places,
    canon.iconic_objects,
    canon.lingo,
    canon.notable_events,
  ].some((arr) => (arr ?? []).filter((s) => s && s.trim()).length > 0);
}
