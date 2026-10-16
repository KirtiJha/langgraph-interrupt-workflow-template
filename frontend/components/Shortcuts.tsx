"use client";

// "?" opens this overlay. The same list is the source of truth for the hints.

import { useEffect } from "react";
import { createPortal } from "react-dom";
import { Keyboard, X } from "lucide-react";

export const SHORTCUTS: [string, string][] = [
  ["J / K", "Next / previous action"],
  ["A", "Approve the focused action"],
  ["E", "Edit it before it runs"],
  ["R", "Reject it with a reason"],
  ["Shift + A", "Approve everything shown"],
  ["L", "Approve all low-risk actions"],
  ["1 – 9", "Pick an option when the steward asks"],
  ["B", "Board (on phones and tablets)"],
  ["?", "Show this list"],
  ["Esc", "Close dialogs and drawers"],
];

export default function Shortcuts({ onClose }: { onClose: () => void }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => (e.key === "Escape" || e.key === "?") && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return createPortal(
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div role="dialog" aria-modal="true" aria-labelledby="shortcuts-title" className="w-full max-w-sm rounded-2xl bg-paper p-5 shadow-lift animate-pop">
        <div className="flex items-center gap-2">
          <Keyboard className="h-4 w-4 text-ember-600" aria-hidden="true" />
          <h2 id="shortcuts-title" className="text-base font-semibold text-ink">Keyboard shortcuts</h2>
          <button type="button" onClick={onClose} className="ml-auto rounded-full p-1 text-stone-500 hover:bg-stone-100" aria-label="Close"><X className="h-4 w-4" aria-hidden="true" /></button>
        </div>
        <dl className="mt-4 space-y-2 text-sm">
          {SHORTCUTS.map(([k, v]) => (
            <div key={k} className="flex items-center justify-between gap-4">
              <dt className="flex gap-1">{k.split(" ").map((p, i) => p === "/" || p === "+" || p === "–" ? <span key={i} className="text-stone-400">{p}</span> : <kbd key={i} className="kbd">{p}</kbd>)}</dt>
              <dd className="text-right text-stone-600">{v}</dd>
            </div>
          ))}
        </dl>
      </div>
    </div>,
    document.body,
  );
}
