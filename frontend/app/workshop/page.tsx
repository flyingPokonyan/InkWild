"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import type { CSSProperties } from "react";
import { motion, AnimatePresence } from "motion/react";
import { useTranslations } from "next-intl";
import {
  Sparkles,
  AlertTriangle,
  Trash2,
  Plus,
  Globe,
  BookOpen,
  Clock,
  Activity,
  ArrowRight,
  LayoutGrid,
  List as ListIcon,
} from "lucide-react";

import { ProductNav } from "@/components/ProductNav";
import { buildLoginHref } from "@/lib/auth-redirect";
import { withReturn } from "@/lib/play-return";
import { workshopFetch } from "@/lib/workshop-api";
import { ossThumb } from "@/lib/oss-image";
import { parseBackendIso } from "@/lib/datetime";
import { useAuthStore } from "@/stores/auth";
import type {
  AdminScriptDraftDetail,
  AdminScriptListResponse,
  AdminWorldDraftDetail,
  AdminWorldListResponse,
  AdminWorldPublishedItem,
  AdminWorldDraftListItem,
  AdminScriptPublishedItem,
  AdminScriptDraftListItem,
} from "@/lib/types";

// Types matching tab keys
type WorkshopTab = "worlds" | "scripts";
type Filter = "all" | "published" | "private";
type MobileActionVariant = "primary" | "ghost";

function mobileWorkshopActionButtonStyle(
  variant: MobileActionVariant = "ghost",
  overrides: CSSProperties = {},
): CSSProperties {
  const isPrimary = variant === "primary";
  return {
    height: 32,
    minWidth: isPrimary ? 52 : 48,
    padding: "0 12px",
    borderRadius: 999,
    border: isPrimary ? "1px solid var(--lv-ink)" : "1px solid rgba(255,255,255,0.10)",
    background: isPrimary ? "var(--lv-ink)" : "rgba(255,255,255,0.04)",
    color: isPrimary ? "var(--lv-bg)" : "var(--lv-ink-2)",
    boxShadow: isPrimary ? "none" : "inset 0 1px 0 rgba(255,255,255,0.06)",
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    fontFamily: "var(--lv-font-sans)",
    fontSize: 12,
    fontWeight: 500,
    lineHeight: 1,
    letterSpacing: 0,
    whiteSpace: "nowrap",
    ...overrides,
  };
}

// A mapper for world genre styles to mock visual palettes (cover-art-spec §5.3)
function getGenreCoverClass(genre?: string | null, name?: string | null): string {
  const g = (genre || "").toLowerCase();
  const n = (name || "");
  
  if (g.includes("悬疑") || g.includes("推理") || n.includes("雾")) return "cover-fog";
  if (g.includes("历史") || g.includes("传奇") || n.includes("巷")) return "cover-amber";
  if (g.includes("武侠") || g.includes("江湖") || n.includes("镇")) return "cover-jade";
  if (g.includes("科幻") || g.includes("未来") || n.includes("计划")) return "cover-deepblue";
  if (g.includes("怪谈") || g.includes("恐怖") || n.includes("魂")) return "cover-noir";
  if (g.includes("废土") || g.includes("末日") || n.includes("荒")) return "cover-rust";
  
  const hash = n.length % 7;
  const classes = ["cover-fog", "cover-amber", "cover-jade", "cover-deepblue", "cover-noir", "cover-rust", "cover-mist"];
  return classes[hash];
}

export default function WorkshopDemoPage() {
  const t = useTranslations("workshopPage");
  const tWorkshop = useTranslations("admin.workshop");
  const router = useRouter();
  const canCreate = useAuthStore((s) => s.user?.canCreate ?? false);
  const queryClient = useQueryClient();

  const [tab, setTab] = useState<WorkshopTab>("worlds");
  const [pickedWorldId, setPickedWorldId] = useState<string | null>(null);
  const [busyTarget, setBusyTarget] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  // Filters for both panels
  const [worldFilter, setWorldFilter] = useState<Filter>("all");
  const [scriptFilter, setScriptFilter] = useState<Filter>("all");

  // Track deletion states (Optimistic Confirmation Overlays)
  const [deleteConfirmWorldId, setDeleteConfirmWorldId] = useState<string | null>(null);
  const [deleteConfirmScriptId, setDeleteConfirmScriptId] = useState<string | null>(null);

  // Sync tab from URL
  useEffect(() => {
    if (typeof window === "undefined") return;
    const sync = () => {
      const params = new URLSearchParams(window.location.search);
      const tabParam = params.get("tab");
      setTab(tabParam === "scripts" ? "scripts" : "worlds");
    };
    sync();
    window.addEventListener("popstate", sync);
    return () => window.removeEventListener("popstate", sync);
  }, []);

  // Auto-clear notices and errors
  useEffect(() => {
    if (!notice && !error) return;
    const id = setTimeout(() => {
      setNotice(null);
      setError(null);
    }, 4000);
    return () => clearTimeout(id);
  }, [notice, error]);

  // ====== Queries ======
  const worldsQuery = useQuery({
    queryKey: ["workshop", "worlds"],
    queryFn: () => workshopFetch<AdminWorldListResponse>("/api/workshop/worlds"),
  });

  // Filter out worlds with script counts > 0 for the scripts pill-bar
  const worldsWithScripts = useMemo(
    () => (worldsQuery.data?.published ?? []).filter((w) => w.script_count > 0),
    [worldsQuery.data],
  );

  // Derived selected world id
  const effectiveWorldId = pickedWorldId ?? worldsWithScripts[0]?.id ?? null;

  const scriptsQuery = useQuery({
    queryKey: ["workshop", "scripts", effectiveWorldId],
    queryFn: () =>
      workshopFetch<AdminScriptListResponse>(
        `/api/workshop/scripts?world_id=${effectiveWorldId}`,
      ),
    enabled: tab === "scripts" && !!effectiveWorldId,
  });

  // ====== Mutations: open draft for world / script ======
  const openWorldDraft = useMutation({
    mutationFn: (id: string) =>
      workshopFetch<AdminWorldDraftDetail>("/api/workshop/world-drafts", {
        method: "POST",
        body: JSON.stringify({ world_id: id }),
      }),
    onMutate: (id) => setBusyTarget(id),
    onSuccess: (d) => router.push(`/workshop/worlds/drafts/${d.id}`),
    onSettled: () => setBusyTarget(null),
    onError: (e: unknown) => {
      setError(e instanceof Error ? e.message : "打开世界草稿失败");
    },
  });

  const openScriptDraft = useMutation({
    mutationFn: (id: string) =>
      workshopFetch<AdminScriptDraftDetail>("/api/workshop/script-drafts", {
        method: "POST",
        body: JSON.stringify({ script_id: id }),
      }),
    onMutate: (id) => setBusyTarget(id),
    onSuccess: (d) => router.push(`/workshop/scripts/drafts/${d.id}`),
    onSettled: () => setBusyTarget(null),
    onError: (e: unknown) => {
      setError(e instanceof Error ? e.message : "打开剧本草稿失败");
    },
  });

  // ====== Mutations: delete ======
  const onDeleteError = useCallback(
    (e: unknown) => setError(e instanceof Error ? e.message : "删除失败"),
    [],
  );

  const deleteWorld = useMutation({
    mutationFn: (id: string) =>
      workshopFetch<unknown>(`/api/workshop/worlds/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["workshop", "worlds"] });
      setNotice("世界已成功删除");
      setDeleteConfirmWorldId(null);
    },
    onError: onDeleteError,
  });

  const deleteWorldDraft = useMutation({
    mutationFn: (id: string) =>
      workshopFetch<unknown>(`/api/workshop/world-drafts/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["workshop", "worlds"] });
      setNotice("世界草稿已成功删除");
      setDeleteConfirmWorldId(null);
    },
    onError: onDeleteError,
  });

  const deleteScript = useMutation({
    mutationFn: (id: string) =>
      workshopFetch<unknown>(`/api/workshop/scripts/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["workshop", "scripts"] });
      queryClient.invalidateQueries({ queryKey: ["workshop", "worlds"] });
      setNotice("剧本已成功删除");
      setDeleteConfirmScriptId(null);
    },
    onError: onDeleteError,
  });

  const deleteScriptDraft = useMutation({
    mutationFn: (id: string) =>
      workshopFetch<unknown>(`/api/workshop/script-drafts/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["workshop", "scripts"] });
      setNotice("剧本草稿已成功删除");
      setDeleteConfirmScriptId(null);
    },
    onError: onDeleteError,
  });

  // ====== Mutations: publish lifecycle (submit / withdraw submission / unpublish) ======
  const onLifecycleError = useCallback(
    (e: unknown) => setError(e instanceof Error ? e.message : "操作失败"),
    [],
  );
  const refetchBoth = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ["workshop", "worlds"] });
    queryClient.invalidateQueries({ queryKey: ["workshop", "scripts"] });
  }, [queryClient]);

  const submitWorld = useMutation({
    mutationFn: (draftId: string) =>
      workshopFetch<unknown>(`/api/workshop/world-drafts/${draftId}/submit`, { method: "POST" }),
    onSuccess: () => {
      refetchBoth();
      setNotice("已提交审核，通过后将对全网可见");
    },
    onError: onLifecycleError,
  });
  const withdrawWorldSubmission = useMutation({
    mutationFn: (draftId: string) =>
      workshopFetch<unknown>(`/api/workshop/world-drafts/${draftId}/withdraw-submission`, {
        method: "POST",
      }),
    onSuccess: () => {
      refetchBoth();
      setNotice("已撤回提交，回到私有");
    },
    onError: onLifecycleError,
  });
  const unpublishWorld = useMutation({
    mutationFn: (worldId: string) =>
      workshopFetch<unknown>(`/api/workshop/worlds/${worldId}/withdraw`, { method: "POST" }),
    onSuccess: () => {
      refetchBoth();
      setNotice("已下架，转为私有");
    },
    onError: onLifecycleError,
  });

  const submitScript = useMutation({
    mutationFn: (draftId: string) =>
      workshopFetch<unknown>(`/api/workshop/script-drafts/${draftId}/submit`, { method: "POST" }),
    onSuccess: () => {
      refetchBoth();
      setNotice("剧本已提交审核");
    },
    onError: onLifecycleError,
  });
  const withdrawScriptSubmission = useMutation({
    mutationFn: (draftId: string) =>
      workshopFetch<unknown>(`/api/workshop/script-drafts/${draftId}/withdraw-submission`, {
        method: "POST",
      }),
    onSuccess: () => {
      refetchBoth();
      setNotice("已撤回提交");
    },
    onError: onLifecycleError,
  });
  const unpublishScript = useMutation({
    mutationFn: (scriptId: string) =>
      workshopFetch<unknown>(`/api/workshop/scripts/${scriptId}/withdraw`, { method: "POST" }),
    onSuccess: () => {
      refetchBoth();
      setNotice("剧本已下架，转为私有");
    },
    onError: onLifecycleError,
  });

  const playWorld = useCallback(
    (worldId: string) => router.push(withReturn(`/worlds/${worldId}`, "/workshop")),
    [router],
  );

  // ====== Switchers ======
  const handleTabChange = (next: WorkshopTab) => {
    setTab(next);
    router.replace(next === "worlds" ? "/workshop" : `/workshop?tab=${next}`);
  };

  const handleCtaClick = () => {
    if (tab === "worlds") {
      router.push("/workshop/generate/world");
    } else if (tab === "scripts") {
      router.push(
        effectiveWorldId
          ? `/workshop/generate/script?world_id=${effectiveWorldId}`
          : "/workshop/generate/script",
      );
    }
  };

  // derived error state
  const errorMessage = useMemo(() => {
    if (worldsQuery.isError && tab === "worlds") {
      const e = worldsQuery.error;
      return e instanceof Error ? e.message : "获取数据失败";
    }
    return error;
  }, [worldsQuery.isError, worldsQuery.error, tab, error]);

  // Loading skeleton and status
  const isWorldsLoading = worldsQuery.isPending && tab === "worlds";
  const isScriptsLoading = scriptsQuery.isPending && tab === "scripts" && !!effectiveWorldId;

  return (
    <main
      className="lv-theme"
      style={{
        background: "var(--lv-bg)",
        color: "var(--lv-ink)",
        minHeight: "100dvh",
        overflowX: "hidden",
        position: "relative",
      }}
    >
      {/* Cinematic drift radial glowing nebulae */}
      {/* Premium Cinematic noise filter */}
      <div
        style={{
          position: "absolute",
          inset: 0,
          backgroundImage: `url("data:image/svg+xml,%3Csvg viewBox='0 0 200 200' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noiseFilter'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.75' numOctaves='3' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noiseFilter)' opacity='0.008'/%3E%3C/svg%3E")`,
          pointerEvents: "none",
          zIndex: 1,
        }}
      />

      {/* Floating Glassmorphic Sticky Header */}
      <ProductNav active="create" variant="solid" />

      <MobileWorkshopView
        worldsQuery={worldsQuery}
        scriptsQuery={scriptsQuery}
        canCreate={canCreate}
        busyTarget={busyTarget}
        onOpenWorldDraft={(id) => openWorldDraft.mutate(id)}
        onOpenScriptDraft={(id) => openScriptDraft.mutate(id)}
        onSubmitWorld={(draftId) => submitWorld.mutate(draftId)}
        onWithdrawWorldSubmission={(draftId) => withdrawWorldSubmission.mutate(draftId)}
        onUnpublishWorld={(worldId) => unpublishWorld.mutate(worldId)}
        onSubmitScript={(draftId) => submitScript.mutate(draftId)}
        onWithdrawScriptSubmission={(draftId) => withdrawScriptSubmission.mutate(draftId)}
        onUnpublishScript={(scriptId) => unpublishScript.mutate(scriptId)}
        notice={notice}
        error={error}
      />

      <div className="lv-workshop-desktop">
      {/* A. Compact 200px Header (ws-header) */}
      <section className="ws-header container">
        <div className="ws-header-row">
          <div>
            <span className="lv-t-caps ws-eyebrow">Creative Studio</span>
            <h1 className="lv-t-h1 ws-title" style={{ fontWeight: 500, fontFamily: "var(--lv-ff-serif)" }}>{t("title")}</h1>
          </div>
          
          {canCreate ? (
            <motion.button
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
              className="ws-cta"
              onClick={handleCtaClick}
            >
              <Plus className="ws-cta-plus" size={18} />
              <span>{tab === "worlds" ? tWorkshop("cta.world") : tWorkshop("cta.script")}</span>
            </motion.button>
          ) : null}
        </div>

        {/* Tab view switcher —— 跟 /history FilterPills 同款奶白 pill */}
        <nav className="ws-tabs" role="tablist">
          {(["worlds", "scripts"] as const).map((key) => {
            const isActive = tab === key;
            return (
              <button
                key={key}
                className={`ws-tab ${isActive ? "active" : ""}`}
                role="tab"
                aria-selected={isActive}
                onClick={() => handleTabChange(key)}
              >
                {isActive && (
                  <motion.div
                    layoutId="ws-tab-pill"
                    className="ws-tab-pill"
                    transition={{ type: "spring", stiffness: 380, damping: 30 }}
                  />
                )}
                <span style={{ position: "relative", zIndex: 1 }}>
                  {key === "worlds" ? tWorkshop("tabs.worlds") : tWorkshop("tabs.scripts")}
                </span>
              </button>
            );
          })}
        </nav>
      </section>

      {/* Floating Notices / Warnings */}
      <AnimatePresence>
        {errorMessage ? (
          <motion.div 
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            className="container" 
            style={{ marginTop: 20 }}
          >
            <div className="ws-toast is-error">
              <AlertTriangle size={16} />
              <span>{errorMessage}</span>
            </div>
          </motion.div>
        ) : null}

        {notice ? (
          <motion.div 
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            className="container" 
            style={{ marginTop: 20 }}
          >
            <div className="ws-toast is-success">
              <Sparkles size={16} />
              <span>{notice}</span>
            </div>
          </motion.div>
        ) : null}

        {!canCreate && (
          <motion.div 
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="container" 
            style={{ marginTop: 20 }}
          >
            <div className="ws-permission-banner">
              你还没有创作权限。当前处于只读模式，可以浏览已发布的世界与剧本；如需开通创作权限，请联系管理员开通。
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* B. Tab Panels */}
      <div className="container" style={{ position: "relative", zIndex: 5 }}>
        
        {/* ====================================
             1. WORLDS PANEL
             ==================================== */}
        {tab === "worlds" && (
          <section className="ws-main">
            {/* Toolbar: filter & counts */}
            <div className="toolbar">
              <div className="toolbar-left">
                <span className="lv-t-caps" style={{ color: "var(--lv-accent)" }}>全部世界</span>
                <span className="lv-t-meta toolbar-count">
                  {isWorldsLoading ? (
                    "读取中..."
                  ) : (
                    `${(worldsQuery.data?.published.length ?? 0) + (worldsQuery.data?.drafts.length ?? 0)} 个世界 · ${worldsQuery.data?.drafts.length ?? 0} 个草稿`
                  )}
                </span>
              </div>
              <div className="toolbar-filters">
                {(["all", "published", "private"] as const).map((mode) => (
                  <button
                    key={mode}
                    className={`toolbar-chip ${worldFilter === mode ? "active" : ""}`}
                    onClick={() => setWorldFilter(mode)}
                  >
                    {mode === "all" ? "全部" : mode === "published" ? "已发布" : "私有"}
                  </button>
                ))}
              </div>
            </div>

            {/* Content List */}
            {isWorldsLoading ? (
              <WorldsGridSkeleton />
            ) : (
              <motion.div 
                layout 
                className="worlds-grid"
              >
                {/* Unsaved generation drafts (not yet a playable world) */}
                {(worldFilter === "all" || worldFilter === "private") &&
                  (worldsQuery.data?.drafts ?? []).map((draft) => (
                    <WorldDraftCard
                      key={`draft-${draft.id}`}
                      draft={draft}
                      busy={busyTarget === draft.id}
                      onOpen={() => router.push(`/workshop/worlds/drafts/${draft.id}`)}
                      onDeleteConfirm={(id) => setDeleteConfirmWorldId(id)}
                      confirmingDelete={deleteConfirmWorldId === draft.id}
                      onCancelDelete={() => setDeleteConfirmWorldId(null)}
                      onConfirmDelete={() => deleteWorldDraft.mutate(draft.id)}
                    />
                  ))}

                {/* Saved worlds: private / submitted / rejected / published */}
                {(worldsQuery.data?.published ?? [])
                  .filter((world) =>
                    worldFilter === "all"
                      ? true
                      : worldFilter === "published"
                        ? world.status === "published"
                        : world.status !== "published",
                  )
                  .map((world) => (
                    <WorldPublishedCard
                      key={`world-${world.id}`}
                      world={world}
                      busy={busyTarget === world.id}
                      onOpen={() => openWorldDraft.mutate(world.id)}
                      onPlay={() => playWorld(world.id)}
                      onSubmit={() => world.draft_id && submitWorld.mutate(world.draft_id)}
                      onWithdrawSubmission={() =>
                        world.draft_id && withdrawWorldSubmission.mutate(world.draft_id)
                      }
                      onUnpublish={() => unpublishWorld.mutate(world.id)}
                      onDeleteConfirm={(id) => setDeleteConfirmWorldId(id)}
                      confirmingDelete={deleteConfirmWorldId === world.id}
                      onCancelDelete={() => setDeleteConfirmWorldId(null)}
                      onConfirmDelete={() => deleteWorld.mutate(world.id)}
                    />
                  ))}

                {/* Dashed placeholder for Create New */}
                {canCreate && (
                  <button
                    onClick={() => router.push("/workshop/generate/world")}
                    className="world-card new-card"
                    type="button"
                  >
                    <div className="world-cover new-card-cover">
                      <div className="new-card-plus">+</div>
                    </div>
                    <div className="world-card-body">
                      <h3 className="lv-t-h3 world-title">创造新世界</h3>
                      <div className="world-meta lv-t-meta">
                        <span>AI 驱动的一键生成</span>
                      </div>
                    </div>
                  </button>
                )}
              </motion.div>
            )}

            {/* Empty fallback */}
            {!isWorldsLoading && 
             (worldsQuery.data?.published.length ?? 0) === 0 && 
             (worldsQuery.data?.drafts.length ?? 0) === 0 && (
              <div className="ws-empty-slate">
                <Globe size={40} style={{ color: "var(--lv-ink-4)", marginBottom: 16 }} />
                <h3 className="lv-t-h3" style={{ color: "var(--lv-ink-2)" }}>你还没有创建过世界</h3>
                <p className="lv-t-meta" style={{ margin: "8px 0 20px" }}>从一个想法开始，新建你的第一个世界。</p>
                {canCreate && (
                  <motion.button 
                    whileHover={{ scale: 1.03 }}
                    onClick={() => router.push("/workshop/generate/world")}
                    className="ws-cta"
                  >
                    <Plus size={16} className="ws-cta-plus" />
                    <span>新建第一个世界</span>
                  </motion.button>
                )}
              </div>
            )}
          </section>
        )}

        {/* ====================================
             2. SCRIPTS PANEL
             ==================================== */}
        {tab === "scripts" && (
          <section className="ws-main">
            {/* World selector pillbar */}
            {worldsWithScripts.length > 0 ? (
              <nav className="world-pillbar" aria-label="选择所属世界">
                {worldsWithScripts.map((w) => {
                  const isActive = effectiveWorldId === w.id;
                  return (
                    <button
                      key={w.id}
                      className={`world-pill ${isActive ? "active" : ""}`}
                      onClick={() => setPickedWorldId(w.id)}
                    >
                      <span>{w.name}</span>
                      <span className="world-pill-count">{w.script_count}</span>
                    </button>
                  );
                })}
              </nav>
            ) : null}

            {/* Toolbar */}
            <div className="toolbar">
              <div className="toolbar-left">
                <span className="lv-t-caps" style={{ color: "var(--lv-accent)" }}>
                  {worldsWithScripts.find((w) => w.id === effectiveWorldId)?.name || "无所属世界"} · 剧本
                </span>
                <span className="lv-t-meta toolbar-count">
                  {isScriptsLoading ? (
                    "读取中..."
                  ) : (
                    `${(scriptsQuery.data?.published.length ?? 0) + (scriptsQuery.data?.drafts.length ?? 0)} 部剧本 · ${scriptsQuery.data?.drafts.length ?? 0} 个草稿`
                  )}
                </span>
              </div>
              <div className="toolbar-filters">
                {(["all", "published", "private"] as const).map((mode) => (
                  <button
                    key={mode}
                    className={`toolbar-chip ${scriptFilter === mode ? "active" : ""}`}
                    onClick={() => setScriptFilter(mode)}
                  >
                    {mode === "all" ? "全部" : mode === "published" ? "已发布" : "私有"}
                  </button>
                ))}
              </div>
            </div>

            {/* List content */}
            {isScriptsLoading ? (
              <WorldsGridSkeleton />
            ) : (
              <motion.div 
                layout 
                className="scripts-grid"
              >
                {/* Unsaved generation drafts */}
                {(scriptFilter === "all" || scriptFilter === "private") &&
                  (scriptsQuery.data?.drafts ?? []).map((draft) => (
                    <ScriptDraftCard
                      key={`draft-${draft.id}`}
                      draft={draft}
                      onOpen={() => router.push(`/workshop/scripts/drafts/${draft.id}`)}
                      onDeleteConfirm={(id) => setDeleteConfirmScriptId(id)}
                      confirmingDelete={deleteConfirmScriptId === draft.id}
                      onCancelDelete={() => setDeleteConfirmScriptId(null)}
                      onConfirmDelete={() => deleteScriptDraft.mutate(draft.id)}
                    />
                  ))}

                {/* Saved scripts: private / submitted / rejected / published */}
                {(scriptsQuery.data?.published ?? [])
                  .filter((script) =>
                    scriptFilter === "all"
                      ? true
                      : scriptFilter === "published"
                        ? script.status === "published"
                        : script.status !== "published",
                  )
                  .map((script) => (
                    <ScriptPublishedCard
                      key={`script-${script.id}`}
                      script={script}
                      busy={busyTarget === script.id}
                      onOpen={() => openScriptDraft.mutate(script.id)}
                      onPlay={() =>
                        effectiveWorldId &&
                        router.push(withReturn(`/worlds/${effectiveWorldId}`, "/workshop?tab=scripts"))
                      }
                      onSubmit={() => script.draft_id && submitScript.mutate(script.draft_id)}
                      onWithdrawSubmission={() =>
                        script.draft_id && withdrawScriptSubmission.mutate(script.draft_id)
                      }
                      onUnpublish={() => unpublishScript.mutate(script.id)}
                      onDeleteConfirm={(id) => setDeleteConfirmScriptId(id)}
                      confirmingDelete={deleteConfirmScriptId === script.id}
                      onCancelDelete={() => setDeleteConfirmScriptId(null)}
                      onConfirmDelete={() => deleteScript.mutate(script.id)}
                    />
                  ))}

                {/* Dashed placeholder for create */}
                {canCreate && (
                  <button
                    onClick={() =>
                      router.push(
                        effectiveWorldId
                          ? `/workshop/generate/script?world_id=${effectiveWorldId}`
                          : "/workshop/generate/script",
                      )
                    }
                    className="world-card new-card"
                    type="button"
                  >
                    <div className="world-cover new-card-cover">
                      <div className="new-card-plus">+</div>
                    </div>
                    <div className="world-card-body">
                      <h3 className="lv-t-h3 world-title">创作新剧本</h3>
                      <div className="world-meta lv-t-meta">
                        <span>一键生成剧情分支与线索</span>
                      </div>
                    </div>
                  </button>
                )}
              </motion.div>
            )}

            {/* Empty / Warning cases */}
            {(worldsQuery.data?.published.length ?? 0) === 0 && (
              <div className="ws-empty-slate">
                <AlertTriangle size={32} style={{ color: "var(--lv-warn)", marginBottom: 16 }} />
                <h3 className="lv-t-h3" style={{ color: "var(--lv-ink-2)" }}>写剧本前，需要先发布一个世界</h3>
                <p className="lv-t-meta" style={{ margin: "8px 0 20px" }}>剧本依附于世界。先创建并发布一个世界，再来写剧本。</p>
                <motion.button 
                  whileHover={{ scale: 1.03 }}
                  onClick={() => handleTabChange("worlds")}
                  className="ws-cta"
                >
                  <span>去世界列表看看</span>
                  <ArrowRight size={14} style={{ marginLeft: 6 }} />
                </motion.button>
              </div>
            )}

            {worldsWithScripts.length === 0 && (worldsQuery.data?.published.length ?? 0) > 0 && (
              <div className="ws-empty-slate">
                <BookOpen size={40} style={{ color: "var(--lv-ink-4)", marginBottom: 16 }} />
                <h3 className="lv-t-h3" style={{ color: "var(--lv-ink-2)" }}>当前世界尚未拥有独立剧本</h3>
                <p className="lv-t-meta" style={{ margin: "8px 0 20px" }}>来为这个波澜壮阔的世界，撰写第一部供玩家推演的剧本主线线索。</p>
                {canCreate && (
                  <motion.button 
                    whileHover={{ scale: 1.03 }}
                    onClick={() => router.push(effectiveWorldId ? `/workshop/generate/script?world_id=${effectiveWorldId}` : "/workshop/generate/script")}
                    className="ws-cta"
                  >
                    <Plus size={16} className="ws-cta-plus" />
                    <span>新建一部剧本</span>
                  </motion.button>
                )}
              </div>
            )}
          </section>
        )}

      </div>
      </div>

      {/* Styled JSX specifically for the Creation Workshop V2.2 Premium Aesthetics */}
      <style jsx global>{`
        @media (max-width: 768px) {
          .lv-workshop-desktop { display: none !important; }
        }
        @media (min-width: 769px) {
          .lv-workshop-mobile { display: none !important; }
        }

        /* Aligned with home-demo/discover-demo global resets */
        @import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@400;500&family=Noto+Serif+SC:wght@400;500&family=JetBrains+Mono:wght@500&display=swap');

        :root {
          --lv-ff-serif: "Cormorant Garamond","Noto Serif SC", Georgia, "Times New Roman", serif;
          --lv-ff-sans: "Inter", -apple-system, BlinkMacSystemFont, "PingFang SC", "Helvetica Neue", sans-serif;
          --lv-ff-mono: "JetBrains Mono","SF Mono", Menlo, Consolas, monospace;
          --lv-ease: cubic-bezier(0.2, 0.7, 0.2, 1);
        }

        .lv-theme {
          font-family: var(--lv-ff-sans);
        }

        /* typography overrides for literary quality */
        .lv-t-display { font-family: var(--lv-ff-serif); }
        .lv-t-h1 { font-family: var(--lv-ff-serif); }
        .lv-t-h2 { font-family: var(--lv-ff-serif); }

        /* Centered max-width container —— 之前没定义导致整体贴左 */
        .container {
          max-width: 1440px;
          margin: 0 auto;
          padding: 0 clamp(20px, 4vw, 52px);
        }

        /* A. Page-internal workspace header (NOT a second nav bar) */
        .ws-header {
          padding-top: 110px;
        }
        .ws-header-row {
          display: flex;
          align-items: flex-end;
          justify-content: space-between;
          gap: 20px;
          flex-wrap: wrap;
          padding-bottom: 24px;
        }
        .ws-eyebrow {
          color: var(--lv-ink-3);
          margin-bottom: 8px;
          display: block;
        }
        .ws-title {
          color: var(--lv-ink);
        }

        /* Tab pills —— 对齐 /history FilterPills 的奶白 pill 风格 */
        .ws-tabs {
          display: inline-flex;
          align-self: flex-start;
          gap: 4px;
          padding: 4px;
          background: rgba(255, 255, 255, 0.015);
          border: 1px solid rgba(255, 255, 255, 0.06);
          border-radius: 100px;
          backdrop-filter: blur(8px);
        }
        .ws-tab {
          position: relative;
          background: transparent;
          border: 0;
          padding: 6px 18px;
          border-radius: 100px;
          color: var(--lv-ink-2);
          font-family: var(--lv-ff-mono);
          font-size: 11px;
          letter-spacing: 0.18em;
          text-transform: uppercase;
          font-weight: 500;
          cursor: pointer;
          outline: 0;
          z-index: 1;
          transition: color 250ms var(--lv-ease);
        }
        .ws-tab:not(.active):hover {
          color: var(--lv-ink);
        }
        .ws-tab.active {
          color: var(--lv-bg);
          font-weight: 700;
        }
        .ws-tab-pill {
          position: absolute;
          inset: 0;
          border-radius: 100px;
          background: rgba(245, 242, 235, 0.90);
          box-shadow: 0 2px 8px rgba(0, 0, 0, 0.25);
          z-index: -1;
        }

        /* Primary CTA — ivory white, neutral hover lift (no gold paint) */
        .ws-cta {
          display: inline-flex;
          align-items: center;
          gap: 8px;
          padding: 0 20px;
          height: 40px;
          border-radius: var(--lv-r-pill);
          background: var(--lv-ink);
          border: 1px solid var(--lv-ink);
          color: #0a0a0c;
          font-family: var(--lv-ff-sans);
          font-size: 13.5px;
          font-weight: 600;
          cursor: pointer;
          transition: all 250ms var(--lv-ease);
          white-space: nowrap;
        }
        .ws-cta:hover {
          transform: translateY(-1px);
          box-shadow: 0 8px 22px rgba(0, 0, 0, 0.45);
        }
        .ws-cta-plus {
          color: #0a0a0c;
        }

        /* B. Main workspace grids */
        .ws-main {
          padding: 32px 0 96px;
        }
        .toolbar {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 16px;
          margin-bottom: 24px;
          flex-wrap: wrap;
        }
        .toolbar-left {
          display: flex;
          align-items: baseline;
          gap: 12px;
        }
        .toolbar-count {
          color: var(--lv-ink-3);
        }

        /* Filter chip filters */
        .toolbar-filters {
          display: flex;
          gap: 4px;
          padding: 3px;
          background: rgba(255, 255, 255, 0.015);
          border: 1px solid var(--lv-line);
          border-radius: var(--lv-r-pill);
        }
        .toolbar-chip {
          padding: 5px 12px;
          height: 28px;
          border-radius: var(--lv-r-pill);
          background: transparent;
          border: none;
          color: var(--lv-ink-3);
          font-family: var(--lv-ff-sans);
          font-size: 12px;
          font-weight: 500;
          cursor: pointer;
          transition: all 200ms var(--lv-ease);
          display: inline-flex;
          align-items: center;
          justify-content: center;
        }
        .toolbar-chip:not(.active):hover {
          color: var(--lv-accent);
        }
        .toolbar-chip.active {
          background: rgba(255, 255, 255, 0.06);
          color: var(--lv-ink);
        }

        /* 16:10 Grid structure */
        .worlds-grid, .scripts-grid {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
          gap: 24px;
        }
        @media (max-width: 1024px) {
          .worlds-grid, .scripts-grid {
            grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
          }
        }
        @media (max-width: 600px) {
          .worlds-grid, .scripts-grid {
            grid-template-columns: 1fr;
          }
        }

        /* C. Cards layout — 紧凑型，hover 反馈集中在 cover；整卡只做 translateY */
        .world-card {
          cursor: pointer;
          display: flex;
          flex-direction: column;
          gap: 10px;
          text-align: left;
          background: none;
          border: none;
          color: inherit;
          font: inherit;
          padding: 0;
          position: relative;
          transition: transform 350ms cubic-bezier(0.16, 1, 0.3, 1);
        }
        .world-card:hover {
          transform: translateY(-3px);
        }

        .world-cover {
          position: relative;
          aspect-ratio: 3 / 2;
          border-radius: 12px;
          overflow: hidden;
          background: var(--lv-bg-1);
          border: 1px solid rgba(255, 255, 255, 0.06);
          box-shadow: 0 6px 15px rgba(0, 0, 0, 0.2);
          transition: border-color 350ms cubic-bezier(0.16, 1, 0.3, 1),
                      box-shadow 350ms cubic-bezier(0.16, 1, 0.3, 1);
          width: 100%;
        }
        .world-card:hover .world-cover {
          border-color: rgba(255, 255, 255, 0.14);
          box-shadow: 0 16px 32px rgba(0, 0, 0, 0.45);
        }

        .world-cover-bg {
          position: absolute;
          inset: 0;
          transition: transform 600ms cubic-bezier(0.16, 1, 0.3, 1);
          background-size: cover;
          background-position: center;
        }
        .world-card:hover .world-cover-bg {
          transform: scale(1.04);
        }

        .world-cover::after {
          content: "";
          position: absolute;
          inset: 50% 0 0 0;
          background: linear-gradient(180deg, transparent, rgba(0, 0, 0, 0.35));
          pointer-events: none;
        }

        /* Specific cover gradients */
        .cover-fog {
          background: radial-gradient(ellipse 60% 50% at 50% 78%, rgba(180, 190, 200, 0.14), transparent 70%),
                      radial-gradient(ellipse 80% 60% at 30% 20%, rgba(110, 125, 140, 0.12), transparent 65%),
                      linear-gradient(170deg, #161c22 0%, #080b0e 100%);
        }
        .cover-amber {
          background: radial-gradient(ellipse 50% 50% at 70% 65%, rgba(201, 163, 106, 0.22), transparent 60%),
                      radial-gradient(ellipse 60% 50% at 20% 30%, rgba(60, 32, 22, 0.45), transparent 55%),
                      linear-gradient(160deg, #16110d 0%, #070604 100%);
        }
        .cover-jade {
          background: radial-gradient(ellipse 60% 60% at 40% 65%, rgba(127, 176, 145, 0.14), transparent 60%),
                      radial-gradient(ellipse 70% 50% at 80% 25%, rgba(80, 110, 90, 0.08), transparent 55%),
                      linear-gradient(150deg, #0b1210 0%, #040806 100%);
        }
        .cover-deepblue {
          background: radial-gradient(ellipse 60% 50% at 50% 30%, rgba(80, 120, 170, 0.18), transparent 65%),
                      radial-gradient(ellipse 50% 40% at 30% 80%, rgba(40, 60, 100, 0.22), transparent 60%),
                      linear-gradient(180deg, #0b1116 0%, #04060c 100%);
        }
        .cover-noir {
          background: radial-gradient(ellipse 50% 50% at 32% 70%, rgba(184, 140, 90, 0.16), transparent 55%),
                      radial-gradient(ellipse 70% 60% at 80% 25%, rgba(70, 80, 95, 0.14), transparent 60%),
                      linear-gradient(140deg, #15181d 0%, #08090c 100%);
        }
        .cover-rust {
          background: radial-gradient(ellipse 50% 50% at 65% 70%, rgba(184, 92, 92, 0.15), transparent 55%),
                      radial-gradient(ellipse 60% 50% at 25% 30%, rgba(35, 25, 25, 0.45), transparent 50%),
                      linear-gradient(170deg, #15100d 0%, #060508 100%);
        }
        .cover-mist {
          background: radial-gradient(ellipse 80% 60% at 50% 60%, rgba(190, 200, 205, 0.08), transparent 70%),
                      linear-gradient(180deg, #10141a 0%, #05070a 100%);
        }

        /* Card overlay states */
        .cover-status {
          position: absolute;
          top: 10px;
          left: 10px;
          padding: 3px 8px;
          border-radius: var(--lv-r-pill);
          background: rgba(0, 0, 0, 0.55);
          backdrop-filter: blur(8px);
          -webkit-backdrop-filter: blur(8px);
          border: 1px solid rgba(255, 255, 255, 0.08);
          color: var(--lv-ink-2);
          z-index: 2;
          display: inline-flex;
          align-items: center;
          gap: 5px;
          font-family: var(--lv-ff-mono);
          font-size: 10px;
        }
        .cover-status.generating {
          color: var(--lv-accent);
          border-color: rgba(223, 194, 144, 0.25);
        }
        .cover-status.generating::before {
          content: "";
          display: inline-block;
          width: 5px;
          height: 5px;
          border-radius: 50%;
          background: var(--lv-accent);
          animation: pulse 1.8s ease infinite;
        }
        .cover-status.failed {
          color: var(--lv-danger);
          border-color: rgba(184, 92, 92, 0.35);
        }
        .cover-status.failed::before {
          content: "";
          display: inline-block;
          width: 5px;
          height: 5px;
          border-radius: 50%;
          background: var(--lv-danger);
        }

        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.3; }
        }

        /* Draft marks for pending cards */
        .draft-mark {
          position: absolute;
          inset: 12px;
          border: 1px dashed var(--lv-line-2);
          border-radius: 10px;
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          gap: 8px;
          color: var(--lv-ink-3);
          z-index: 1;
        }
        .draft-mark-icon {
          width: 28px;
          height: 28px;
          border-radius: 50%;
          border: 1px solid var(--lv-line-2);
          display: flex;
          align-items: center;
          justify-content: center;
          color: var(--lv-ink-3);
          font-family: var(--lv-ff-mono);
          font-size: 12px;
        }
        .draft-mark-icon.spinner {
          border-color: rgba(223, 194, 144, 0.2);
          color: var(--lv-accent);
          position: relative;
        }
        .draft-mark-icon.spinner::before {
          content: "";
          position: absolute;
          inset: 3px;
          border-radius: 50%;
          border: 1px solid transparent;
          border-top-color: var(--lv-accent);
          animation: spin 1.2s linear infinite;
        }

        @keyframes spin {
          to { transform: rotate(360deg); }
        }

        /* Card bodies & typography layout */
        .world-card-body {
          display: flex;
          flex-direction: column;
          gap: 4px;
          padding: 0 2px;
        }
        .world-title {
          color: var(--lv-ink);
          font-family: var(--lv-font-serif);
          font-weight: 500;
          font-size: 18px;
          margin: 0;
          transition: color 200ms ease;
        }
        .world-card:hover .world-title {
          color: var(--lv-accent);
        }
        .world-meta {
          color: var(--lv-ink-3);
          display: flex;
          gap: 5px;
          align-items: center;
          flex-wrap: wrap;
          font-size: 11.5px;
        }
        .world-meta-sep {
          color: var(--lv-ink-5);
        }

        /* Dashed New creation trigger cards — reuse .world-card layout so
           total height (cover + body) matches published cards. */
        .new-card {
          color: var(--lv-ink-3);
        }
        .new-card-cover {
          border-style: dashed;
          border-color: var(--lv-line-2);
          background: rgba(255, 255, 255, 0.01);
          display: flex;
          align-items: center;
          justify-content: center;
        }
        .new-card-cover::after {
          /* drop the inherited 50% bottom gradient — no real cover image here */
          display: none;
        }
        .world-card.new-card:hover .new-card-cover {
          border-color: rgba(255, 255, 255, 0.14);
          background: rgba(255, 255, 255, 0.02);
        }
        .new-card-plus {
          width: 38px;
          height: 38px;
          border-radius: 50%;
          border: 1px solid var(--lv-line-2);
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: 18px;
          color: var(--lv-ink-2);
          background: rgba(255, 255, 255, 0.01);
          transition: all 250ms var(--lv-ease);
        }
        .world-card.new-card:hover .new-card-plus {
          border-color: rgba(255, 255, 255, 0.18);
          color: var(--lv-ink);
        }

        /* World selectors bar */
        .world-pillbar {
          display: flex;
          gap: 8px;
          padding: 2px 0 16px;
          margin-bottom: 20px;
          border-bottom: 1px solid var(--lv-line);
          overflow-x: auto;
          scrollbar-width: none;
        }
        .world-pillbar::-webkit-scrollbar {
          display: none;
        }

        .world-pill {
          flex-shrink: 0;
          height: 32px;
          padding: 0 14px;
          border-radius: var(--lv-r-pill);
          background: transparent;
          border: 1px solid var(--lv-line);
          color: var(--lv-ink-3);
          font-family: var(--lv-ff-sans);
          font-size: 12.5px;
          font-weight: 500;
          cursor: pointer;
          transition: all 200ms var(--lv-ease);
          display: inline-flex;
          align-items: center;
          gap: 6px;
        }
        .world-pill:hover {
          color: var(--lv-ink-2);
          border-color: var(--lv-line-2);
        }
        .world-pill.active {
          background: var(--lv-accent-soft);
          border-color: rgba(223, 194, 144, 0.14);
          color: var(--lv-accent);
        }
        .world-pill-count {
          font-family: var(--lv-ff-mono);
          font-size: 9.5px;
          color: var(--lv-ink-3);
        }
        .world-pill.active .world-pill-count {
          color: var(--lv-accent);
        }

        /* Action elements (trash bins / confirmations) */
        .card-action-btn {
          position: absolute;
          top: 10px;
          right: 10px;
          width: 28px;
          height: 28px;
          border-radius: 50%;
          background: rgba(0, 0, 0, 0.5);
          border: 1px solid rgba(255, 255, 255, 0.08);
          color: var(--lv-ink-3);
          display: flex;
          align-items: center;
          justify-content: center;
          cursor: pointer;
          opacity: 0;
          transition: all 250ms var(--lv-ease);
          z-index: 5;
        }
        .world-cover:hover .card-action-btn {
          opacity: 1;
        }
        .card-action-btn:hover {
          background: var(--lv-danger);
          border-color: rgba(184, 92, 92, 0.4);
          color: #fff;
        }

        /* Confirm overlay cover sheet */
        .confirm-delete-overlay {
          position: absolute;
          inset: 0;
          background: rgba(184, 92, 92, 0.85);
          backdrop-filter: blur(10px);
          -webkit-backdrop-filter: blur(10px);
          z-index: 10;
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          gap: 12px;
          padding: 12px;
          text-align: center;
          border-radius: var(--lv-r-card);
        }
        .confirm-delete-title {
          font-size: 12.5px;
          font-weight: 600;
          color: #fff;
        }
        .confirm-delete-btns {
          display: flex;
          gap: 8px;
        }
        .confirm-delete-btn {
          padding: 4px 10px;
          border-radius: var(--lv-r-pill);
          border: 1px solid rgba(255, 255, 255, 0.25);
          background: rgba(255, 255, 255, 0.1);
          color: #fff;
          font-size: 11px;
          cursor: pointer;
          transition: all 200ms ease;
        }
        .confirm-delete-btn.yes:hover {
          background: #fff;
          color: var(--lv-danger);
        }
        .confirm-delete-btn.no:hover {
          background: rgba(255, 255, 255, 0.2);
        }

        /* Toasts alert bars */
        .ws-toast {
          display: flex;
          align-items: center;
          gap: 10px;
          padding: 12px 18px;
          border-radius: 8px;
          font-size: 13.5px;
          width: 100%;
        }
        .ws-toast.is-error {
          background: rgba(184, 92, 92, 0.08);
          border: 1px solid rgba(184, 92, 92, 0.2);
          color: #f7aaaa;
        }
        .ws-toast.is-success {
          background: rgba(127, 176, 145, 0.08);
          border: 1px solid rgba(127, 176, 145, 0.22);
          color: var(--lv-success);
        }
        .ws-permission-banner {
          background: rgba(255, 255, 255, 0.02);
          border: 1px solid var(--lv-line);
          border-radius: var(--lv-r-card);
          padding: 12px 16px;
          color: var(--lv-ink-2);
          font-size: 13px;
        }

        /* Skeletons */
        .lv-skel-grid {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
          gap: 24px;
        }
        .skel-card {
          display: flex;
          flex-direction: column;
          gap: 12px;
        }
        .skel-cover {
          aspect-ratio: 3 / 2;
          border-radius: var(--lv-r-card);
        }
        .skel-line {
          height: 14px;
          border-radius: var(--lv-r-pill);
        }

        /* Empty slate placeholders */
        .ws-empty-slate {
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          text-align: center;
          padding: 80px 24px;
          background: rgba(255, 255, 255, 0.01);
          border: 1px dashed var(--lv-line);
          border-radius: var(--lv-r-card);
        }

        /* Script fallback covers layout */
        .script-fallback-cover {
          position: absolute;
          inset: 0;
          background: linear-gradient(135deg, #10141e 0%, #06080d 100%);
          display: flex;
          flex-direction: column;
          justify-content: space-between;
          padding: 16px;
          z-index: 1;
        }
        .script-fallback-header {
          display: flex;
          justify-content: space-between;
          align-items: flex-start;
          width: 100%;
        }
        .script-fallback-title {
          font-family: var(--lv-ff-serif);
          font-size: 16px;
          font-weight: 500;
          color: var(--lv-accent);
          line-height: 1.3;
          margin-top: 24px;
          display: -webkit-box;
          WebkitBoxOrient: "vertical";
          WebkitLineClamp: 2;
          overflow: hidden;
        }
        .script-fallback-meta {
          display: flex;
          gap: 10px;
          font-size: 11px;
          color: var(--lv-ink-3);
        }
      `}</style>
    </main>
  );
}

// ====== SUB COMPONENTS ======

// Worlds Listing Skeletons
function WorldsGridSkeleton() {
  return (
    <div className="lv-skel-grid">
      {Array.from({ length: 4 }).map((_, i) => (
        <div key={i} className="skel-card">
          <div className="skel-cover lv-skel" />
          <div className="skel-line lv-skel" style={{ width: "60%" }} />
          <div className="skel-line lv-skel" style={{ width: "45%" }} />
        </div>
      ))}
    </div>
  );
}

// 1. World Draft Card Component
interface WorldDraftCardProps {
  draft: AdminWorldDraftListItem;
  busy: boolean;
  onOpen: () => void;
  confirmingDelete: boolean;
  onDeleteConfirm: (id: string) => void;
  onCancelDelete: () => void;
  onConfirmDelete: () => void;
}

function WorldDraftCard({
  draft,
  onOpen,
  confirmingDelete,
  onDeleteConfirm,
  onCancelDelete,
  onConfirmDelete,
}: WorldDraftCardProps) {
  const isGenerating = draft.generation_status === "pending" || draft.generation_status === "running";
  const isFailed = draft.generation_status === "failed";
  
  // Progress calculations
  const progressText = isGenerating ? "生成中" : isFailed ? "失败" : "草稿";
  const statusClass = isGenerating ? "generating" : isFailed ? "failed" : "draft";

  const handleCardClick = () => {
    if (confirmingDelete || isGenerating) return;
    onOpen();
  };

  return (
    <article className="world-card" onClick={handleCardClick}>
      <div className={`world-cover ${isGenerating ? "draft active" : "draft static"}`}>

        {/* Deletion confirmations overlay */}
        {confirmingDelete && (
          <div className="confirm-delete-overlay" onClick={(e) => e.stopPropagation()}>
            <span className="confirm-delete-title">确认丢弃此草稿？</span>
            <div className="confirm-delete-btns">
              <button className="confirm-delete-btn yes" onClick={onConfirmDelete}>丢弃</button>
              <button className="confirm-delete-btn no" onClick={onCancelDelete}>取消</button>
            </div>
          </div>
        )}

        {/* Scanning skeleton when generating */}
        {isGenerating && (
          <div className="skel-fill lv-skel" style={{ position: "absolute", inset: 0 }} />
        )}

        {/* Background gradient covers */}
        <div className={`world-cover-bg ${getGenreCoverClass((draft as { genre?: string | null }).genre, draft.name)}`} />

        {/* Cover image if the draft already has one (之前从不展示草稿封面，封面被埋没) */}
        {!isGenerating && draft.cover_image && (
          <div
            className="world-cover-bg"
            style={{ backgroundImage: `url(${ossThumb(draft.cover_image, 520)})` }}
          />
        )}

        {/* Central visual indicator —— 仅在没有封面（或生成中）时显示占位 */}
        {(isGenerating || !draft.cover_image) && (
          <div className="draft-mark">
            <div className={`draft-mark-icon ${isGenerating ? "spinner" : ""}`}>
              {isFailed ? "!" : isGenerating ? "" : "+"}
            </div>
            <span className="lv-t-caps" style={{ fontSize: 10 }}>
              {isFailed ? "生成失败 · 重试" : isGenerating ? "构筑场景中" : "待出封面"}
            </span>
          </div>
        )}

        {/* Left top badges */}
        <span className={`cover-status ${statusClass}`}>
          {progressText}
        </span>

        {/* Delete trigger */}
        {!isGenerating && !confirmingDelete && (
          <button
            className="card-action-btn"
            aria-label="删除"
            onClick={(e) => {
              e.stopPropagation();
              onDeleteConfirm(draft.id);
            }}
          >
            <Trash2 size={12} />
          </button>
        )}
      </div>

      <div className="world-card-body">
        <h3 className="lv-t-h3 world-title">{draft.name || "未命名草稿"}</h3>
        <div className="world-meta lv-t-meta">
          <span>{(draft as { genre?: string | null }).genre || "无特定分类"}</span>
          <span className="world-meta-sep">·</span>
          <span>草稿修改中</span>
        </div>
      </div>
    </article>
  );
}

// 2. World Saved Card Component (private / submitted / rejected / published)
interface WorldPublishedCardProps {
  world: AdminWorldPublishedItem;
  busy: boolean;
  onOpen: () => void;
  onPlay: () => void;
  onSubmit: () => void;
  onWithdrawSubmission: () => void;
  onUnpublish: () => void;
  confirmingDelete: boolean;
  onDeleteConfirm: (id: string) => void;
  onCancelDelete: () => void;
  onConfirmDelete: () => void;
}

function worldStatusBadge(world: AdminWorldPublishedItem): { label: string; color: string } {
  if (world.status === "published") return { label: "已发布", color: "var(--lv-accent)" };
  if (world.status === "withdrawn") return { label: "已下架", color: "var(--lv-danger)" };
  if (world.review_status === "submitted") return { label: "审核中", color: "var(--lv-accent-2)" };
  if (world.review_status === "rejected") return { label: "已驳回", color: "var(--lv-danger)" };
  return { label: "私有", color: "var(--lv-ink-2)" };
}

function WorldPublishedCard({
  world,
  busy,
  onOpen,
  onPlay,
  onSubmit,
  onWithdrawSubmission,
  onUnpublish,
  confirmingDelete,
  onDeleteConfirm,
  onCancelDelete,
  onConfirmDelete,
}: WorldPublishedCardProps) {
  const isOwner = world.is_owner;
  const badge = worldStatusBadge(world);

  // Owner clicks edit the draft; visitors (published worlds by others) preview.
  const handleCardClick = () => {
    if (confirmingDelete || busy) return;
    if (isOwner) onOpen();
    else onPlay();
  };

  return (
    <article className="world-card" onClick={handleCardClick}>
      <div className="world-cover">

        {confirmingDelete && (
          <div className="confirm-delete-overlay" onClick={(e) => e.stopPropagation()}>
            <span className="confirm-delete-title">确定要删除此世界及其关联的剧本么？</span>
            <div className="confirm-delete-btns">
              <button className="confirm-delete-btn yes" onClick={onConfirmDelete}>删除</button>
              <button className="confirm-delete-btn no" onClick={onCancelDelete}>取消</button>
            </div>
          </div>
        )}

        {/* Fallback covers rotating on genres */}
        <div className={`world-cover-bg ${getGenreCoverClass(world.genre, world.name)}`} />

        {/* Cover image if loaded */}
        {world.cover_image && (
          <div
            className="world-cover-bg"
            style={{ backgroundImage: `url(${ossThumb(world.cover_image, 520)})` }}
          />
        )}

        {/* Lifecycle status badge */}
        <span className="cover-status" style={{ color: badge.color, borderColor: "rgba(223, 194, 144, 0.2)" }}>
          {badge.label}
        </span>

        {/* Optimistic delete icon (owner only) */}
        {isOwner && !confirmingDelete && (
          <button
            className="card-action-btn"
            aria-label="删除世界"
            onClick={(e) => {
              e.stopPropagation();
              onDeleteConfirm(world.id);
            }}
          >
            <Trash2 size={12} />
          </button>
        )}
      </div>

      <div className="world-card-body">
        <h3 className="lv-t-h3 world-title">{world.name}</h3>
        <div className="world-meta lv-t-meta">
          <span>{world.genre || "未分类"}</span>
          <span className="world-meta-sep">·</span>
          <span>{world.era || "未知时代"}</span>
        </div>

        {isOwner && world.review_status === "rejected" && world.review_note && (
          <p className="lv-t-meta" style={{ color: "var(--lv-danger)", marginTop: 6 }}>
            驳回：{world.review_note}
          </p>
        )}

        {isOwner && (
          <div
            className="ws-card-actions"
            onClick={(e) => e.stopPropagation()}
            style={{ display: "flex", gap: 8, marginTop: 12, flexWrap: "wrap" }}
          >
            <button type="button" className="lv-btn lv-btn-sm" onClick={onPlay} disabled={busy}>
              试玩
            </button>
            {world.status === "published" ? (
              <button type="button" className="lv-btn lv-btn-sm" onClick={onUnpublish} disabled={busy}>
                下架
              </button>
            ) : world.review_status === "submitted" ? (
              <button
                type="button"
                className="lv-btn lv-btn-sm"
                onClick={onWithdrawSubmission}
                disabled={busy}
              >
                撤回提交
              </button>
            ) : (
              <button
                type="button"
                className="lv-btn lv-btn-primary lv-btn-sm"
                onClick={onSubmit}
                disabled={busy || !world.draft_id}
              >
                提交发布
              </button>
            )}
            <button type="button" className="lv-btn lv-btn-sm" onClick={onOpen} disabled={busy}>
              编辑
            </button>
          </div>
        )}
      </div>
    </article>
  );
}

// 3. Script Draft Card Component
interface ScriptDraftCardProps {
  draft: AdminScriptDraftListItem;
  onOpen: () => void;
  confirmingDelete: boolean;
  onDeleteConfirm: (id: string) => void;
  onCancelDelete: () => void;
  onConfirmDelete: () => void;
}

function ScriptDraftCard({
  draft,
  onOpen,
  confirmingDelete,
  onDeleteConfirm,
  onCancelDelete,
  onConfirmDelete,
}: ScriptDraftCardProps) {
  const t = useTranslations("workshopPage");
  const tCard = useTranslations("admin.workshop.card");
  const isGenerating = draft.generation_status === "pending" || draft.generation_status === "running";
  const isFailed = draft.generation_status === "failed";

  const statusText = isGenerating ? tCard("statusGenerating") : isFailed ? tCard("statusFailed") : tCard("statusDraft");
  const statusClass = isGenerating ? "generating" : isFailed ? "failed" : "draft";

  const handleCardClick = () => {
    if (confirmingDelete || isGenerating) return;
    onOpen();
  };

  return (
    <article className="world-card" onClick={handleCardClick}>
      <div className={`world-cover ${isGenerating ? "draft active" : "draft static"}`}>
        
        {confirmingDelete && (
          <div className="confirm-delete-overlay" onClick={(e) => e.stopPropagation()}>
            <span className="confirm-delete-title">确认丢弃此剧本草稿？</span>
            <div className="confirm-delete-btns">
              <button className="confirm-delete-btn yes" onClick={onConfirmDelete}>丢弃</button>
              <button className="confirm-delete-btn no" onClick={onCancelDelete}>取消</button>
            </div>
          </div>
        )}

        {isGenerating && (
          <div className="skel-fill lv-skel" style={{ position: "absolute", inset: 0, zIndex: 3 }} />
        )}

        {/* Fallback covers representation for scripts */}
        <div className="script-fallback-cover">
          <div className="script-fallback-header">
            <span className="lv-t-micro" style={{ color: "var(--lv-accent)", letterSpacing: "0.04em" }}>{t("fallbackScriptDraft")}</span>
            <BookOpen size={14} style={{ color: "var(--lv-accent)" }} />
          </div>
          <span className="script-fallback-title">{draft.name || "未命名剧本"}</span>
          <div className="script-fallback-meta">
            <span>草稿阶段</span>
          </div>
        </div>

        {/* Left top badges */}
        <span className={`cover-status ${statusClass}`} style={{ zIndex: 4 }}>
          {statusText}
        </span>

        {/* Delete trigger */}
        {!isGenerating && !confirmingDelete && (
          <button
            className="card-action-btn"
            aria-label="删除"
            style={{ zIndex: 5 }}
            onClick={(e) => {
              e.stopPropagation();
              onDeleteConfirm(draft.id);
            }}
          >
            <Trash2 size={12} />
          </button>
        )}
      </div>

      <div className="world-card-body">
        <h3 className="lv-t-h3 world-title">{draft.name || "未命名剧本草稿"}</h3>
        <div className="world-meta lv-t-meta">
          <span>线索收集</span>
          <span className="world-meta-sep">·</span>
          <span>草稿修改中</span>
        </div>
      </div>
    </article>
  );
}

// 4. Script Saved Card Component (private / submitted / rejected / published)
interface ScriptPublishedCardProps {
  script: AdminScriptPublishedItem;
  busy: boolean;
  onOpen: () => void;
  onPlay: () => void;
  onSubmit: () => void;
  onWithdrawSubmission: () => void;
  onUnpublish: () => void;
  confirmingDelete: boolean;
  onDeleteConfirm: (id: string) => void;
  onCancelDelete: () => void;
  onConfirmDelete: () => void;
}

function scriptStatusBadge(s: AdminScriptPublishedItem): { label: string; color: string } {
  if (s.status === "published") return { label: "已发布", color: "var(--lv-accent)" };
  if (s.status === "withdrawn") return { label: "已下架", color: "var(--lv-danger)" };
  if (s.review_status === "submitted") return { label: "审核中", color: "var(--lv-accent-2)" };
  if (s.review_status === "rejected") return { label: "已驳回", color: "var(--lv-danger)" };
  return { label: "私有", color: "var(--lv-ink-2)" };
}

function ScriptPublishedCard({
  script,
  busy,
  onOpen,
  onPlay,
  onSubmit,
  onWithdrawSubmission,
  onUnpublish,
  confirmingDelete,
  onDeleteConfirm,
  onCancelDelete,
  onConfirmDelete,
}: ScriptPublishedCardProps) {
  const t = useTranslations("workshopPage");
  const isOwner = script.is_owner;
  const badge = scriptStatusBadge(script);

  const handleCardClick = () => {
    if (confirmingDelete || busy) return;
    if (isOwner) onOpen();
    else onPlay();
  };

  return (
    <article className="world-card" onClick={handleCardClick}>
      <div className="world-cover">
        
        {confirmingDelete && (
          <div className="confirm-delete-overlay" onClick={(e) => e.stopPropagation()}>
            <span className="confirm-delete-title">确定要删除此发布剧本么？</span>
            <div className="confirm-delete-btns">
              <button className="confirm-delete-btn yes" onClick={onConfirmDelete}>删除</button>
              <button className="confirm-delete-btn no" onClick={onCancelDelete}>取消</button>
            </div>
          </div>
        )}

        {/* Cover illustration fallback or script spec details */}
        <div className="script-fallback-cover">
          <div className="script-fallback-header">
            <span className="lv-t-micro" style={{ color: "var(--lv-ink-3)", letterSpacing: "0.04em" }}>{t("fallbackPublishedScript")}</span>
            <BookOpen size={14} style={{ color: "var(--lv-ink-3)" }} />
          </div>
          <span className="script-fallback-title" style={{ color: "var(--lv-ink)" }}>{script.name}</span>
          <div className="script-fallback-meta">
            {script.difficulty ? (
              <span style={{ display: "inline-flex", alignItems: "center", gap: 3 }}>
                <Activity size={10} />
                {script.difficulty}
              </span>
            ) : null}
            {script.difficulty && script.estimated_time ? <span className="world-meta-sep">·</span> : null}
            {script.estimated_time ? (
              <span style={{ display: "inline-flex", alignItems: "center", gap: 3 }}>
                <Clock size={10} />
                {script.estimated_time}
              </span>
            ) : null}
          </div>
        </div>

        {/* Cover image if loaded */}
        {(script as { cover_image?: string | null }).cover_image && (
          <div 
            className="world-cover-bg" 
            style={{ backgroundImage: `url(${ossThumb((script as { cover_image?: string | null }).cover_image, 520)})`, zIndex: 2 }}
          />
        )}

        {/* Lifecycle status badge */}
        <span className="cover-status" style={{ color: badge.color, borderColor: "rgba(223, 194, 144, 0.2)", zIndex: 4 }}>
          {badge.label}
        </span>

        {/* Delete button (owner only) */}
        {isOwner && !confirmingDelete && (
          <button
            className="card-action-btn"
            aria-label="删除剧本"
            style={{ zIndex: 5 }}
            onClick={(e) => {
              e.stopPropagation();
              onDeleteConfirm(script.id);
            }}
          >
            <Trash2 size={12} />
          </button>
        )}
      </div>

      <div className="world-card-body">
        <h3 className="lv-t-h3 world-title">{script.name}</h3>
        {script.description ? (
          <div className="world-meta lv-t-meta">
            <span style={{
              display: "-webkit-box",
              WebkitBoxOrient: "vertical",
              WebkitLineClamp: 1,
              overflow: "hidden",
            }}>{script.description}</span>
          </div>
        ) : (
          <div className="world-meta lv-t-meta">
            <span>暂无简介描述</span>
          </div>
        )}

        {isOwner && script.review_status === "rejected" && script.review_note && (
          <p className="lv-t-meta" style={{ color: "var(--lv-danger)", marginTop: 6 }}>
            驳回：{script.review_note}
          </p>
        )}

        {isOwner && (
          <div
            className="ws-card-actions"
            onClick={(e) => e.stopPropagation()}
            style={{ display: "flex", gap: 8, marginTop: 12, flexWrap: "wrap" }}
          >
            <button type="button" className="lv-btn lv-btn-sm" onClick={onPlay} disabled={busy}>
              试玩
            </button>
            {script.status === "published" ? (
              <button type="button" className="lv-btn lv-btn-sm" onClick={onUnpublish} disabled={busy}>
                下架
              </button>
            ) : script.review_status === "submitted" ? (
              <button
                type="button"
                className="lv-btn lv-btn-sm"
                onClick={onWithdrawSubmission}
                disabled={busy}
              >
                撤回提交
              </button>
            ) : (
              <button
                type="button"
                className="lv-btn lv-btn-primary lv-btn-sm"
                onClick={onSubmit}
                disabled={busy || !script.draft_id}
              >
                提交发布
              </button>
            )}
            <button type="button" className="lv-btn lv-btn-sm" onClick={onOpen} disabled={busy}>
              编辑
            </button>
          </div>
        )}
      </div>
    </article>
  );
}

// ─────────────────────────────────────────────────────────
// 移动端工坊视图
// ─────────────────────────────────────────────────────────

type MobileTab = "drafts" | "worlds" | "scripts";

interface MobileWorkshopViewProps {
  worldsQuery: { data?: AdminWorldListResponse; isLoading: boolean };
  scriptsQuery: { data?: AdminScriptListResponse; isLoading: boolean };
  canCreate: boolean;
  busyTarget: string | null;
  onOpenWorldDraft: (id: string) => void;
  onOpenScriptDraft: (id: string) => void;
  onSubmitWorld: (draftId: string) => void;
  onWithdrawWorldSubmission: (draftId: string) => void;
  onUnpublishWorld: (worldId: string) => void;
  onSubmitScript: (draftId: string) => void;
  onWithdrawScriptSubmission: (draftId: string) => void;
  onUnpublishScript: (scriptId: string) => void;
  notice: string | null;
  error: string | null;
}

function MobileWorkshopView({
  worldsQuery,
  scriptsQuery,
  canCreate,
  busyTarget,
  onOpenWorldDraft,
  onOpenScriptDraft,
  onSubmitWorld,
  onWithdrawWorldSubmission,
  onUnpublishWorld,
  onSubmitScript,
  onWithdrawScriptSubmission,
  onUnpublishScript,
  notice,
  error,
}: MobileWorkshopViewProps) {
  const t = useTranslations("workshopPage");
  const tWorkshop = useTranslations("admin.workshop");
  const router = useRouter();
  const user = useAuthStore((s) => s.user);
  const [tab, setTab] = useState<MobileTab>("drafts");
  const [viewMode, setViewMode] = useState<"list" | "grid">("list");
  const [sheetOpen, setSheetOpen] = useState(false);

  const worldDrafts = useMemo(() => worldsQuery.data?.drafts ?? [], [worldsQuery.data?.drafts]);
  const worldsPublished = worldsQuery.data?.published ?? [];
  const scriptDrafts = useMemo(() => scriptsQuery.data?.drafts ?? [], [scriptsQuery.data?.drafts]);
  const scriptsPublished = scriptsQuery.data?.published ?? [];

  const inProgress = useMemo(
    () =>
      [...worldDrafts, ...scriptDrafts].filter(
        (d) => d.generation_status === "running" || d.generation_status === "pending",
      ),
    [worldDrafts, scriptDrafts],
  );

  // 列表/网格共用同一套 MobileWorkCardProps，直接换组件即可
  const CardComp: typeof MobileWorkCard = viewMode === "grid" ? MobileWorkGridTile : MobileWorkCard;

  const worldPrimaryAction = (world: AdminWorldPublishedItem) => {
    if (!world.is_owner) return { label: null, action: undefined, variant: "ghost" as const };
    if (world.status === "published") {
      return { label: "下架", action: () => onUnpublishWorld(world.id), variant: "ghost" as const };
    }
    if (world.review_status === "submitted") {
      return {
        label: "撤回",
        action: world.draft_id ? () => onWithdrawWorldSubmission(world.draft_id!) : undefined,
        variant: "ghost" as const,
      };
    }
    return {
      label: world.draft_id ? "发布" : null,
      action: world.draft_id ? () => onSubmitWorld(world.draft_id!) : undefined,
      variant: "primary" as const,
    };
  };

  const scriptPrimaryAction = (script: AdminScriptPublishedItem) => {
    if (!script.is_owner) return { label: null, action: undefined, variant: "ghost" as const };
    if (script.status === "published") {
      return { label: "下架", action: () => onUnpublishScript(script.id), variant: "ghost" as const };
    }
    if (script.review_status === "submitted") {
      return {
        label: "撤回",
        action: script.draft_id ? () => onWithdrawScriptSubmission(script.draft_id!) : undefined,
        variant: "ghost" as const,
      };
    }
    return {
      label: script.draft_id ? "发布" : null,
      action: script.draft_id ? () => onSubmitScript(script.draft_id!) : undefined,
      variant: "primary" as const,
    };
  };

  return (
    <div
      className="lv-workshop-mobile"
      style={{
        position: "relative",
        zIndex: 2,
        paddingBottom: "calc(76px + env(safe-area-inset-bottom))",
      }}
    >
      {(notice || error) && (
        <div
          style={{
            margin: "0 16px 8px",
            padding: "10px 12px",
            borderRadius: 12,
            background: error ? "rgba(200,125,112,0.12)" : "rgba(154,185,161,0.10)",
            border: error
              ? "1px solid rgba(200,125,112,0.28)"
              : "1px solid rgba(154,185,161,0.24)",
            color: error ? "var(--lv-danger)" : "var(--lv-success)",
            fontSize: 12.5,
          }}
        >
          {error || notice}
        </div>
      )}

      <div style={{ padding: "calc(env(safe-area-inset-top, 0px) + 16px) 12px 0" }}>
        {/* create card —— 文案左、按钮右，垂直居中，避免叠加 */}
        <section
          style={{
            margin: "8px 4px 12px",
            borderRadius: 22,
            border: "1px solid rgba(255,255,255,0.08)",
            background: "rgba(255,255,255,0.055)",
            padding: "15px 14px 14px 16px",
            display: "grid",
            gridTemplateColumns: "1fr auto",
            gap: 12,
            alignItems: "center",
          }}
        >
          <div style={{ minWidth: 0 }}>
            <div
              style={{
                fontFamily: "var(--lv-font-mono)",
                fontSize: 10,
                letterSpacing: "0.04em",
                color: "var(--lv-accent)",
                marginBottom: 6,
              }}
            >
              {t("eyebrow")}
            </div>
            <h1
              style={{
                fontFamily: "var(--lv-font-serif)",
                fontSize: 22,
                fontWeight: 500,
                lineHeight: 1.1,
                color: "var(--lv-ink)",
                marginBottom: 6,
              }}
            >
              {t("heroTitle")}
            </h1>
            <p
              style={{
                color: "var(--lv-ink-3)",
                fontSize: 12.5,
                lineHeight: 1.5,
                margin: 0,
              }}
            >
              {t("subtitle")}
            </p>
          </div>
          <button
            type="button"
            onClick={() => {
              if (!user) {
                router.push(buildLoginHref("/workshop"));
                return;
              }
              setSheetOpen(true);
            }}
            disabled={!canCreate && !!user}
            style={{
              height: 40,
              padding: "0 16px",
              borderRadius: 999,
              background: "rgba(245,242,235,0.95)",
              color: "var(--lv-bg)",
              display: "inline-flex",
              alignItems: "center",
              justifyContent: "center",
              gap: 6,
              fontSize: 13,
              fontWeight: 600,
              border: 0,
              cursor: !canCreate && !!user ? "not-allowed" : "pointer",
              opacity: !canCreate && !!user ? 0.5 : 1,
              whiteSpace: "nowrap",
              flexShrink: 0,
              alignSelf: "center",
            }}
          >
            <span style={{ fontSize: 18, lineHeight: 1, marginTop: -1 }}>+</span> {t("createCta")}
          </button>
        </section>

        {/* generation progress card(s) */}
        {inProgress.length > 0 && (
          <section
            style={{
              margin: "0 4px 12px",
              borderRadius: 18,
              border: "1px solid rgba(255,255,255,0.08)",
              background: "rgba(255,255,255,0.04)",
              padding: "10px 13px",
              display: "grid",
              gridTemplateColumns: "1fr auto",
              gap: 12,
              alignItems: "center",
            }}
          >
            <div style={{ minWidth: 0 }}>
              <h2
                style={{
                  fontFamily: "var(--lv-font-serif)",
                  fontSize: 17,
                  fontWeight: 500,
                  marginBottom: 4,
                  whiteSpace: "nowrap",
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                }}
              >
                {inProgress[0].name || "新草稿"} · 生成中
              </h2>
              <p style={{ color: "var(--lv-ink-3)", fontSize: 12, margin: 0 }}>
                {inProgress.length > 1
                  ? `还有 ${inProgress.length - 1} 个任务在跑`
                  : "封面图与设定正在生成"}
              </p>
            </div>
            <div
              style={{
                height: 30,
                padding: "0 10px",
                borderRadius: 999,
                background: "var(--lv-accent-soft)",
                color: "var(--lv-accent)",
                display: "inline-flex",
                alignItems: "center",
                fontFamily: "var(--lv-font-mono)",
                fontSize: 9,
                letterSpacing: "0.12em",
              }}
            >
              生成中
            </div>
          </section>
        )}

        {/* segmented */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(3, 1fr)",
            gap: 4,
            padding: 4,
            margin: "0 4px 12px",
            borderRadius: 999,
            border: "1px solid rgba(255,255,255,0.08)",
            background: "rgba(255,255,255,0.035)",
          }}
        >
          {(
            [
              { k: "drafts" as const, label: tWorkshop("filters.draft") },
              { k: "worlds" as const, label: tWorkshop("tabs.worlds") },
              { k: "scripts" as const, label: tWorkshop("tabs.scripts") },
            ]
          ).map((seg) => {
            const active = tab === seg.k;
            return (
              <button
                key={seg.k}
                type="button"
                onClick={() => setTab(seg.k)}
                style={{
                  height: 34,
                  borderRadius: 999,
                  border: 0,
                  background: active ? "rgba(245,242,235,0.90)" : "transparent",
                  color: active ? "var(--lv-bg)" : "var(--lv-ink-3)",
                  fontFamily: "var(--lv-font-mono)",
                  fontSize: 9,
                  letterSpacing: "0.14em",
                  cursor: "pointer",
                }}
              >
                {seg.label}
              </button>
            );
          })}
        </div>

        {/* section title + 视图切换（drafts/worlds/scripts 共用，照搬 discover） */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            padding: "0 4px 10px",
          }}
        >
          <h2
            style={{
              fontFamily: "var(--lv-font-serif)",
              fontSize: 21,
              fontWeight: 500,
              color: "var(--lv-ink)",
            }}
          >
            {tab === "drafts" ? t("tabDrafts") : tab === "worlds" ? t("tabWorlds") : t("tabScripts")}
          </h2>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <span
              style={{
                fontFamily: "var(--lv-font-mono)",
                fontSize: 9,
                letterSpacing: "0.14em",
                color: "var(--lv-ink-4)",
              }}
            >
              {tab === "drafts"
                ? `${worldDrafts.length + scriptDrafts.length} items`
                : tab === "worlds"
                  ? `${worldsPublished.length} items`
                  : `${scriptsPublished.length} items`}
            </span>
            <div
              style={{
                height: 34,
                display: "grid",
                gridTemplateColumns: "repeat(2, 34px)",
                borderRadius: 999,
                border: "1px solid rgba(255,255,255,0.08)",
                background: "rgba(255,255,255,0.025)",
                overflow: "hidden",
              }}
            >
              <button
                type="button"
                aria-label="网格视图"
                onClick={() => setViewMode("grid")}
                style={{
                  display: "grid",
                  placeItems: "center",
                  background: viewMode === "grid" ? "rgba(255,255,255,0.10)" : "transparent",
                  color: viewMode === "grid" ? "var(--lv-ink)" : "var(--lv-ink-3)",
                  border: 0,
                  cursor: "pointer",
                }}
              >
                <LayoutGrid size={16} />
              </button>
              <button
                type="button"
                aria-label="列表视图"
                onClick={() => setViewMode("list")}
                style={{
                  display: "grid",
                  placeItems: "center",
                  background: viewMode === "list" ? "rgba(255,255,255,0.10)" : "transparent",
                  color: viewMode === "list" ? "var(--lv-ink)" : "var(--lv-ink-3)",
                  border: 0,
                  cursor: "pointer",
                }}
              >
                <ListIcon size={16} />
              </button>
            </div>
          </div>
        </div>

        {/* list / grid */}
        <div
          style={
            viewMode === "grid"
              ? { display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: "16px 10px", paddingBottom: 8 }
              : { display: "flex", flexDirection: "column", gap: 9, paddingBottom: 8 }
          }
        >
          {tab === "drafts" && (
            <>
              {worldDrafts.length + scriptDrafts.length === 0 ? (
                <EmptyHint loading={worldsQuery.isLoading} text={t("emptyDrafts")} />
              ) : (
                <>
                  {worldDrafts.map((d) => (
                    <CardComp
                      key={d.id}
                      cover={null}
                      status={d.generation_status === "running" ? "running" : "draft"}
                      kind="world"
                      title={d.name || "未命名世界"}
                      desc={d.description || "草稿，等待你补完。"}
                      updatedAt={d.updated_at}
                      busy={busyTarget === (d.world_id ?? d.id)}
                      onEdit={() =>
                        d.world_id
                          ? onOpenWorldDraft(d.world_id)
                          : router.push(`/workshop/worlds/drafts/${d.id}`)
                      }
                    />
                  ))}
                  {scriptDrafts.map((d) => (
                    <CardComp
                      key={d.id}
                      cover={null}
                      status={d.generation_status === "running" ? "running" : "draft"}
                      kind="script"
                      title={d.name || "未命名剧本"}
                      desc={d.description || "草稿，等待你补完。"}
                      updatedAt={d.updated_at}
                      busy={busyTarget === d.id}
                      onEdit={() =>
                        router.push(`/workshop/scripts/drafts/${d.id}`)
                      }
                    />
                  ))}
                </>
              )}
            </>
          )}

          {tab === "worlds" && (
            <>
              {worldsPublished.length === 0 ? (
                <EmptyHint loading={worldsQuery.isLoading} text={t("emptyWorlds")} />
              ) : (
                worldsPublished.map((w) => {
                  const primary = worldPrimaryAction(w);
                  return (
                    <CardComp
                      key={w.id}
                      cover={w.cover_image}
                      status="published"
                      badgeLabel={worldStatusBadge(w).label}
                      badgeColor={worldStatusBadge(w).color}
                      isOwner={w.is_owner}
                      kind="world"
                      title={w.name}
                      desc={w.description}
                      updatedAt={null}
                      bottomMeta={`${w.script_count} 剧本`}
                      busy={busyTarget === w.id}
                      onEdit={() => onOpenWorldDraft(w.id)}
                      onPlay={() => router.push(withReturn(`/worlds/${w.id}`, "/workshop"))}
                      primaryActionLabel={primary.label}
                      onPrimaryAction={primary.action}
                      primaryActionVariant={primary.variant}
                    />
                  );
                })
              )}
            </>
          )}

          {tab === "scripts" && (
            <>
              {scriptsPublished.length === 0 ? (
                <EmptyHint loading={scriptsQuery.isLoading} text={t("emptyScripts")} />
              ) : (
                scriptsPublished.map((s) => {
                  const primary = scriptPrimaryAction(s);
                  return (
                    <CardComp
                      key={s.id}
                      cover={null}
                      status="published"
                      badgeLabel={scriptStatusBadge(s).label}
                      badgeColor={scriptStatusBadge(s).color}
                      isOwner={s.is_owner}
                      kind="script"
                      title={s.name}
                      desc={s.description}
                      updatedAt={null}
                      bottomMeta={`难度 ${s.difficulty} · ${s.estimated_time}`}
                      busy={busyTarget === s.id}
                      onEdit={() => onOpenScriptDraft(s.id)}
                      onPlay={() => {
                        const wid = scriptsQuery.data?.world?.id;
                        if (wid) router.push(withReturn(`/worlds/${wid}`, "/workshop?tab=scripts"));
                      }}
                      primaryActionLabel={primary.label}
                      onPrimaryAction={primary.action}
                      primaryActionVariant={primary.variant}
                    />
                  );
                })
              )}
            </>
          )}
        </div>
      </div>

      {/* create bottom sheet */}
      <AnimatePresence>
        {sheetOpen && (
          <>
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => setSheetOpen(false)}
              style={{
                position: "fixed",
                inset: 0,
                background: "rgba(0,0,0,0.55)",
                zIndex: 80,
              }}
            />
            <motion.div
              initial={{ y: "100%" }}
              animate={{ y: 0 }}
              exit={{ y: "100%" }}
              transition={{ type: "spring", stiffness: 320, damping: 32 }}
              style={{
                position: "fixed",
                left: 0,
                right: 0,
                bottom: 0,
                zIndex: 81,
                background: "var(--lv-bg-1)",
                borderTopLeftRadius: 22,
                borderTopRightRadius: 22,
                padding: "12px 16px calc(20px + env(safe-area-inset-bottom))",
                boxShadow: "0 -20px 40px rgba(0,0,0,0.55)",
              }}
            >
              <div
                aria-hidden
                style={{
                  width: 44,
                  height: 4,
                  borderRadius: 999,
                  background: "rgba(255,255,255,0.18)",
                  margin: "4px auto 16px",
                }}
              />
              <h3
                style={{
                  fontFamily: "var(--lv-font-serif)",
                  fontSize: 18,
                  fontWeight: 500,
                  color: "var(--lv-ink)",
                  marginBottom: 12,
                }}
              >
                创建
              </h3>
              <Link
                href="/workshop/generate/world"
                onClick={() => setSheetOpen(false)}
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  padding: "14px 16px",
                  borderRadius: 14,
                  border: "1px solid rgba(255,255,255,0.08)",
                  background: "rgba(255,255,255,0.035)",
                  textDecoration: "none",
                  color: "var(--lv-ink)",
                  marginBottom: 8,
                }}
              >
                <div>
                  <div style={{ fontWeight: 600, fontSize: 14 }}>生成世界</div>
                  <div style={{ color: "var(--lv-ink-3)", fontSize: 12, marginTop: 2 }}>
                    用一句话描述，AI 帮你生成完整世界设定。
                  </div>
                </div>
                <span style={{ color: "var(--lv-ink-3)", fontFamily: "var(--lv-font-mono)" }}>→</span>
              </Link>
              <Link
                href="/workshop/generate/script"
                onClick={() => setSheetOpen(false)}
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  padding: "14px 16px",
                  borderRadius: 14,
                  border: "1px solid rgba(255,255,255,0.08)",
                  background: "rgba(255,255,255,0.035)",
                  textDecoration: "none",
                  color: "var(--lv-ink)",
                }}
              >
                <div>
                  <div style={{ fontWeight: 600, fontSize: 14 }}>生成剧本</div>
                  <div style={{ color: "var(--lv-ink-3)", fontSize: 12, marginTop: 2 }}>
                    给已有世界加一条剧情线、目标和结局。
                  </div>
                </div>
                <span style={{ color: "var(--lv-ink-3)", fontFamily: "var(--lv-font-mono)" }}>→</span>
              </Link>
            </motion.div>
          </>
        )}
      </AnimatePresence>

    </div>
  );
}

function EmptyHint({ loading, text }: { loading: boolean; text: string }) {
  return (
    <p
      style={{
        gridColumn: "1 / -1", // 网格视图下跨满两列；flex 下无副作用
        margin: "0 0 8px",
        padding: "16px 14px",
        borderRadius: 16,
        border: "1px dashed rgba(255,255,255,0.08)",
        color: "var(--lv-ink-3)",
        fontSize: 12.5,
      }}
    >
      {loading ? "" : text}
    </p>
  );
}

interface MobileWorkCardProps {
  cover: string | null;
  status: "draft" | "running" | "published";
  kind: "world" | "script";
  title: string;
  desc: string;
  updatedAt: string | null;
  bottomMeta?: string;
  busy: boolean;
  onEdit: () => void;
  // Lifecycle (saved worlds/scripts). When badgeLabel is provided it overrides
  // the legacy status label; when primaryActionLabel is provided the row shows
  // owner lifecycle buttons (试玩 + the primary action) instead of 查看/编辑.
  badgeLabel?: string;
  badgeColor?: string;
  isOwner?: boolean;
  onPlay?: () => void;
  primaryActionLabel?: string | null;
  onPrimaryAction?: () => void;
  primaryActionVariant?: MobileActionVariant;
}

function MobileWorkCard({
  cover,
  status,
  kind,
  title,
  desc,
  updatedAt,
  bottomMeta,
  busy,
  onEdit,
  badgeLabel,
  badgeColor,
  isOwner = true,
  onPlay,
  primaryActionLabel,
  onPrimaryAction,
  primaryActionVariant = "ghost",
}: MobileWorkCardProps) {
  const statusLabel =
    badgeLabel ??
    (status === "running" ? "生成中" : status === "published" ? "已发布" : "草稿");
  const statusColor =
    badgeColor ??
    (status === "running"
      ? "var(--lv-accent)"
      : status === "published"
        ? "var(--lv-success)"
        : "var(--lv-accent)");


  const updated = updatedAt ? parseBackendIso(updatedAt) : null;
  const updatedLabel = updated
    ? `${kind === "world" ? "世界" : "剧本"} · ${updated.toLocaleDateString("zh-CN", { month: "short", day: "numeric" })}`
    : `${kind === "world" ? "世界" : "剧本"} · 已发布`;

  const onCardTap = busy ? undefined : isOwner ? onEdit : onPlay;
  return (
    <article
      onClick={onCardTap}
      style={{
        display: "grid",
        gridTemplateColumns: "40% 1fr",
        minHeight: 168,
        borderRadius: 20,
        overflow: "hidden",
        border: "1px solid rgba(255,255,255,0.08)",
        background: "rgba(255,255,255,0.055)",
        cursor: busy ? "wait" : "pointer",
        opacity: busy ? 0.6 : 1,
      }}
    >
      <div
        className={cover ? undefined : getGenreCoverClass(null, title)}
        style={{
          position: "relative",
          backgroundImage: cover ? `url(${ossThumb(cover, 520)})` : undefined,
          backgroundSize: "cover",
          backgroundPosition: "center",
        }}
      >
        <div
          style={{
            position: "absolute",
            left: 8,
            top: 8,
            height: 22,
            padding: "0 8px",
            borderRadius: 999,
            background: "rgba(5,5,7,0.64)",
            backdropFilter: "blur(12px)",
            border: "1px solid rgba(255,255,255,0.12)",
            display: "inline-flex",
            alignItems: "center",
            fontFamily: "var(--lv-font-mono)",
            fontSize: 9,
            letterSpacing: "0.12em",
            color: statusColor,
          }}
        >
          {statusLabel}
        </div>
      </div>
      <div style={{ padding: "13px 12px 10px", display: "flex", flexDirection: "column", minWidth: 0 }}>
        <span
          style={{
            fontFamily: "var(--lv-font-mono)",
            fontSize: 9,
            letterSpacing: "0.14em",
            color: "var(--lv-ink-3)",
            marginBottom: 4,
          }}
        >
          {updatedLabel}
        </span>
        <h3
          style={{
            fontFamily: "var(--lv-font-serif)",
            fontSize: 20,
            fontWeight: 500,
            lineHeight: 1.1,
            color: "var(--lv-ink)",
            whiteSpace: "nowrap",
            overflow: "hidden",
            textOverflow: "ellipsis",
            marginBottom: 7,
          }}
        >
          {title}
        </h3>
        <p
          style={{
            color: "var(--lv-ink-2)",
            fontSize: 12,
            lineHeight: 1.42,
            display: "-webkit-box",
            WebkitLineClamp: 2,
            WebkitBoxOrient: "vertical",
            overflow: "hidden",
            margin: 0,
          }}
        >
          {desc}
        </p>
        <div
          style={{
            marginTop: "auto",
            paddingTop: 8,
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: 8,
          }}
        >
          <span
            style={{
              fontFamily: "var(--lv-font-mono)",
              fontSize: 9,
              letterSpacing: "0.12em",
              color: "var(--lv-ink-4)",
            }}
          >
            {bottomMeta || (status === "published" ? "已发布" : "草稿")}
          </span>
          {primaryActionLabel && isOwner ? (
            <span
              style={{
                display: "inline-flex",
                alignItems: "center",
                justifyContent: "flex-end",
                gap: 6,
                flexShrink: 0,
              }}
              onClick={(e) => e.stopPropagation()}
            >
              <button
                type="button"
                onClick={onPlay}
                disabled={busy}
                style={mobileWorkshopActionButtonStyle("ghost")}
              >
                试玩
              </button>
              <button
                type="button"
                onClick={onPrimaryAction}
                disabled={busy}
                style={mobileWorkshopActionButtonStyle(primaryActionVariant)}
              >
                {primaryActionLabel}
              </button>
            </span>
          ) : (
            <span
              style={{
                height: 34,
                minWidth: 52,
                padding: "0 12px",
                borderRadius: 999,
                border: "1px solid rgba(255,255,255,0.12)",
                background: "rgba(255,255,255,0.05)",
                color: "var(--lv-ink)",
                display: "inline-flex",
                alignItems: "center",
                justifyContent: "center",
                fontSize: 12,
                fontWeight: 500,
                letterSpacing: "0.04em",
              }}
            >
              {isOwner ? "编辑" : "查看"}
            </span>
          )}
        </div>
      </div>
    </article>
  );
}

// Grid 视图瓦片：16:10 封面 + 状态角标 + 标题/题材（对齐 discover 的 MobileWorldGridTile）。
// 复用 MobileWorkCardProps，与 MobileWorkCard 可直接互换。
function MobileWorkGridTile({
  cover,
  status,
  kind,
  title,
  bottomMeta,
  busy,
  onEdit,
  badgeLabel,
  badgeColor,
  isOwner = true,
  onPlay,
  primaryActionLabel,
  onPrimaryAction,
  primaryActionVariant = "ghost",
}: MobileWorkCardProps) {
  const statusLabel =
    badgeLabel ??
    (status === "running" ? "生成中" : status === "published" ? "已发布" : "草稿");
  const statusColor =
    badgeColor ??
    (status === "running"
      ? "var(--lv-accent)"
      : status === "published"
        ? "var(--lv-success)"
        : "var(--lv-accent)");
  const onCardTap = busy ? undefined : isOwner ? onEdit : onPlay;

  return (
    <article
      onClick={onCardTap}
      style={{ minWidth: 0, cursor: busy ? "wait" : "pointer", opacity: busy ? 0.6 : 1 }}
    >
      <div
        className={cover ? undefined : getGenreCoverClass(null, title)}
        style={{
          position: "relative",
          aspectRatio: "16 / 10",
          borderRadius: 12,
          overflow: "hidden",
          border: "1px solid rgba(255,255,255,0.08)",
          backgroundImage: cover ? `url(${ossThumb(cover, 520)})` : undefined,
          backgroundSize: "cover",
          backgroundPosition: "center",
        }}
      >
        <div
          style={{
            position: "absolute",
            left: 8,
            top: 8,
            height: 22,
            padding: "0 8px",
            borderRadius: 999,
            background: "rgba(5,5,7,0.64)",
            backdropFilter: "blur(12px)",
            border: "1px solid rgba(255,255,255,0.12)",
            display: "inline-flex",
            alignItems: "center",
            fontFamily: "var(--lv-font-mono)",
            fontSize: 9,
            letterSpacing: "0.12em",
            color: statusColor,
          }}
        >
          {statusLabel}
        </div>
      </div>
      <div style={{ padding: "7px 2px 0", minWidth: 0 }}>
        <h3
          style={{
            fontFamily: "var(--lv-font-serif)",
            fontSize: 15,
            fontWeight: 500,
            color: "var(--lv-ink)",
            whiteSpace: "nowrap",
            overflow: "hidden",
            textOverflow: "ellipsis",
            margin: 0,
          }}
        >
          {title}
        </h3>
        <span
          style={{
            display: "block",
            marginTop: 3,
            fontFamily: "var(--lv-font-mono)",
            fontSize: 9,
            letterSpacing: "0.12em",
            color: "var(--lv-ink-3)",
            whiteSpace: "nowrap",
            overflow: "hidden",
            textOverflow: "ellipsis",
          }}
        >
          {bottomMeta || (kind === "world" ? "世界" : "剧本")}
        </span>
        {primaryActionLabel && isOwner ? (
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              onPrimaryAction?.();
            }}
            disabled={busy}
            style={{
              marginTop: 8,
              ...mobileWorkshopActionButtonStyle(primaryActionVariant, {
                minWidth: primaryActionVariant === "primary" ? 56 : 52,
              }),
            }}
          >
            {primaryActionLabel}
          </button>
        ) : null}
      </div>
    </article>
  );
}
