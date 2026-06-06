"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { motion } from "motion/react";
import { ChevronLeft } from "lucide-react";
import { useTranslations } from "next-intl";

import { AccountShell } from "@/components/account/AccountShell";
import { CreditsPanel } from "@/components/account/CreditsPanel";
import { ProductNav } from "@/components/ProductNav";
import { MobileTopBar, MobileIconButton } from "@/components/MobileTopBar";
import { useAuthStore } from "@/stores/auth";
import { buildLoginHref } from "@/lib/auth-redirect";
import { lvFadeUp } from "@/lib/motion";

export default function CreditsPage() {
  const t = useTranslations("account");
  const router = useRouter();
  const user = useAuthStore((s) => s.user);

  useEffect(() => {
    void (async () => {
      const auth = useAuthStore.getState();
      const u = auth.hasLoaded ? auth.user : await auth.loadMe();
      if (!u) router.replace(buildLoginHref("/me/credits"));
    })();
  }, [router]);

  return (
    <main className="lv-theme mc-root">
      <div aria-hidden className="mc-glow" />

      <ProductNav variant="solid" />
      <MobileTopBar
        brand={t("creditsTitle")}
        left={
          <MobileIconButton aria-label="返回" onClick={() => router.push("/me")}>
            <ChevronLeft size={20} />
          </MobileIconButton>
        }
        right={null}
      />

      {/* 桌面：账户中心 */}
      <AccountShell active="credits">
        <CreditsPanel heading={t("creditsTitle")} />
      </AccountShell>

      {/* 移动：积分页 */}
      {user && (
        <motion.div className="mc-mobile" variants={lvFadeUp} initial="hidden" animate="show">
          <CreditsPanel />
        </motion.div>
      )}

      <style jsx global>{`
        .mc-root {
          background: var(--lv-bg);
          color: var(--lv-ink);
          min-height: 100dvh;
          overflow-x: hidden;
          position: relative;
        }
        .mc-glow {
          position: absolute;
          top: -160px;
          left: 50%;
          transform: translateX(-50%);
          width: 680px;
          height: 460px;
          pointer-events: none;
          z-index: 0;
          background: radial-gradient(ellipse 50% 50% at 50% 50%, rgba(223, 194, 144, 0.06), transparent 70%);
        }
        .mc-mobile {
          position: relative;
          z-index: 2;
          max-width: 640px;
          margin: 0 auto;
          padding: 14px clamp(16px, 5vw, 24px) calc(76px + env(safe-area-inset-bottom));
        }
        @media (min-width: 769px) {
          .mc-mobile {
            display: none !important;
          }
        }
      `}</style>
    </main>
  );
}
