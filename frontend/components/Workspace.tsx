"use client";

// The mission workspace: mission panel | feed + decision tray | your world.
// On phones the panels collapse into a summary bar and a bottom sheet.

import { useEffect, useState } from "react";
import { ArrowRight, CheckCheck, Globe, Hand, X } from "lucide-react";
import ApprovalCard from "./ApprovalCard";
import Feed from "./Feed";
import MissionPanel from "./MissionPanel";
import QuestionCard from "./QuestionCard";
import WorldPanel from "./WorldPanel";
import { Decision, money } from "../lib/api";
import { MissionUI } from "../lib/useMission";

/** Desktop vs phone layout, so the decision tray (and its hotkeys) renders exactly once. */
function useDesktop() {
  const [desktop, setDesktop] = useState<boolean | null>(null);
  useEffect(() => {
    const mq = window.matchMedia("(min-width: 1024px)");
    const update = () => setDesktop(mq.matches);
    update();
    mq.addEventListener("change", update);
    return () => mq.removeEventListener("change", update);
  }, []);
  return desktop;
}

export default function Workspace({ ui, onDecide, onFollowUp, onFork, onLoadHistory, onPause }: {
  ui: MissionUI; onDecide: (d: Record<string, Decision>) => void; onFollowUp: (m: string) => void;
  onFork: (cp: string) => void; onLoadHistory: () => void; onPause: () => void;
}) {
  const [worldOpen, setWorldOpen] = useState(false);
  const desktop = useDesktop();
  const [followUp, setFollowUp] = useState("");
  const approvals = ui.pending.approvals;
  const question = ui.pending.question;
  const needsYou = approvals.length > 0 || !!question;
  const busy = ui.streaming;

  const tray = needsYou && (
    <section aria-label="Decisions" className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-ember-700">
          <Hand className="h-3.5 w-3.5" aria-hidden="true" />
          {question ? "The agent needs an answer" : `${approvals.length} action${approvals.length === 1 ? "" : "s"} need${approvals.length === 1 ? "s" : ""} your approval`}
        </h2>
        {approvals.length > 1 && (
          <button type="button" className="btn-ghost h-8 px-2.5 text-xs" disabled={busy}
                  onClick={() => onDecide(Object.fromEntries(approvals.map((a) => [a.interrupt_id, { type: "approve" } as Decision])))}>
            <CheckCheck className="h-3.5 w-3.5" aria-hidden="true" /> Approve all
          </button>
        )}
      </div>
      {question && <QuestionCard question={question} busy={busy} onAnswer={(a) => onDecide({ [question.interrupt_id]: a })} />}
      {approvals.map((a, i) => (
        <ApprovalCard key={a.interrupt_id} approval={a} index={i} busy={busy} hotkeys={i === 0}
                      onDecide={(d) => onDecide({ [a.interrupt_id]: d })} />
      ))}
    </section>
  );

  const composer = ui.status === "completed" && !busy && (
    <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); if (followUp.trim()) { onFollowUp(followUp.trim()); setFollowUp(""); } }}>
      <input className="field h-11" value={followUp} onChange={(e) => setFollowUp(e.target.value)} placeholder="Anything else? e.g. “Also invite Jordan” — same world, same thread" aria-label="Follow-up" />
      <button type="submit" className="btn-primary h-11 shrink-0" disabled={!followUp.trim()} aria-label="Send follow-up"><ArrowRight className="h-4 w-4" aria-hidden="true" /></button>
    </form>
  );

  return (
    <div className="mx-auto grid w-full max-w-[1480px] flex-1 gap-4 px-3 pb-3 pt-3 lg:min-h-0 lg:grid-cols-[300px_minmax(0,1fr)_360px] lg:px-4">
      {/* Mobile summary bar */}
      <div className="flex items-center gap-2 lg:hidden">
        <div className="min-w-0 flex-1 rounded-xl border border-stone-200 bg-white px-3 py-2">
          <div className="truncate text-sm font-semibold text-ink">{ui.title || ui.goal}</div>
          <div className="tabular text-[11px] text-stone-500">{ui.world ? money(ui.world.wallet.balance, 2) : ""} · {ui.decisionsMade} decision{ui.decisionsMade === 1 ? "" : "s"}{ui.branches > 1 ? ` · branch ${ui.branches}` : ""}</div>
        </div>
        <button type="button" onClick={() => setWorldOpen(true)} className="btn-outline relative h-11 px-3" aria-label="Open your world">
          <Globe className="h-4 w-4" aria-hidden="true" /> World
          {needsYou && <span className="absolute -right-1 -top-1 h-2.5 w-2.5 rounded-full bg-ember-500" />}
        </button>
      </div>

      <div className="hidden min-h-0 lg:block"><MissionPanel ui={ui} onFork={onFork} onLoadHistory={onLoadHistory} onPause={onPause} /></div>

      <main className="flex min-h-0 flex-col lg:overflow-hidden">
        <div className="min-h-0 flex-1 overflow-y-auto pb-4 pr-1 scrollbar-none">
          <Feed feed={ui.feed} streaming={ui.streaming} />
          {/* Desktop: decisions sit right under the feed, where your eye already is. */}
          <div className="mt-4">{desktop && tray}{composer}</div>
        </div>
      </main>

      <div className="hidden min-h-0 lg:block">{ui.world && <WorldPanel world={ui.world} pending={approvals} startBalance={ui.startBalance} />}</div>

      {/* Mobile: decisions slide up from the bottom. */}
      {needsYou && desktop === false && (
        <div className="fixed inset-x-0 bottom-0 z-30 max-h-[70dvh] overflow-y-auto rounded-t-2xl border-t border-stone-200 bg-paper p-3 shadow-lift animate-slide-up lg:hidden" role="region" aria-label="Decisions">
          {tray}
        </div>
      )}

      {worldOpen && (
        <div className="fixed inset-0 z-40 flex items-end bg-ink/30 lg:hidden" onMouseDown={(e) => e.target === e.currentTarget && setWorldOpen(false)}>
          <div className="flex h-[80dvh] w-full flex-col rounded-t-2xl bg-white shadow-lift animate-slide-up" role="dialog" aria-modal="true" aria-label="Your world">
            <div className="flex items-center justify-between px-4 pt-3">
              <span className="text-sm font-semibold text-ink">Your world</span>
              <button type="button" onClick={() => setWorldOpen(false)} className="rounded-full p-1 text-stone-500 hover:bg-stone-100" aria-label="Close"><X className="h-4 w-4" aria-hidden="true" /></button>
            </div>
            <div className="min-h-0 flex-1">{ui.world && <WorldPanel world={ui.world} pending={approvals} startBalance={ui.startBalance} compact />}</div>
          </div>
        </div>
      )}
    </div>
  );
}
