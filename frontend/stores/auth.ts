"use client";

import { create } from "zustand";

import { apiFetch } from "@/lib/api";
import { normalizeCurrentUser, type CurrentUser, type CurrentUserDTO } from "@/lib/types";
import { useGameStore } from "@/stores/game";

interface AuthStore {
  user: CurrentUser | null;
  error: string | null;
  isLoading: boolean;
  hasLoaded: boolean;
  loadMe: () => Promise<CurrentUser | null>;
  login: (email: string, password: string) => Promise<CurrentUser>;
  logout: () => Promise<void>;
  setUser: (dto: CurrentUserDTO) => void;
}

let loadMePromise: Promise<CurrentUser | null> | null = null;

function getErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "请求失败";
}

export const useAuthStore = create<AuthStore>((set) => ({
  user: null,
  error: null,
  isLoading: false,
  hasLoaded: false,

  loadMe: async () => {
    if (loadMePromise) {
      return loadMePromise;
    }

    set({ isLoading: true, error: null });

    loadMePromise = (async () => {
      try {
        const userDTO = await apiFetch<CurrentUserDTO | null>("/api/auth/me");
        const user = userDTO ? normalizeCurrentUser(userDTO) : null;
        set({
          user,
          error: null,
          isLoading: false,
          hasLoaded: true,
        });
        return user;
      } catch (error) {
        set({
          user: null,
          error: getErrorMessage(error),
          isLoading: false,
          hasLoaded: true,
        });
        return null;
      } finally {
        loadMePromise = null;
      }
    })();

    return loadMePromise;
  },

  login: async (email, password) => {
    set({ isLoading: true, error: null });

    try {
      const userDTO = await apiFetch<CurrentUserDTO>("/api/auth/password/login", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      });
      const user = normalizeCurrentUser(userDTO);
      set({
        user,
        error: null,
        isLoading: false,
        hasLoaded: true,
      });
      return user;
    } catch (error) {
      const message = getErrorMessage(error);
      set({
        error: message,
        isLoading: false,
        hasLoaded: true,
      });
      throw error;
    }
  },

  logout: async () => {
    await apiFetch<void>("/api/auth/logout", {
      method: "POST",
    });
    useGameStore.getState().reset();
    set({
      user: null,
      error: null,
      isLoading: false,
      hasLoaded: true,
    });
  },

  // 资料/头像更新接口返回最新 CurrentUserDTO，直接写回 store 即时刷新 UI。
  setUser: (dto) => set({ user: normalizeCurrentUser(dto), hasLoaded: true }),
}));
