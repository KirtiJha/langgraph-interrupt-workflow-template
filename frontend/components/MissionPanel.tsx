"use client";

// Left column: the mission, meters, a live checklist of actions, and the
// time-travel scrubber (decision points you can branch from).

import { useEffect, useState } from "react";
import { Check, GitBranch, Hand, History, LoaderCircle, MessageSquare, Pencil, Rewind, TriangleAlert, X } from "lucide-react";
import { DecisionPoint, describeCall } from "../lib/api";
import { Entry, MissionUI } from "../lib/useMission";

const AUTONOMY: Record<string, { label: string; blurb: string }> = {
  observe: { label: "Observe", blurb: "proposals only" },
  careful: { label: "Careful", blurb: "asks before every action" },
  balanced: { label: "Balanced", blurb: "asks when it matters" },
  autopilot: { label: "Autopilot", blurb: "asks only for high risk" },
};
const READS = new Set(["list_issues", "list_pulls", "read_issue", "find_similar", "read_file", "read_pull", "release_context", "remember"]);

function checklist(feed: Entry[]) {
  const items: { id: string; text: string; status: string }[] = [];
  for (const e of feed) {
    if (e.kind !== "tools") continue;
    for (const c of e.calls) if (!READS.has(c.name)) items.push({ id: c.id, text: describeCall(c.name, c.args), status: c.status });
  }
  return items;
}

export default function MissionPanel({ ui, onFork, onLoadHistory, onPause }: {
  ui: MissionUI; onFork: (cp: string) => void; onLoadHistory: () => void; onPause: () => void;
}) {
  const [showHistory, setShowHistory] = useState(false);
  const items = checklist(ui.feed);
  const done = items.filter((i) => i.status === "ok" || i.status === "edited").length;
  const declined = items.filter((i) => i.status === "rejected").length;
  const proposed = ui.board?.ledger.filter((l) => l.proposed).length || 0;
  const progress = ui.status === "completed" ? 100 : items.length ? Math.round(((done + declined) / items.length) * 85) : ui.streaming ? 10 : 0;

  useEffect(() => { if (showHistory) onLoadHistory(); }, [showHistory, ui.decisionsMade, onLoadHistory]);

  return (
    <aside className="flex h-full flex-col gap-3">
      <div className="card p-4">
        <div className="text-[11px] font-semibold uppercase tracking-wide text-stone-500">Mission · {ui.repo}</div>
        <h2 className="mt-1 text-base font-semibold leading-snug text-ink">{ui.title || ui.goal}</h2>
        <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-stone-100">
          <div className={`h-full rounded-full transition-all duration-700 ${ui.status === "completed" ? "bg-emerald-500" : "bg-ember-500"}`} style={{ width: `${progress}%` }} />
        </div>
        <div className="mt-2 flex items-center gap-2 text-xs text-stone-600">
          {ui.status === "completed" ? <><Check className="h-3.5 w-3.5 text-emerald-600" aria-hidden="true" /> Complete</>
            : ui.status === "awaiting_approval" || ui.status === "awaiting_answer" ? <><Hand className="h-3.5 w-3.5 text-ember-600" aria-hidden="true" /> Waiting on you</>
            : ui.status === "paused" ? <>Paused — progress saved</>
            : ui.streaming ? <><LoaderCircle className="h-3.5 w-3.5 animate-spin text-ember-500" aria-hidden="true" /> Working</> : <>Idle</>}
          {ui.streaming && <button type="button" onClick={onPause} className="ml-auto text-[11px] font-medium text-stone-500 underline-offset-2 hover:text-ink hover:underline">Pause</button>}
        </div>
        <dl className="mt-3 grid grid-cols-3 gap-2 text-center">
          <div className="rounded-xl bg-stone-50 p-2"><dt className="text-[10px] uppercase tracking-wide text-stone-500">{proposed && !done ? "Proposed" : "Done"}</dt><dd className="tabular mt-0.5 text-sm font-semibold text-emerald-700">{proposed && !done ? proposed : done}</dd></div>
          <div className="rounded-xl bg-stone-50 p-2"><dt className="text-[10px] uppercase tracking-wide text-stone-500">Declined</dt><dd className="tabular mt-0.5 text-sm font-semibold text-rose-700">{declined}</dd></div>
          <div className="rounded-xl bg-stone-50 p-2"><dt className="text-[10px] uppercase tracking-wide text-stone-500">Decisions</dt><dd className="tabular mt-0.5 text-sm font-semibold text-ink">{ui.decisionsMade}</dd></div>
        </dl>
        <div className="mt-3 flex items-center justify-between gap-2 text-[11px] text-stone-500">
          <span><span className="font-medium text-stone-700">{AUTONOMY[ui.autonomy]?.label}</span> · {AUTONOMY[ui.autonomy]?.blurb}</span>
          {ui.branches > 1 && <span className="chip border-ember-200 bg-ember-50 text-ember-700"><GitBranch className="h-3 w-3" aria-hidden="true" />branch {ui.branches}</span>}
        </div>
        {ui.mode === "live" && ui.canWrite && ui.autonomy !== "observe" && (
          <p className="mt-2 flex items-start gap-1 text-[11px] text-ember-800"><TriangleAlert className="mt-px h-3 w-3 shrink-0" aria-hidden="true" />Approved actions happen on the real repository.</p>
        )}
      </div>

      <div className="card min-h-0 flex-1 overflow-hidden p-4">
        <div className="flex items-center justify-between">
          <div className="text-[11px] font-semibold uppercase tracking-wide text-stone-500">Actions</div>
          <button type="button" onClick={() => setShowHistory((v) => !v)} disabled={!ui.threadId || ui.decisionsMade === 0}
                  className="flex items-center gap-1 text-[11px] font-medium text-stone-600 hover:text-ink disabled:opacity-40" aria-pressed={showHistory}>
            <History className="h-3.5 w-3.5" aria-hidden="true" /> {showHistory ? "Hide" : "Rewind"}
          </button>
        </div>
        {!showHistory ? (
          <ol className="mt-2 space-y-1.5 overflow-y-auto text-[13px]">
            {items.length === 0 && <li className="text-stone-400">Reading the repository…</li>}
            {items.map((i) => (
              <li key={i.id} className="flex items-start gap-2">
                <span className="mt-0.5 shrink-0">
                  {i.status === "ok" && <Check className="h-3.5 w-3.5 text-emerald-600" aria-hidden="true" />}
                  {i.status === "edited" && <Pencil className="h-3.5 w-3.5 text-sky-600" aria-hidden="true" />}
                  {i.status === "rejected" && <X className="h-3.5 w-3.5 text-rose-500" aria-hidden="true" />}
                  {i.status === "error" && <TriangleAlert className="h-3.5 w-3.5 text-rose-600" aria-hidden="true" />}
                  {i.status === "responded" && <MessageSquare className="h-3.5 w-3.5 text-violet-600" aria-hidden="true" />}
                  {i.status === "pending" && <Hand className="h-3.5 w-3.5 text-ember-600" aria-hidden="true" />}
                  {i.status === "running" && <LoaderCircle className="h-3.5 w-3.5 animate-spin text-stone-400" aria-hidden="true" />}
                </span>
                <span className={i.status === "rejected" ? "text-stone-400 line-through" : "text-stone-800"}>{i.text}</span>
              </li>
            ))}
          </ol>
        ) : (
          <div className="mt-2 overflow-y-auto text-[13px]">
            <p className="text-xs text-stone-500">Every point where the mission waited on you. Branch from one to decide differently — the board rewinds with it{ui.mode === "live" ? "; anything already posted on GitHub stays" : ""}.</p>
            <ol className="mt-2 space-y-1.5">
              {ui.history.map((p: DecisionPoint, i) => (
                <li key={p.checkpoint_id} className="rounded-xl border border-stone-200 bg-white p-2.5">
                  <div className="flex items-center justify-between text-[11px] text-stone-500"><span>Decision {i + 1} · step {p.step}</span><span className="tabular">{p.ledger_len} done before</span></div>
                  <div className="mt-0.5 line-clamp-2 text-stone-800">{p.question ? `Asked: ${p.question}` : p.approvals.map((a) => describeCall(a.name, a.args)).join(" · ")}</div>
                  <button type="button" onClick={() => onFork(p.checkpoint_id)} disabled={ui.streaming}
                          className="mt-1.5 flex items-center gap-1 text-[11px] font-semibold text-ember-700 hover:underline disabled:opacity-40">
                    <Rewind className="h-3 w-3" aria-hidden="true" /> Branch from here
                  </button>
                </li>
              ))}
              {ui.history.length === 0 && <li className="text-stone-400">Loading…</li>}
            </ol>
          </div>
        )}
      </div>
    </aside>
  );
}
