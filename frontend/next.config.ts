import type { NextConfig } from "next";
import { withSentryConfig } from "@sentry/nextjs";
import createNextIntlPlugin from "next-intl/plugin";
import withSerwistInit from "@serwist/next";

const withNextIntl = createNextIntlPlugin("./i18n/request.ts");

const withSerwist = withSerwistInit({
  swSrc: "app/sw.ts",
  swDest: "public/sw.js",
  // 仅生产构建启用，dev 不生成 sw.js（避免 hot-reload 缓存干扰）
  disable: process.env.NODE_ENV !== "production",
  reloadOnOnline: true,
  cacheOnNavigation: true,
});

const nextConfig: NextConfig = {
  devIndicators: false,
  // Local dev: backend mounts /static/images under uvicorn on :8000.
  // The browser hits /static/... from Next's origin (:3000), so we proxy
  // that path to backend. Production uses OSS public URLs and never matches.
  async rewrites() {
    const backend = process.env.INTERNAL_API_URL || "http://localhost:8000";
    return [
      { source: "/static/:path*", destination: `${backend}/static/:path*` },
    ];
  },
};

export default withSentryConfig(withSerwist(withNextIntl(nextConfig)), {
  silent: true,
  telemetry: false,
  sourcemaps: {
    disable:
      !process.env.SENTRY_AUTH_TOKEN ||
      !process.env.SENTRY_ORG ||
      !process.env.SENTRY_PROJECT,
  },
});
