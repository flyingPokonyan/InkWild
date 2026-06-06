import type { WorldListItem } from "@/lib/types";

import { PosterCard } from "@/components/ui/PosterCard";

/**
 * 世界卡片（旧 wrapper）。新代码请直接用 `<PosterCard />`。
 * 保留此组件作为类型适配，避免外部引用断裂；字段守纪见 §7.1。
 */
export function WorldCard({ world }: { world: WorldListItem }) {
  return (
    <PosterCard
      href={`/worlds/${world.id}`}
      title={world.name}
      genre={world.genre}
      era={world.era}
      description={world.description}
      coverImage={world.cover_image}
      difficulty={world.difficulty}
      estimatedTime={world.estimated_time}
      hasScript={world.has_script}
    />
  );
}
