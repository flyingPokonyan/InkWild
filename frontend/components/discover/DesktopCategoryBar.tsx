"use client";

import { CATEGORIES } from "./url-state";

export function DesktopCategoryBar({
  active,
  onClick,
}: {
  active: string;
  onClick: (cat: string) => void;
}) {
  return (
    <div className="category-rail-wrapper">
      <div className="category-rail">
        {CATEGORIES.map((cat) => (
          <button
            key={cat}
            type="button"
            onClick={() => onClick(cat)}
            className={`category-pill ${active === cat ? "active" : ""}`}
          >
            {cat}
          </button>
        ))}
      </div>
    </div>
  );
}
