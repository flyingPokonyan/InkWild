/**
 * 阿里云 OSS 图片实时处理：按渲染尺寸缩放 + 转 WebP。
 *
 * 封面/hero 原图常是 1-3MB 的 PNG，直接怼给手机当缩略图极浪费。
 * OSS 支持 `?x-oss-process=image/resize,...` 实时出图：缩到目标宽 + webp 后通常 10-30KB。
 * 实测同一张封面：原图 2.4MB → w_400/webp 9KB（265×）。
 *
 * 非 OSS URL（本地 / data URI / 占位图）或已带处理参数的，原样返回。
 */
export function ossThumb(
  url: string | null | undefined,
  width: number,
  opts?: { quality?: number; dpr?: number },
): string {
  if (!url) return "";
  if (!url.includes("aliyuncs.com")) return url;
  if (url.includes("x-oss-process")) return url;
  const dpr = opts?.dpr ?? 2; // 默认按 2x retina 取图
  const quality = opts?.quality ?? 80;
  const w = Math.max(1, Math.round(width * dpr));
  const sep = url.includes("?") ? "&" : "?";
  // m_lfit：限定在目标宽内、保持比例、绝不放大原图
  return `${url}${sep}x-oss-process=image/resize,w_${w},m_lfit/format,webp/quality,q_${quality}`;
}

/**
 * Full-bleed hero images need more pixels than card thumbnails, especially on
 * retina laptops / large desktop monitors. OSS will not upscale smaller source
 * images because we use m_lfit, so this mainly protects high-resolution uploads.
 */
export function ossHero(url: string | null | undefined): string {
  return ossThumb(url, 1600, { quality: 90 });
}
