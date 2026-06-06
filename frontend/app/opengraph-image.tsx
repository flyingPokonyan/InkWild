import { ImageResponse } from "next/og";

/**
 * Open Graph 分享卡片 · 1200×630
 *
 * 用途：链接被分享到 Twitter / Discord / Slack / iMessage / WhatsApp 等平台时，
 *      自动展开成"标题 + 描述 + 图"的卡片预览。
 *
 * 字体策略：用 Satori 自带 fallback（系统 serif：Georgia / Times New Roman）。
 *
 * 不再从 Google Fonts 拉 Fraunces 的原因：
 * - Next 16 内置的 Satori 不解 woff2，Google Fonts 给现代 UA 默认就是 woff2，会让 build 挂
 * - 即便强行换 UA 拿 ttf/woff，build 期网络不稳也会偶发失败
 * - 系统 serif 跟 Fraunces 体型接近，OG 卡尺寸（1200×630）下视觉差异极小
 *
 * 如果以后想要严格 Fraunces，正确做法是把 Fraunces TTF 落到 frontend/app/fonts/，
 * 用 `new URL("./fonts/Fraunces-Regular.ttf", import.meta.url)` + fetch.arrayBuffer 加载。
 */

export const alt = "InkWild — Pick a world. Let it grow.";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

export default async function OpenGraphImage() {
  const titleFont = "Georgia, 'Times New Roman', 'Noto Serif SC', serif";

  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          alignItems: "center",
          background:
            "radial-gradient(ellipse 60% 80% at 20% 50%, rgba(80,90,120,0.22) 0%, rgba(8,8,10,0) 70%), radial-gradient(ellipse 40% 60% at 85% 50%, rgba(110,80,60,0.15) 0%, rgba(8,8,10,0) 70%), #0a0a0c",
          padding: "72px 88px",
        }}
      >
        {/* Branch mark */}
        <div
          style={{
            display: "flex",
            flexShrink: 0,
            marginRight: 72,
          }}
        >
          <svg width="240" height="288" viewBox="0 0 100 120" fill="none">
            <g stroke="#f5f2eb" strokeWidth="6" strokeLinecap="round">
              <path d="M 50 112 Q 50 84, 52 56 Q 54 32, 52 12" />
              <path d="M 51 84 Q 62 80, 76 70" />
              <path d="M 52 58 Q 40 52, 28 46" />
              <path d="M 52 28 Q 62 24, 72 18" />
              <path d="M 76 70 L 81 66" />
            </g>
          </svg>
        </div>

        {/* Text block */}
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            flex: 1,
            color: "#f5f2eb",
          }}
        >
          {/* Title */}
          <div
            style={{
              fontFamily: titleFont,
              fontSize: 80,
              fontWeight: 400,
              letterSpacing: "-0.025em",
              lineHeight: 1.0,
              marginBottom: 28,
              display: "flex",
              flexDirection: "column",
            }}
          >
            <span>Pick a world.</span>
            <span style={{ color: "#8a857a" }}>Let it grow.</span>
          </div>

          {/* Tagline */}
          <div
            style={{
              fontSize: 22,
              color: "#8a857a",
              lineHeight: 1.5,
              marginBottom: 64,
              maxWidth: 540,
              fontFamily: "system-ui, -apple-system, sans-serif",
            }}
          >
            An AI-driven interactive narrative engine. Scripted mysteries
            with hidden truths, or open-world roleplay — both run on the
            same living world.
          </div>

          {/* Wordmark + domain */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 24,
            }}
          >
            <span
              style={{
                fontFamily: titleFont,
                fontSize: 30,
                fontWeight: 500,
                color: "#f5f2eb",
                letterSpacing: "-0.015em",
              }}
            >
              InkWild
            </span>
            <span
              style={{
                width: 1,
                height: 22,
                background: "#22222a",
              }}
            />
            <span
              style={{
                fontFamily: "system-ui, -apple-system, sans-serif",
                fontSize: 14,
                color: "#4a463f",
                letterSpacing: "0.04em",
              }}
            >
              inkwild.app
            </span>
          </div>
        </div>
      </div>
    ),
    size,
  );
}
