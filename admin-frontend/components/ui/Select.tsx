"use client";

import { ChevronDown } from "lucide-react";
import { useEffect, useRef, useState } from "react";

export interface SelectOption {
  value: string;
  label: string;
  meta?: string;
  icon?: React.ReactNode;
}

export interface SelectGroup {
  label: string;
  options: SelectOption[];
}

interface Props {
  value: string;
  onChange: (v: string) => void;
  options?: SelectOption[];
  groups?: SelectGroup[];
  placeholder?: string;
  minWidth?: number;
  menuWidth?: number;
  renderValue?: (option: SelectOption | undefined) => React.ReactNode;
}

export function Select({
  value,
  onChange,
  options,
  groups,
  placeholder = "选择…",
  minWidth,
  menuWidth,
  renderValue,
}: Props) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function onDoc(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  const flat = groups ? groups.flatMap((g) => g.options) : options || [];
  const selected = flat.find((o) => o.value === value);

  return (
    <div className="select" ref={ref} style={{ minWidth }}>
      <button
        type="button"
        className="select-trigger"
        onClick={() => setOpen(!open)}
        style={{ minWidth }}
      >
        {renderValue ? (
          renderValue(selected)
        ) : selected ? (
          <span
            style={{
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
            }}
          >
            {selected.label}
          </span>
        ) : (
          <span className="dim-2">{placeholder}</span>
        )}
        <span className="select-caret">
          <ChevronDown size={10} />
        </span>
      </button>
      {open && (
        <div className="select-menu" style={{ minWidth: menuWidth }}>
          {groups
            ? groups.map((g, gi) => (
                <div key={gi}>
                  <div className="select-menu-group">{g.label}</div>
                  {g.options.map((o) => (
                    <div
                      key={o.value}
                      className="select-opt"
                      data-active={o.value === value || undefined}
                      onClick={() => {
                        onChange(o.value);
                        setOpen(false);
                      }}
                    >
                      {o.icon}
                      <span>{o.label}</span>
                      {o.meta && (
                        <span className="select-opt-meta">{o.meta}</span>
                      )}
                    </div>
                  ))}
                </div>
              ))
            : options?.map((o) => (
                <div
                  key={o.value}
                  className="select-opt"
                  data-active={o.value === value || undefined}
                  onClick={() => {
                    onChange(o.value);
                    setOpen(false);
                  }}
                >
                  {o.icon}
                  <span>{o.label}</span>
                  {o.meta && <span className="select-opt-meta">{o.meta}</span>}
                </div>
              ))}
        </div>
      )}
    </div>
  );
}
