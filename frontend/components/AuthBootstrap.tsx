"use client";

import { useEffect } from "react";

import { useAuthStore } from "@/stores/auth";

export function AuthBootstrap() {
  useEffect(() => {
    if (!useAuthStore.getState().hasLoaded) {
      void useAuthStore.getState().loadMe();
    }
  }, []);

  return null;
}
