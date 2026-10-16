"use client";

// The mission workspace: mission panel | feed + decision tray | the repo board.
// Decisions are grouped by issue so a triage of forty items reads as a list.

import { useEffect, useMemo, useState } from "react";
import { ArrowRight, CheckCheck, Github, Hand, X } from "lucide-react";
import ApprovalCard from "./ApprovalCard";
import BoardPanel from "./BoardPanel";
import Feed from "./Feed";
import MissionPanel from "./MissionPanel";
import QuestionCard from "./QuestionCard";
import { Approval, Decision } from "../lib/api";
import { MissionUI } from "../lib/useMission";

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
  const [boardOpen, setBoardOpen] = useState(false);
  const [followUp, setFollowUp] = useState("");
  const desktop = useDesktop();
  const approvals = ui.pending.approvals;
  const question = ui.pending.question;
  const needsYou = approvals.length > 0 || !!question;
  const busy = ui.streaming;
  const observe = ui.autonomy === "observe" || !ui.canWrite;

  const groups = useMemo(() => {
    const byNumber = new Map<string, { key: string; title: string; items: Approval[] }>();
    for (const a of approvals) {
      const n = a.args?.number;
      const key = n != null ? `#${n}` : a.name === "create_issue" ? "new" : "other";
      const title = n != null ? (a.risk?.preview?.title || "") : a.name === "create_issue" ? "New issue" : "";
      if (!byNumber.has(key)) byNumber.set(key, { key, title, items: [] });
      byNumber.get(key)!.items.push(a);
    }
    return [...byNumber.values()];
  }, [approvals]);

  const approveGroup = (items: Approval[]) => onDecide(Object.fromEntries(items.map((a) => [a.interrupt_id, { type: "approve" } as Decision])));

  const tray = needsYou && (
    <section aria-label="Decisions" className="space-y-3">
      <div className="flex items-center justify-between gap-2">
        <h2 className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-ember-700">
          <Hand className="h-3.5 w-3.5" aria-hidden="true" />
          {question ? "The steward needs an answer" : `${approvals.length} action${approvals.length === 1 ? "" : "s"} ${observe ? "to propose" : "need" + (approvals.length === 1 ? "s" : "") + " your approval"}${groups.length > 1 ? ` · ${groups.length} threads` : ""}`}
        </h2>
        {approvals.length > 1 && (
          <button type="button" className="btn-ghost h-8 px-2.5 text-xs" disabled={busy} onClick={() => approveGroup(approvals)}>
            <CheckCheck className="h-3.5 w-3.5" aria-hidden="true" /> {observe ? "Propose all" : "Approve all"}
          </button>
        )}
      </div>
      {question && <QuestionCard question={question} busy={busy} onAnswer={(a) => onDecide({ [question.interrupt_id]: a })} />}
      {groups.map((g, gi) => (
        <div key={g.key} className="space-y-2">
          {groups.length > 1 && (
            <div className="flex items-center gap-2 pt-1">
              <span className="font-mono text-xs text-stone-500">{g.key}</span>
              <span className="min-w-0 flex-1 truncate text-sm font-medium text-ink">{g.title}</span>
              {g.items.length > 1 && <button type="button" className="btn-ghost h-7 px-2 text-[11px]" disabled={busy} onClick={() => approveGroup(g.items)}>Approve {g.items.length}</button>}
            </div>
          )}
          {g.items.map((a, i) => (
            <ApprovalCard key={a.interrupt_id} approval={a} index={i} busy={busy} hotkeys={gi === 0 && i === 0} labels={ui.board?.labels}
                          onDecide={(d) => onDecide({ [a.interrupt_id]: d })} />
          ))}
        </div>
      ))}
    </section>
  );

  const composer = ui.status === "completed" && !busy && (
    <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); if (followUp.trim()) { onFollowUp(followUp.trim()); setFollowUp(""); } }}>
      <input className="field h-11" value={followUp} onChange={(e) => setFollowUp(e.target.value)} placeholder="Anything else on this repo? Same thread, same board." aria-label="Follow-up" />
      <button type="submit" className="btn-primary h-11 shrink-0" disabled={!followUp.trim()} aria-label="Send follow-up"><ArrowRight className="h-4 w-4" aria-hidden="true" /></button>
    </form>
  );

  return (
    <div className="mx-auto grid w-full max-w-[1480px] flex-1 gap-4 px-3 pb-3 pt-3 lg:min-h-0 lg:grid-cols-[300px_minmax(0,1fr)_380px] lg:px-4">
      <div className="flex items-center gap-2 lg:hidden">
        <div className="min-w-0 flex-1 rounded-xl border border-stone-200 bg-white px-3 py-2">
          <div className="truncate text-sm font-semibold text-ink">{ui.title || ui.goal}</div>
          <div className="truncate text-[11px] text-stone-500">{ui.repo} · {ui.decisionsMade} decision{ui.decisionsMade === 1 ? "" : "s"}{ui.branches > 1 ? ` · branch ${ui.branches}` : ""}</div>
        </div>
        <button type="button" onClick={() => setBoardOpen(true)} className="btn-outline relative h-11 px-3" aria-label="Open the repository board">
          <Github className="h-4 w-4" aria-hidden="true" /> Board
          {needsYou && <span className="absolute -right-1 -top-1 h-2.5 w-2.5 rounded-full bg-ember-500" />}
        </button>
      </div>

      <div className="hidden min-h-0 lg:block"><MissionPanel ui={ui} onFork={onFork} onLoadHistory={onLoadHistory} onPause={onPause} /></div>

      <main className="flex min-h-0 flex-col lg:overflow-hidden">
        <div className="min-h-0 flex-1 overflow-y-auto pb-4 pr-1 scrollbar-none">
          <Feed feed={ui.feed} streaming={ui.streaming} board={ui.board} title={ui.title || ui.goal} />
          <div className="mt-4">{desktop && tray}{composer}</div>
        </div>
      </main>

      <div className="hidden min-h-0 lg:block">{ui.board && <BoardPanel board={ui.board} pending={approvals} />}</div>

      {needsYou && desktop === false && (
        <div className="fixed inset-x-0 bottom-0 z-30 max-h-[70dvh] overflow-y-auto rounded-t-2xl border-t border-stone-200 bg-paper p-3 shadow-lift animate-slide-up" role="region" aria-label="Decisions">{tray}</div>
      )}

      {boardOpen && (
        <div className="fixed inset-0 z-40 flex items-end bg-ink/30 lg:hidden" onMouseDown={(e) => e.target === e.currentTarget && setBoardOpen(false)}>
          <div className="flex h-[80dvh] w-full flex-col rounded-t-2xl bg-white shadow-lift animate-slide-up" role="dialog" aria-modal="true" aria-label="Repository board">
            <div className="flex items-center justify-between px-4 pt-3">
              <span className="text-sm font-semibold text-ink">Repository board</span>
              <button type="button" onClick={() => setBoardOpen(false)} className="rounded-full p-1 text-stone-500 hover:bg-stone-100" aria-label="Close"><X className="h-4 w-4" aria-hidden="true" /></button>
            </div>
            <div className="min-h-0 flex-1">{ui.board && <BoardPanel board={ui.board} pending={approvals} compact />}</div>
          </div>
        </div>
      )}
    </div>
  );
}
