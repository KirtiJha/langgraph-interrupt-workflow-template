"use client";

// The mission feed: what the agent is thinking, doing, changing — and what you decided.

import { useEffect, useRef, useState } from "react";
import {
  Book, Bot, Brain, Check, CircleCheck, CircleDot, CircleHelp, Copy, Eye, FileText, Flag, GitBranch, GitMerge, GitPullRequest,
  Hand, Info, List, LoaderCircle, MessageSquare, Pencil, Plus, Search, ShieldCheck, Sparkles, Tag, TriangleAlert, Undo2,
  User, X, Diff,
} from "lucide-react";
import { Board, Report, TOOL_LABELS, describeCall, ledgerToMarkdown } from "../lib/api";
import { Entry, ToolCall } from "../lib/useMission";

const ICON: Record<string, any> = {
  list: List, git: GitPullRequest, book: Book, search: Search, file: FileText, diff: Diff, tag: Tag, help: CircleHelp,
  brain: Brain, message: MessageSquare, check: CircleCheck, undo: Undo2, pencil: Pencil, plus: Plus, user: User, eye: Eye, flag: Flag,
};

function CallRow({ call }: { call: ToolCall }) {
  const Icon = ICON[TOOL_LABELS[call.name]?.icon || "search"] || Search;
  const s = call.status;
  return (
    <li className="flex items-center gap-2.5 py-1.5">
      <span className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-lg ${s === "rejected" ? "bg-rose-100 text-rose-700" : s === "pending" ? "bg-ember-100 text-ember-700" : s === "edited" ? "bg-sky-100 text-sky-700" : s === "error" ? "bg-rose-100 text-rose-700" : "bg-stone-100 text-stone-600"}`}>
        <Icon className="h-3.5 w-3.5" aria-hidden="true" />
      </span>
      <span className={`min-w-0 flex-1 truncate text-[13px] ${s === "rejected" ? "text-stone-400 line-through" : "text-stone-800"}`} title={s === "error" ? call.result : undefined}>
        {describeCall(call.name, call.args)}{s === "error" && <span className="ml-1 text-rose-700">— {call.result?.slice(0, 80)}</span>}
      </span>
      <span className="shrink-0 text-stone-400" aria-label={s}>
        {s === "running" && <LoaderCircle className="h-3.5 w-3.5 animate-spin text-ember-500" />}
        {s === "pending" && <Hand className="h-3.5 w-3.5 text-ember-600" />}
        {s === "ok" && <Check className="h-3.5 w-3.5 text-emerald-600" />}
        {s === "edited" && <Pencil className="h-3.5 w-3.5 text-sky-600" />}
        {s === "rejected" && <X className="h-3.5 w-3.5 text-rose-500" />}
        {s === "error" && <TriangleAlert className="h-3.5 w-3.5 text-rose-600" />}
        {s === "responded" && <MessageSquare className="h-3.5 w-3.5 text-violet-600" />}
      </span>
    </li>
  );
}

function opText(op: any) {
  const n = op.number != null ? `#${op.number}` : "";
  return op.op === "add_labels" ? `${n} +${op.labels.join(", ")}` : op.op === "remove_labels" ? `${n} −${op.labels.join(", ")}`
    : op.op === "comment" ? `Comment on ${n}` : op.op === "close" ? `Closed ${n}` : op.op === "reopen" ? `Reopened ${n}` : op.op === "retitle" ? `Retitled ${n}`
    : op.op === "create_issue" ? `Opened “${op.title}”` : op.op === "assign" ? `${n} → @${op.assignees.join(", @")}` : op.op === "request_review" ? `Review ${n} ← @${op.reviewers.join(", @")}`
    : op.op === "merge" ? `Merged ${n}` : op.op;
}

function ChangeChips({ ops }: { ops: any[] }) {
  const [open, setOpen] = useState(false);
  const CAP = 8;
  const shown = open ? ops : ops.slice(0, CAP);
  const proposed = ops.every((o) => o.proposed);
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <span className={`text-[11px] font-semibold uppercase tracking-wide ${proposed ? "text-violet-700" : "text-emerald-700"}`}>
        {proposed ? "Proposed" : "Applied"} · {ops.length}
      </span>
      {shown.map((op, i) => (
        <span key={i} className={`chip max-w-full animate-pop ${op.proposed ? "border-violet-200 bg-violet-50 text-violet-800" : "border-emerald-200 bg-emerald-50 text-emerald-800"}`}>
          <Sparkles className="h-3 w-3 shrink-0" aria-hidden="true" /><span className="truncate">{opText(op)}</span>
          {op.url && <a href={op.url} target="_blank" rel="noreferrer" className="ml-1 underline-offset-2 hover:underline" aria-label="Open on GitHub">↗</a>}
        </span>
      ))}
      {ops.length > CAP && (
        <button type="button" onClick={() => setOpen((v) => !v)} className="chip border-stone-200 bg-white text-stone-600 hover:text-ink">
          {open ? "Show less" : `+${ops.length - CAP} more`}
        </button>
      )}
    </div>
  );
}

function ToolList({ calls }: { calls: ToolCall[] }) {
  const [open, setOpen] = useState(false);
  const CAP = 6;
  // Keep anything still waiting on you visible even when collapsed.
  const pending = calls.filter((c) => c.status === "pending" || c.status === "running");
  const shown = open || calls.length <= CAP ? calls : [...calls.filter((c) => !pending.includes(c)).slice(0, CAP - Math.min(pending.length, CAP - 2)), ...pending].slice(0, Math.max(CAP, pending.length));
  const hidden = calls.length - shown.length;
  return (
    <div className="ml-9 min-w-0 rounded-xl border border-stone-200 bg-white/70 px-3 py-1 animate-fade-in">
      <ul className="divide-y divide-stone-100">{shown.map((c) => <CallRow key={c.id} call={c} />)}</ul>
      {(open ? calls.length > CAP : hidden > 0) && (
        <button type="button" onClick={() => setOpen((v) => !v)} className="w-full border-t border-stone-100 py-1.5 text-left text-[12px] font-medium text-stone-500 hover:text-ink">
          {open ? "Show fewer" : `Show ${hidden} more`}
        </button>
      )}
    </div>
  );
}

const KIND_LABEL: Record<string, string> = { Labelled: "Labelled", Commented: "Comments", Closed: "Closed", Opened: "Opened", Requested: "Reviews", Assigned: "Assigned", Retitled: "Retitled", Merged: "Merged", Removed: "Unlabelled", Reopened: "Reopened" };

export function ReportCard({ report, board, title }: { report: Report; board: Board | null; title: string }) {
  const [copied, setCopied] = useState(false);
  const [open, setOpen] = useState(false);
  const copy = async () => {
    if (!board) return;
    try { await navigator.clipboard.writeText(ledgerToMarkdown(board, title)); setCopied(true); setTimeout(() => setCopied(false), 1500); } catch { /* clipboard blocked */ }
  };
  const counts: Record<string, number> = {};
  for (const d of report.done) {
    const k = KIND_LABEL[d.split(" ")[0]] || "Other";
    counts[k] = (counts[k] || 0) + 1;
  }
  const declined = report.open_items.filter((d) => d.startsWith("Skipped")).length;
  const CAP = 5;
  const done = open ? report.done : report.done.slice(0, CAP);
  return (
    <div className="card animate-pop overflow-hidden">
      <div className="flex flex-wrap items-center gap-2 border-b border-stone-100 bg-stone-50 px-4 py-2.5">
        <Flag className="h-4 w-4 text-ember-600" aria-hidden="true" />
        <span className="text-[11px] font-semibold uppercase tracking-wide text-stone-600">Mission report</span>
        {report.proposals > 0 && <span className="chip border-violet-200 bg-violet-50 text-violet-700">{report.proposals} proposal{report.proposals === 1 ? "" : "s"}</span>}
        {board && board.ledger.length > 0 && (
          <button type="button" onClick={copy} className="ml-auto flex items-center gap-1 text-[11px] font-medium text-stone-600 hover:text-ink">
            {copied ? <Check className="h-3.5 w-3.5 text-emerald-600" aria-hidden="true" /> : <Copy className="h-3.5 w-3.5" aria-hidden="true" />}{copied ? "Copied" : "Copy as checklist"}
          </button>
        )}
      </div>
      <div className="p-4">
        <p className="text-[15px] leading-relaxed text-ink">{report.summary}</p>
        {(Object.keys(counts).length > 0 || declined > 0) && (
          <dl className="mt-3 flex flex-wrap gap-2">
            {Object.entries(counts).map(([k, v]) => (
              <div key={k} className="rounded-xl border border-stone-200 bg-white px-3 py-1.5"><dt className="text-[10px] uppercase tracking-wide text-stone-500">{k}</dt><dd className="tabular text-base font-semibold text-ink">{v}</dd></div>
            ))}
            {declined > 0 && <div className="rounded-xl border border-rose-200 bg-rose-50 px-3 py-1.5"><dt className="text-[10px] uppercase tracking-wide text-rose-700">Declined</dt><dd className="tabular text-base font-semibold text-rose-700">{declined}</dd></div>}
          </dl>
        )}
        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          {report.done.length > 0 && (
            <div className="min-w-0">
              <div className="text-[11px] font-semibold uppercase tracking-wide text-emerald-700">{report.proposals ? "Proposed" : "Done"}</div>
              <ul className="mt-1 space-y-1 text-[13px] text-stone-700">{done.map((d, i) => <li key={i} className="flex gap-1.5"><Check className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-600" aria-hidden="true" /><span className="min-w-0 break-words">{d}</span></li>)}</ul>
              {report.done.length > CAP && (
                <button type="button" onClick={() => setOpen((v) => !v)} className="mt-1 text-[12px] font-medium text-stone-500 hover:text-ink">{open ? "Show less" : `Show all ${report.done.length}`}</button>
              )}
            </div>
          )}
          {report.open_items.length > 0 && (
            <div className="min-w-0">
              <div className="text-[11px] font-semibold uppercase tracking-wide text-amber-700">Needs you</div>
              <ul className="mt-1 space-y-1 text-[13px] text-stone-700">{report.open_items.map((d, i) => <li key={i} className="flex gap-1.5"><CircleDot className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-600" aria-hidden="true" /><span className="min-w-0 break-words">{d}</span></li>)}</ul>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default function Feed({ feed, streaming, board, title }: { feed: Entry[]; streaming: boolean; board: Board | null; title: string }) {
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => { end.current?.scrollIntoView({ behavior: "smooth", block: "end" }); }, [feed.length, streaming]);

  return (
    <div className="min-w-0 space-y-3" role="log" aria-live="polite" aria-relevant="additions">
      {feed.map((e) => {
        switch (e.kind) {
          case "goal":
            return (
              <div key={e.id} className="flex justify-end animate-slide-up">
                <div className="flex max-w-[85%] items-start gap-2">
                  <div className="min-w-0 break-words rounded-2xl rounded-tr-sm bg-ink px-4 py-2.5 text-[15px] leading-relaxed text-paper">{e.text}</div>
                  <span className="mt-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-stone-200 text-stone-700"><User className="h-3.5 w-3.5" aria-hidden="true" /></span>
                </div>
              </div>
            );
          case "narration":
            return (
              <div key={e.id} className="flex items-start gap-2 animate-fade-in">
                <span className="mt-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-ember-600 text-white"><Bot className="h-3.5 w-3.5" aria-hidden="true" /></span>
                <p className="min-w-0 max-w-[85%] break-words rounded-2xl rounded-tl-sm border border-stone-200 bg-white px-4 py-2.5 text-[15px] leading-relaxed text-ink">
                  {e.text}{e.streaming && <span className="ml-0.5 inline-block h-4 w-1.5 animate-pulse-soft rounded-sm bg-ember-500 align-text-bottom" />}
                </p>
              </div>
            );
          case "tools":
            return <ToolList key={e.id} calls={e.calls} />;
          case "change":
            return <div key={e.id} className="ml-9 min-w-0"><ChangeChips ops={e.ops} /></div>;
          case "decision": {
            const tone = e.tone === "approve" ? "border-emerald-200 bg-emerald-50 text-emerald-800" : e.tone === "reject" ? "border-rose-200 bg-rose-50 text-rose-800"
              : e.tone === "edit" ? "border-sky-200 bg-sky-50 text-sky-800" : "border-violet-200 bg-violet-50 text-violet-800";
            const Icon = e.tone === "approve" ? Check : e.tone === "reject" ? X : e.tone === "edit" ? Pencil : MessageSquare;
            return <div key={e.id} className="flex justify-end animate-slide-up"><span className={`chip max-w-[85%] whitespace-normal px-2.5 py-1 text-[12px] ${tone}`}><Icon className="h-3 w-3 shrink-0" aria-hidden="true" />{e.text}</span></div>;
          }
          case "report":
            return <div key={e.id} className="ml-9 min-w-0"><ReportCard report={e.report} board={board} title={title} /></div>;
          case "system": {
            const Icon = e.tone === "memory" ? Brain : e.tone === "branch" ? GitBranch : e.tone === "warn" ? ShieldCheck : e.tone === "error" ? TriangleAlert : Info;
            const cls = e.tone === "error" ? "border-rose-200 bg-rose-50 text-rose-800" : e.tone === "branch" ? "border-ember-200 bg-ember-50 text-ember-800"
              : e.tone === "memory" ? "border-violet-200 bg-violet-50 text-violet-800" : "border-stone-200 bg-stone-50 text-stone-700";
            return <div key={e.id} className={`ml-9 flex min-w-0 items-start gap-2 rounded-xl border px-3 py-2 text-[13px] animate-fade-in ${cls}`}><Icon className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" /><span className="min-w-0 break-words">{e.text}</span></div>;
          }
        }
      })}
      {streaming && feed.length > 0 && feed[feed.length - 1].kind !== "narration" && (
        <div className="ml-9 flex items-center gap-2 text-xs text-stone-500 animate-fade-in"><LoaderCircle className="h-3.5 w-3.5 animate-spin text-ember-500" aria-hidden="true" /> Working…</div>
      )}
      <div ref={end} />
    </div>
  );
}

