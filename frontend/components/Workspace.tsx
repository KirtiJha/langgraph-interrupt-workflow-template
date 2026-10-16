"use client";

// The mission workspace.
//
//   phone   (<768)   feed; decisions in a collapsible bottom sheet, one card at a time;
//                     board and mission panel open as sheets
//   tablet  (768+)   feed + board; mission panel opens as a sheet
//   laptop  (1024+)  mission panel | feed | board
//
// Decisions: grouped by thread, risk filters, "approve low-risk", J/K focus,
// A/E/R on the focused card, Shift+A approve all, L approve low-risk, ? help.

import { useCallback, useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { ArrowRight, CheckCheck, ChevronDown, ChevronLeft, ChevronRight, ChevronUp, Github, Hand, Keyboard, ListChecks, ShieldCheck, X } from "lucide-react";
import ApprovalCard from "./ApprovalCard";
import BoardPanel from "./BoardPanel";
import Feed from "./Feed";
import IssueDrawer from "./IssueDrawer";
import MissionPanel from "./MissionPanel";
import QuestionCard from "./QuestionCard";
import Shortcuts from "./Shortcuts";
import { Approval, Decision } from "../lib/api";
import { MissionUI } from "../lib/useMission";

type Size = "phone" | "tablet" | "laptop";
type RiskFilter = "all" | "high" | "medium" | "low";

function useSize(): Size | null {
  const [size, setSize] = useState<Size | null>(null);
  useEffect(() => {
    const md = window.matchMedia("(min-width: 768px)");
    const lg = window.matchMedia("(min-width: 1024px)");
    const update = () => setSize(lg.matches ? "laptop" : md.matches ? "tablet" : "phone");
    update();
    md.addEventListener("change", update);
    lg.addEventListener("change", update);
    return () => { md.removeEventListener("change", update); lg.removeEventListener("change", update); };
  }, []);
  return size;
}

function typing(e: KeyboardEvent) {
  const t = e.target as HTMLElement;
  return t?.tagName === "INPUT" || t?.tagName === "TEXTAREA" || t?.tagName === "SELECT" || t?.isContentEditable || e.metaKey || e.ctrlKey || e.altKey;
}

function Sheet({ title, onClose, children }: { title: string; onClose: () => void; children: React.ReactNode }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return createPortal(
    <div className="fixed inset-0 z-40 flex items-end bg-black/30" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="flex h-[85dvh] w-full flex-col rounded-t-2xl bg-paper shadow-lift animate-slide-up" role="dialog" aria-modal="true" aria-label={title}>
        <div className="flex items-center justify-between px-4 pt-3">
          <span className="text-sm font-semibold text-ink">{title}</span>
          <button type="button" onClick={onClose} className="rounded-full p-1 text-stone-500 hover:bg-stone-100" aria-label="Close"><X className="h-4 w-4" aria-hidden="true" /></button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto p-3">{children}</div>
      </div>
    </div>,
    document.body,
  );
}

export default function Workspace({ ui, onDecide, onFollowUp, onFork, onLoadHistory, onPause }: {
  ui: MissionUI; onDecide: (d: Record<string, Decision>) => void; onFollowUp: (m: string) => void;
  onFork: (cp: string) => void; onLoadHistory: () => void; onPause: () => void;
}) {
  const size = useSize();
  const [sheet, setSheet] = useState<null | "board" | "mission">(null);
  const [drawer, setDrawer] = useState<number | null>(null);
  const [help, setHelp] = useState(false);
  const [trayOpen, setTrayOpen] = useState(true);
  const [filter, setFilter] = useState<RiskFilter>("all");
  const [focus, setFocus] = useState(0);
  const [followUp, setFollowUp] = useState("");

  const approvals = ui.pending.approvals;
  const question = ui.pending.question;
  const needsYou = approvals.length > 0 || !!question;
  const busy = ui.streaming;
  const observe = ui.autonomy === "observe" || !ui.canWrite;
  const verb = observe ? "Propose" : "Approve";

  const counts = useMemo(() => {
    const c = { all: approvals.length, high: 0, medium: 0, low: 0 } as Record<RiskFilter, number>;
    for (const a of approvals) c[(a.risk?.level || "low") as RiskFilter]++;
    return c;
  }, [approvals]);
  const visible = useMemo(() => approvals.filter((a) => filter === "all" || (a.risk?.level || "low") === filter), [approvals, filter]);
  const lowRisk = approvals.filter((a) => (a.risk?.level || "low") === "low");

  // New batch of decisions → reset focus, filter and open the tray.
  const batchKey = approvals.map((a) => a.interrupt_id).join(",");
  useEffect(() => { setFocus(0); setTrayOpen(true); }, [batchKey]);
  useEffect(() => { if (filter !== "all" && counts[filter] === 0) setFilter("all"); }, [counts, filter]);
  useEffect(() => { if (focus >= visible.length) setFocus(Math.max(0, visible.length - 1)); }, [visible.length, focus]);

  const decideMany = useCallback((items: Approval[]) => {
    if (items.length) onDecide(Object.fromEntries(items.map((a) => [a.interrupt_id, { type: "approve" } as Decision])));
  }, [onDecide]);

  const scrollTo = (i: number) => {
    const a = visible[i];
    if (a && size !== "phone") document.getElementById(`approval-${a.interrupt_id}`)?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  };

  // Global shortcuts (card-level A/E/R live in ApprovalCard, on the focused card).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (typing(e) || drawer !== null) return;
      if (e.key === "?") { e.preventDefault(); setHelp((v) => !v); return; }
      if ((e.key === "b" || e.key === "B") && size !== "laptop") { e.preventDefault(); setSheet((s) => (s === "board" ? null : "board")); return; }
      if (!visible.length || busy) return;
      if (e.key === "j") { e.preventDefault(); setFocus((f) => { const n = Math.min(visible.length - 1, f + 1); scrollTo(n); return n; }); }
      else if (e.key === "k") { e.preventDefault(); setFocus((f) => { const n = Math.max(0, f - 1); scrollTo(n); return n; }); }
      else if (e.key === "A" && e.shiftKey) { e.preventDefault(); decideMany(visible); }
      else if (e.key === "l" || e.key === "L") { e.preventDefault(); decideMany(lowRisk); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visible, lowRisk, busy, drawer, size, decideMany]);

  const groups = useMemo(() => {
    const byKey = new Map<string, { key: string; title: string; items: Approval[] }>();
    for (const a of visible) {
      const n = a.args?.number;
      const key = n != null ? `#${n}` : a.name === "create_issue" ? "new" : "other";
      const title = n != null ? (a.risk?.preview?.title || "") : a.name === "create_issue" ? "New issue" : "";
      if (!byKey.has(key)) byKey.set(key, { key, title, items: [] });
      byKey.get(key)!.items.push(a);
    }
    return [...byKey.values()];
  }, [visible]);

  const header = (compact: boolean) => needsYou && (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className={`${compact ? "sr-only" : "flex"} items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-ember-700`}>
          <Hand className="h-3.5 w-3.5" aria-hidden="true" />
          {question ? "The steward needs an answer" : `${approvals.length} action${approvals.length === 1 ? "" : "s"} ${observe ? "to propose" : approvals.length === 1 ? "needs your approval" : "need your approval"}`}
        </h2>
        {approvals.length > 1 && (
          <div className="flex items-center gap-1">
            {lowRisk.length > 0 && lowRisk.length < approvals.length && (
              <button type="button" className="btn-ghost h-8 px-2.5 text-xs" disabled={busy} onClick={() => decideMany(lowRisk)} title="Shortcut: L">
                <ShieldCheck className="h-3.5 w-3.5 text-emerald-600" aria-hidden="true" /> {verb} low-risk ({lowRisk.length})
              </button>
            )}
            <button type="button" className="btn-ghost h-8 px-2.5 text-xs" disabled={busy} onClick={() => decideMany(visible)} title="Shortcut: Shift+A">
              <CheckCheck className="h-3.5 w-3.5" aria-hidden="true" /> {verb} {filter === "all" ? "all" : `all ${filter}`}
            </button>
          </div>
        )}
      </div>
      {approvals.length > 2 && (counts.high > 0 || counts.medium > 0) && counts.low + counts.medium + counts.high > Math.max(counts.low, counts.medium, counts.high) && (
        <div role="radiogroup" aria-label="Filter by risk" className="flex flex-wrap gap-1.5">
          {(["all", "high", "medium", "low"] as RiskFilter[]).filter((f) => f === "all" || counts[f] > 0).map((f) => (
            <button key={f} role="radio" aria-checked={filter === f} type="button" onClick={() => setFilter(f)}
                    className={`chip ${filter === f ? "border-ink bg-ink text-paper" : f === "high" ? "border-rose-200 bg-rose-50 text-rose-700" : f === "medium" ? "border-amber-200 bg-amber-50 text-amber-800" : f === "low" ? "border-emerald-200 bg-emerald-50 text-emerald-700" : "border-stone-200 bg-white text-stone-600"}`}>
              {f === "all" ? "All" : `${f[0].toUpperCase()}${f.slice(1)} risk`} · {counts[f]}
            </button>
          ))}
        </div>
      )}
    </div>
  );

  // Laptop / tablet: all cards, grouped by thread.
  const list = needsYou && (
    <section aria-label="Decisions" className="space-y-3">
      {header(false)}
      {question && <QuestionCard question={question} busy={busy} onAnswer={(a) => onDecide({ [question.interrupt_id]: a })} />}
      {groups.map((g) => (
        <div key={g.key} className="space-y-2">
          {groups.length > 1 && (
            <div className="flex items-center gap-2 pt-1">
              <button type="button" onClick={() => g.key.startsWith("#") && setDrawer(Number(g.key.slice(1)))} className="font-mono text-xs text-stone-500 hover:text-ember-700">{g.key}</button>
              <span className="min-w-0 flex-1 truncate text-sm font-medium text-ink">{g.title}</span>
              {g.items.length > 1 && <button type="button" className="btn-ghost h-7 px-2 text-[11px]" disabled={busy} onClick={() => decideMany(g.items)}>{verb} {g.items.length}</button>}
            </div>
          )}
          {g.items.map((a) => {
            const idx = visible.indexOf(a);
            return (
              <ApprovalCard key={a.interrupt_id} approval={a} index={idx} busy={busy} hotkeys={idx === focus && drawer === null && !help}
                            labels={ui.board?.labels} onFocus={() => setFocus(idx)} onDecide={(d) => onDecide({ [a.interrupt_id]: d })} />
            );
          })}
        </div>
      ))}
      {approvals.length > 0 && (
        <p className="hidden items-center gap-1.5 text-[11px] text-stone-500 md:flex">
          <Keyboard className="h-3.5 w-3.5" aria-hidden="true" /> <kbd className="kbd">J</kbd><kbd className="kbd">K</kbd> move · <kbd className="kbd">A</kbd> approve · <kbd className="kbd">E</kbd> edit · <kbd className="kbd">R</kbd> reject ·
          <button type="button" onClick={() => setHelp(true)} className="underline-offset-2 hover:underline">all shortcuts</button>
        </p>
      )}
    </section>
  );

  // Phone: a collapsible sheet with one card at a time.
  const current = visible[Math.min(focus, Math.max(0, visible.length - 1))];
  const phoneTray = needsYou && (
    <div className="fixed inset-x-0 bottom-0 z-30 flex max-h-[78dvh] flex-col rounded-t-2xl border-t border-stone-200 bg-paper shadow-lift animate-slide-up" role="region" aria-label="Decisions">
      <button type="button" onClick={() => setTrayOpen((v) => !v)} aria-expanded={trayOpen}
              className="flex w-full items-center gap-2 px-4 pb-2 pt-2.5 text-left">
        <span className="absolute left-1/2 top-1.5 h-1 w-10 -translate-x-1/2 rounded-full bg-stone-300" aria-hidden="true" />
        <Hand className="h-4 w-4 shrink-0 text-ember-600" aria-hidden="true" />
        <span className="min-w-0 flex-1 truncate text-sm font-semibold text-ink">
          {question ? "The steward needs an answer" : `${approvals.length} action${approvals.length === 1 ? "" : "s"} waiting`}
          {!question && visible.length > 1 && <span className="ml-1.5 font-normal text-stone-500">· {Math.min(focus + 1, visible.length)} of {visible.length}</span>}
        </span>
        {trayOpen ? <ChevronDown className="h-4 w-4 text-stone-500" aria-hidden="true" /> : <ChevronUp className="h-4 w-4 text-stone-500" aria-hidden="true" />}
      </button>
      {trayOpen && (
        <div className="min-h-0 flex-1 space-y-3 overflow-y-auto px-3 pb-[max(0.75rem,env(safe-area-inset-bottom))]">
          {header(true)}
          {question && <QuestionCard question={question} busy={busy} onAnswer={(a) => onDecide({ [question.interrupt_id]: a })} />}
          {current && (
            <>
              {current.args?.number != null && (
                <button type="button" onClick={() => setDrawer(current.args.number)} className="flex w-full items-center gap-2 text-left">
                  <span className="font-mono text-xs text-stone-500">#{current.args.number}</span>
                  <span className="min-w-0 flex-1 truncate text-sm font-medium text-ink">{current.risk?.preview?.title}</span>
                  <span className="text-[11px] text-ember-700">thread ›</span>
                </button>
              )}
              <ApprovalCard key={current.interrupt_id} approval={current} index={focus} busy={busy} hotkeys labels={ui.board?.labels}
                            onDecide={(d) => onDecide({ [current.interrupt_id]: d })} />
              {visible.length > 1 && (
                <div className="flex items-center justify-between">
                  <button type="button" className="btn-outline h-9 px-3 text-xs" disabled={focus === 0} onClick={() => setFocus((f) => Math.max(0, f - 1))}>
                    <ChevronLeft className="h-4 w-4" aria-hidden="true" /> Previous
                  </button>
                  <div className="flex gap-1" aria-hidden="true">
                    {visible.slice(0, 12).map((a, i) => <span key={a.interrupt_id} className={`h-1.5 w-1.5 rounded-full ${i === focus ? "bg-ember-600" : "bg-stone-300"}`} />)}
                  </div>
                  <button type="button" className="btn-outline h-9 px-3 text-xs" disabled={focus >= visible.length - 1} onClick={() => setFocus((f) => Math.min(visible.length - 1, f + 1))}>
                    Next <ChevronRight className="h-4 w-4" aria-hidden="true" />
                  </button>
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );

  const composer = ui.status === "completed" && !busy && (
    <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); if (followUp.trim()) { onFollowUp(followUp.trim()); setFollowUp(""); } }}>
      <input className="field h-11" value={followUp} onChange={(e) => setFollowUp(e.target.value)} placeholder="Anything else on this repo? Same thread, same board." aria-label="Follow-up" />
      <button type="submit" className="btn-primary h-11 shrink-0" disabled={!followUp.trim()} aria-label="Send follow-up"><ArrowRight className="h-4 w-4" aria-hidden="true" /></button>
    </form>
  );

  return (
    <div className="mx-auto grid w-full max-w-[1600px] flex-1 grid-cols-1 gap-4 px-3 pb-3 pt-3 md:min-h-0 md:grid-cols-[minmax(0,1fr)_320px] lg:grid-cols-[272px_minmax(0,1fr)_360px] lg:px-4 xl:grid-cols-[300px_minmax(0,1fr)_400px]">
      {/* Summary bar: phones and tablets */}
      <div className="flex min-w-0 items-center gap-2 md:col-span-2 lg:hidden">
        <button type="button" onClick={() => setSheet("mission")} className="min-w-0 flex-1 rounded-xl border border-stone-200 bg-white px-3 py-2 text-left">
          <div className="truncate text-sm font-semibold text-ink">{ui.title || ui.goal}</div>
          <div className="truncate text-[11px] text-stone-500">{ui.repo} · {ui.decisionsMade} decision{ui.decisionsMade === 1 ? "" : "s"}{ui.branches > 1 ? ` · branch ${ui.branches}` : ""} · <span className="text-ember-700">actions & rewind ›</span></div>
        </button>
        {size === "phone" && (
          <button type="button" onClick={() => setSheet("board")} className="btn-outline relative h-11 shrink-0 px-3" aria-label="Open the repository board">
            <Github className="h-4 w-4" aria-hidden="true" /> Board
            {needsYou && <span className="absolute -right-1 -top-1 h-2.5 w-2.5 rounded-full bg-ember-500" />}
          </button>
        )}
      </div>

      <div className="hidden min-h-0 min-w-0 lg:block"><MissionPanel ui={ui} onFork={onFork} onLoadHistory={onLoadHistory} onPause={onPause} /></div>

      <main className="flex min-h-0 min-w-0 flex-col md:overflow-hidden">
        <div className={`min-h-0 min-w-0 flex-1 overflow-y-auto pr-1 scrollbar-none ${size === "phone" && needsYou ? (trayOpen ? "pb-[60dvh]" : "pb-20") : "pb-4"}`}>
          <Feed feed={ui.feed} streaming={ui.streaming} board={ui.board} title={ui.title || ui.goal} />
          <div className="mt-4 space-y-3">{size !== "phone" && list}{composer}</div>
        </div>
      </main>

      <div className="hidden min-h-0 min-w-0 md:block">{ui.board && <BoardPanel board={ui.board} pending={approvals} onOpen={setDrawer} />}</div>

      {size === "phone" && phoneTray}

      {sheet === "board" && ui.board && (
        <Sheet title="Repository board" onClose={() => setSheet(null)}>
          <BoardPanel board={ui.board} pending={approvals} compact onOpen={(n) => { setSheet(null); setDrawer(n); }} />
        </Sheet>
      )}
      {sheet === "mission" && (
        <Sheet title="Mission" onClose={() => setSheet(null)}>
          <MissionPanel ui={ui} onFork={(cp) => { setSheet(null); onFork(cp); }} onLoadHistory={onLoadHistory} onPause={onPause} />
        </Sheet>
      )}
      {drawer !== null && ui.board && (
        <IssueDrawer board={ui.board} number={drawer} pending={approvals} busy={busy} onDecide={onDecide} onClose={() => setDrawer(null)} />
      )}
      {help && <Shortcuts onClose={() => setHelp(false)} />}
      <button type="button" onClick={() => setHelp(true)} className="sr-only focus:not-sr-only" aria-label="Keyboard shortcuts"><ListChecks className="h-4 w-4" /></button>
    </div>
  );
}
