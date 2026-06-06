"use client";

import { useEffect } from "react";
import * as Sentry from "@sentry/nextjs";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    Sentry.captureException(error);
  }, [error]);

  return (
    <html lang="zh-CN">
      <body>
        <main className="flex min-h-dvh items-center justify-center bg-[#090a0f] px-6 text-[#f5f1e8]">
          <section className="max-w-md space-y-5 text-center">
            <p className="text-sm uppercase text-[#bda46a]">
              InkWild
            </p>
            <h1 className="text-2xl font-semibold">页面暂时无法继续</h1>
            <p className="text-sm leading-6 text-[#b9b0a3]">
              当前页面遇到了异常，已记录错误信息。
            </p>
            <div className="flex flex-col items-center justify-center gap-3 sm:flex-row">
              <button
                type="button"
                onClick={reset}
                className="rounded border border-[#bda46a]/60 px-5 py-2 text-sm text-[#f5f1e8] transition hover:border-[#e1c675] hover:bg-[#bda46a]/10"
              >
                重试
              </button>
              {/* global-error 替换整个 HTML 树，next/link 在这里没 router context，必须用原生 <a>。 */}
              {/* eslint-disable-next-line @next/next/no-html-link-for-pages */}
              <a
                href="/"
                className="rounded border border-[#b9b0a3]/40 px-5 py-2 text-sm text-[#b9b0a3] transition hover:border-[#f5f1e8] hover:text-[#f5f1e8]"
              >
                返回首页
              </a>
            </div>
          </section>
        </main>
      </body>
    </html>
  );
}
