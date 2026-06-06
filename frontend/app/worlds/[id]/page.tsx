import { dehydrate, HydrationBoundary, QueryClient } from "@tanstack/react-query";

import { fetchWorldDetail, worldsQueryKeys } from "@/lib/api/worlds";

import { WorldDetailClient } from "./WorldDetailClient";

// Server Component：在服务端预取世界详情并 dehydrate，交给 HydrationBoundary。
// 这样客户端 useWorldDetail 首帧即命中缓存（isLoading=false），世界内容直接 SSR，
// 不再先闪 LoadingPulse；对公开世界爬虫也能拿到真实内容（LCP/SEO）。
// world 详情接口 get_current_user_optional → 公开，服务端无 cookie 可取已发布世界；
// 私有/404 时 prefetchQuery 不抛、失败查询不进 dehydrate，客户端再带 cookie 兜底取数。
export default async function WorldPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;

  const queryClient = new QueryClient();
  await queryClient.prefetchQuery({
    queryKey: worldsQueryKeys.detail(id),
    queryFn: () => fetchWorldDetail(id),
  });

  return (
    <HydrationBoundary state={dehydrate(queryClient)}>
      <WorldDetailClient />
    </HydrationBoundary>
  );
}
