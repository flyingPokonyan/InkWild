"use client";

interface StepIndicatorProps {
  steps: { key: string; label: string }[];
  currentStep: string;
}

/**
 * 步骤指示器。位于 sticky header 下方，灰阶风格（§2.2 选中态走 ink）。
 */
export function StepIndicator({ steps, currentStep }: StepIndicatorProps) {
  const currentIndex = steps.findIndex((s) => s.key === currentStep);

  if (steps.length === 0) return null;

  return (
    <div
      className="lv-theme"
      style={{
        position: "sticky",
        top: 56,
        zIndex: "var(--lv-z-sticky)" as unknown as number,
        borderBottom: "1px solid var(--lv-line)",
        background: "rgba(10,10,12,0.85)",
        backdropFilter: "blur(20px)",
      }}
    >
      <div
        style={{
          margin: "0 auto",
          maxWidth: "var(--lv-max-w)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          padding: "var(--lv-s-3) var(--lv-pad-x)",
          gap: 0,
        }}
      >
        {steps.map((step, i) => {
          const isCompleted = i < currentIndex;
          const isCurrent = i === currentIndex;
          const dotBg = isCompleted || isCurrent ? "var(--lv-ink)" : "transparent";
          const dotColor = isCompleted || isCurrent ? "var(--lv-bg)" : "var(--lv-ink-3)";
          const dotBorder = isCompleted || isCurrent ? "var(--lv-ink)" : "var(--lv-line-2)";
          return (
            <div key={step.key} style={{ display: "flex", alignItems: "center" }}>
              {i > 0 && (
                <div
                  style={{
                    height: 1,
                    width: "var(--lv-s-8)",
                    background: i <= currentIndex ? "var(--lv-ink-3)" : "var(--lv-line)",
                  }}
                />
              )}
              <div
                style={{
                  display: "flex",
                  flexDirection: "column",
                  alignItems: "center",
                  gap: "var(--lv-s-1)",
                }}
              >
                <div
                  className="lv-t-meta"
                  style={{
                    display: "grid",
                    placeItems: "center",
                    width: 24,
                    height: 24,
                    borderRadius: "var(--lv-r-pill)",
                    background: dotBg,
                    color: dotColor,
                    border: `1px solid ${dotBorder}`,
                    transition: "all var(--lv-dur-fast) var(--lv-ease)",
                  }}
                >
                  {isCompleted ? (
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
                      <polyline points="20 6 9 17 4 12" />
                    </svg>
                  ) : (
                    <span className="lv-t-micro">{i + 1}</span>
                  )}
                </div>
                <span
                  className="lv-t-meta"
                  style={{
                    whiteSpace: "nowrap",
                    color: isCurrent || isCompleted ? "var(--lv-ink)" : "var(--lv-ink-3)",
                  }}
                >
                  {step.label}
                </span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
