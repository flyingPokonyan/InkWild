"use client";

import { useTranslations } from "next-intl";

interface ImageProps {
  url?: string | null;
  label: string;
  type?: "cover" | "poster" | "banner";
}

export function ImageGallery({ images }: { images: ImageProps[] }) {
  const t = useTranslations("admin.image");

  const aspectClass = (type?: "cover" | "poster" | "banner") => {
    if (type === "poster") return "aspect-[2/3]";
    if (type === "banner") return "aspect-video";
    return "aspect-[3/4]";
  };

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6 w-full">
      {images.map((img, i) => (
        <div key={i} className="flex flex-col gap-3">
          <div
            className={`relative w-full overflow-hidden ${aspectClass(img.type)} ${
              img.url
                ? "border border-white/10 bg-white/5"
                : "border border-dashed border-white/10 bg-white/5 flex items-center justify-center p-6"
            }`}
            style={{ borderRadius: "var(--lv-r-card)" }}
          >
            {img.url ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={img.url}
                alt={img.label}
                className="absolute inset-0 w-full h-full object-cover opacity-90 transition-transform duration-200 hover:scale-[1.02]"
                style={{ transitionTimingFunction: "var(--lv-ease)" }}
              />
            ) : (
              <div className="text-center">
                <svg
                  className="w-8 h-8 mx-auto mb-3"
                  style={{ color: "var(--lv-ink-4)" }}
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={1.5}
                    d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"
                  />
                </svg>
                <span className="lv-t-micro">{t("empty")}</span>
              </div>
            )}
          </div>
          <div className="text-center">
            <span className="lv-t-caps">{img.label}</span>
          </div>
        </div>
      ))}
    </div>
  );
}
