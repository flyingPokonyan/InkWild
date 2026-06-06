"use client";

import { useRouter, usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import { LoadingPulse } from "@/components/ui/LoadingPulse";
import { buildLoginHref } from "@/lib/auth-redirect";
import { useAuthStore } from "@/stores/auth";

export default function WorkshopLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [ready, setReady] = useState(() => {
    const store = useAuthStore.getState();
    return store.hasLoaded && !!store.user;
  });

  useEffect(() => {
    let active = true;
    void (async () => {
      const store = useAuthStore.getState();
      const user = store.hasLoaded ? store.user : await store.loadMe();
      if (!active) return;
      if (!user) {
        router.replace(buildLoginHref(pathname));
        return;
      }
      setReady(true);
    })();
    return () => {
      active = false;
    };
  }, [pathname, router]);

  if (!ready) {
    return (
      <div
        style={{
          minHeight: "100dvh",
          background: "var(--lv-bg)",
          display: "grid",
          placeItems: "center",
        }}
      >
        <LoadingPulse variant="block" />
      </div>
    );
  }

  return <>{children}</>;
}
