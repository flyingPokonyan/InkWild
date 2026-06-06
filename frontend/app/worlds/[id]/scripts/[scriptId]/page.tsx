import { dehydrate, HydrationBoundary, QueryClient } from "@tanstack/react-query";

import { fetchWorldDetail, worldsQueryKeys } from "@/lib/api/worlds";

import { ScriptDetailClient } from "./ScriptDetailClient";

// Server Component：预取所属世界详情并 hydrate。剧本详情页用 useWorldDetail(id) 取世界、
// 再从 world.scripts 里定位该剧本，所以预取 world 即可让首帧命中缓存、内容直接 SSR。
// 详见同级 ../page.tsx 注释（公开接口、私有/404 兜底）。
export default async function ScriptDetailPage({
  params,
}: {
  params: Promise<{ id: string; scriptId: string }>;
}) {
  const { id } = await params;

  const queryClient = new QueryClient();
  await queryClient.prefetchQuery({
    queryKey: worldsQueryKeys.detail(id),
    queryFn: () => fetchWorldDetail(id),
  });

  return (
    <HydrationBoundary state={dehydrate(queryClient)}>
      <ScriptDetailClient />
    </HydrationBoundary>
  );
}
