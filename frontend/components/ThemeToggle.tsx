"use client";

// System / light / dark. The choice lives on <html data-theme> (see the inline
// script in layout.tsx, which applies it before first paint to avoid a flash).

import { useEffect, useState } from "react";
import { Monitor, Moon, Sun } from "lucide-react";
import { THEME_KEY as KEY } from "../lib/themeScript";

type Theme = "system" | "light" | "dark";
const ORDER: Theme[] = ["system", "light", "dark"];

export function applyTheme(theme: Theme) {
  const root = document.documentElement;
  if (theme === "system") root.removeAttribute("data-theme");
  else root.setAttribute("data-theme", theme);
  try { localStorage.setItem(KEY, theme); } catch { /* storage blocked */ }
}

export default function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>("system");
  useEffect(() => {
    try { setTheme((localStorage.getItem(KEY) as Theme) || "system"); } catch { /* ignore */ }
  }, []);
  const next = () => {
    const t = ORDER[(ORDER.indexOf(theme) + 1) % ORDER.length];
    setTheme(t);
    applyTheme(t);
  };
  const Icon = theme === "dark" ? Moon : theme === "light" ? Sun : Monitor;
  return (
    <button type="button" onClick={next} aria-label={`Theme: ${theme}. Click to change.`} title={`Theme: ${theme}`}
            className="flex h-8 w-8 items-center justify-center rounded-full border border-stone-200 bg-white text-stone-600 transition-colors hover:text-ink">
      <Icon className="h-3.5 w-3.5" aria-hidden="true" />
    </button>
  );
}
