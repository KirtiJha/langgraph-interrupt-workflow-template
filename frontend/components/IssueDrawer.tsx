"use client";

// Click any issue or PR on the board: its body, labels, thread (including what
// the steward posted or proposed) and the actions pending on it, decidable here.

import { useEffect } from "react";
import { createPortal } from "react-dom";
import ReactMarkdown from "react-markdown";
import { ExternalLink, GitPullRequest, CircleDot, X } from "lucide-react";
import ApprovalCard, { LabelChip } from "./ApprovalCard";
import { Approval, Board, Decision, ageLabel } from "../lib/api";

export default function IssueDrawer({ board, number, pending, busy, onDecide, onClose }: {
  board: Board; number: number; pending: Approval[]; busy: boolean;
  onDecide: (d: Record<string, Decision>) => void; onClose: () => void;
}) {
  const item = board.issues.concat(board.pulls).find((i) => i.number === number);
  const mine = pending.filter((a) => a.args?.number === number);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  if (!item) return null;
  const Icon = item.is_pr ? GitPullRequest : CircleDot;

  return createPortal(
    <div className="fixed inset-0 z-50 flex justify-end bg-black/30" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <aside role="dialog" aria-modal="true" aria-label={`#${item.number} ${item.title}`}
             className="flex h-full w-full max-w-xl flex-col bg-paper shadow-lift animate-slide-in">
        <header className="flex items-start gap-3 border-b border-stone-200 px-5 py-4">
          <Icon className={`mt-1 h-4 w-4 shrink-0 ${item.state === "open" ? "text-emerald-600" : "text-violet-600"}`} aria-hidden="true" />
          <div className="min-w-0 flex-1">
            <h2 className="text-base font-semibold leading-snug text-ink"><span className="font-mono text-stone-500">#{item.number}</span> {item.title}</h2>
            <p className="mt-0.5 text-xs text-stone-500">
              {item.author}{item.author_association === "FIRST_TIME_CONTRIBUTOR" ? " · first-time contributor" : ""} · opened {ageLabel(item.created_at)}
              {item.comments ? ` · ${item.comments} comment${item.comments === 1 ? "" : "s"}` : ""} · {item.state}
            </p>
            <div className="mt-2 flex flex-wrap gap-1">{item.labels.map((l) => <LabelChip key={l} name={l} labels={board.labels} />)}</div>
          </div>
          {item.url && <a href={item.url} target="_blank" rel="noreferrer" className="rounded-full p-1.5 text-stone-500 hover:bg-stone-100 hover:text-ink" aria-label="Open on GitHub"><ExternalLink className="h-4 w-4" aria-hidden="true" /></a>}
          <button type="button" onClick={onClose} className="rounded-full p-1.5 text-stone-500 hover:bg-stone-100 hover:text-ink" aria-label="Close"><X className="h-4 w-4" aria-hidden="true" /></button>
        </header>

        <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-5 py-4">
          {mine.length > 0 && (
            <section className="space-y-3" aria-label="Pending on this thread">
              <h3 className="text-[11px] font-semibold uppercase tracking-wide text-ember-700">Waiting on you · {mine.length}</h3>
              {mine.map((a, i) => (
                <ApprovalCard key={a.interrupt_id} approval={a} index={i} busy={busy} hotkeys={i === 0} labels={board.labels}
                              onDecide={(d) => onDecide({ [a.interrupt_id]: d })} />
              ))}
            </section>
          )}
          <section>
            <h3 className="text-[11px] font-semibold uppercase tracking-wide text-stone-500">Description</h3>
            <div className="prose-steward mt-1 break-words text-[14px] leading-relaxed text-stone-800">
              {item.body ? <ReactMarkdown>{item.body}</ReactMarkdown> : <p className="text-stone-400">No description.</p>}
            </div>
          </section>
          {item.thread?.length > 0 && (
            <section>
              <h3 className="text-[11px] font-semibold uppercase tracking-wide text-stone-500">Thread</h3>
              <ol className="mt-2 space-y-2">
                {item.thread.map((t, i) => (
                  <li key={i} className={`rounded-xl border p-3 ${t.author === "repo-steward" ? (t.proposed ? "border-violet-200 bg-violet-50" : "border-emerald-200 bg-emerald-50") : "border-stone-200 bg-white"}`}>
                    <div className="text-[11px] text-stone-500"><strong className="text-stone-700">{t.author}</strong>{t.created_at ? ` · ${ageLabel(t.created_at)}` : ""}{t.author === "repo-steward" ? (t.proposed ? " · proposed" : " · posted by the steward") : ""}</div>
                    <div className="prose-steward mt-1 break-words text-[13px] text-stone-800"><ReactMarkdown>{t.body}</ReactMarkdown></div>
                  </li>
                ))}
              </ol>
            </section>
          )}
          {board.mode === "live" && item.comments > 0 && !item.thread?.length && (
            <p className="text-xs text-stone-500">{item.comments} comment{item.comments === 1 ? "" : "s"} on GitHub — <a className="text-ember-700 hover:underline" href={item.url} target="_blank" rel="noreferrer">read the thread ↗</a></p>
          )}
        </div>
      </aside>
    </div>,
    document.body,
  );
}
