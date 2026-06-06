"use client";

interface SectionNavProps {
  sections: { id: string; label: string }[];
  activeSection: string;
  onSectionClick: (id: string) => void;
}

export function SectionNav({ sections, activeSection, onSectionClick }: SectionNavProps) {
  const handleClick = (id: string) => {
    onSectionClick(id);
    const el = document.getElementById(id);
    if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  };

  return (
    <nav className="sticky top-32 hidden lg:block">
      <ul className="flex flex-col gap-1">
        {sections.map((section) => {
          const isActive = section.id === activeSection;
          return (
            <li key={section.id}>
              <button
                type="button"
                onClick={() => handleClick(section.id)}
                className={`w-full rounded-sm px-3 py-2 text-left text-body-sm transition-colors ${
                  isActive
                    ? "border-l-2 border-accent bg-accent-soft text-accent"
                    : "text-text-muted hover:text-text-secondary"
                }`}
                style={{ transitionDuration: "var(--duration-fast)" }}
              >
                {section.label}
              </button>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
