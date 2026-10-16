"use client";

// The repository board — issues, pull requests, labels, activity — with the
// agent's pending actions drawn in as dashed "ghosts" until you approve them.

import { useState } from "react";
import { Activity, CircleDot, GitPullRequest, MessageSquare, Tag } from "lucide-react";
import { Approval, Board, Issue, ageLabel } from "../lib/api";
import { LabelChip } from "./ApprovalCard";

type Tab = "issues" | "pulls" | "labels" | "activity";
const TABS: { id: Tab; label: string; Icon: any }[] = [
  { id: "issues", label: "Issues", Icon: CircleDot }, { id: "pulls", label: "Pull requests", Icon: GitPullRequest },
  { id: "labels", label: "Labels", Icon: Tag }, { id: "activity", label: "Activity", Icon: Activity },
];

function ghostsFor(pending: Approval[], number: number) {
  const p = pending.filter((a) => a.args?.number === number);
  return {
    labels: p.filter((a) => a.name === "add_labels").flatMap((a) => a.args.labels as string[]),
    comments: p.filter((a) => a.name === "comment" || (a.name === "close_issue" && a.args.note)).length,
    close: p.some((a) => a.name === "close_issue"),
    merge: p.some((a) => a.name === "merge_pull"),
    review: p.filter((a) => a.name === "request_reviewers").flatMap((a) => a.args.reviewers as string[]),
    retitle: p.find((a) => a.name === "retitle")?.args.title as string | undefined,
  };
}

function Row({ item, board, pending }: { item: Issue; board: Board; pending: Approval[] }) {
  const g = ghostsFor(pending, item.number);
  const closed = item.state !== "open";
  const touched = g.labels.length || g.comments || g.close || g.merge || g.review.length || g.retitle;
  const agentThread = (item.thread || []).filter((t) => t.author === "repo-steward");
  return (
    <li className={`rounded-xl border p-2.5 ${closed ? "border-stone-100 bg-stone-50/70 opacity-70" : touched ? "ghost" : item.by_agent ? "border-emerald-200 bg-emerald-50/50" : "border-stone-200 bg-white"}`}>
      <div className="flex items-start gap-2">
        <span className={`mt-0.5 shrink-0 font-mono text-[11px] ${closed ? "text-stone-400" : "text-stone-500"}`}>#{item.number}</span>
        <div className="min-w-0 flex-1">
          <div className={`text-[13px] leading-snug ${closed ? "text-stone-500 line-through" : "text-ink"}`}>
            {g.retitle ? <><span className="line-through text-stone-400">{item.title}</span> <span className="text-ember-700">{g.retitle}</span></> : item.title}
            {item.url && <a href={item.url} target="_blank" rel="noreferrer" className="ml-1 text-[11px] text-stone-400 hover:text-ember-700">↗</a>}
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-1">
            {item.labels.map((l) => <LabelChip key={l} name={l} labels={board.labels} />)}
            {g.labels.map((l) => <LabelChip key={`g-${l}`} name={l} labels={board.labels} ghost />)}
            {item.draft && <span className="chip border-stone-200 bg-stone-50 text-stone-500">draft</span>}
            {item.state === "merged" && <span className="chip border-violet-200 bg-violet-50 text-violet-700">merged</span>}
            {closed && item.state !== "merged" && <span className="chip border-stone-200 bg-stone-50 text-stone-500">closed{item.state_reason ? ` · ${item.state_reason.replace("_", " ")}` : ""}</span>}
            {g.close && <span className="chip border-ember-300 bg-ember-50 text-ember-700">will close</span>}
            {g.merge && <span className="chip border-rose-300 bg-rose-50 text-rose-700">will merge</span>}
            {g.comments > 0 && <span className="chip border-ember-300 bg-ember-50 text-ember-700"><MessageSquare className="h-3 w-3" aria-hidden="true" />reply pending</span>}
            {g.review.length > 0 && <span className="chip border-ember-300 bg-ember-50 text-ember-700">review → @{g.review.join(", @")}</span>}
            {agentThread.length > 0 && <span className={`chip ${agentThread.some((t) => t.proposed) ? "border-violet-200 bg-violet-50 text-violet-700" : "border-emerald-200 bg-emerald-50 text-emerald-700"}`}>{agentThread.some((t) => t.proposed) ? "proposed reply" : "replied"}</span>}
          </div>
          <div className="mt-1 text-[11px] text-stone-500">
            {item.author}{item.author_association === "FIRST_TIME_CONTRIBUTOR" || item.author_association === "FIRST_TIMER" ? " · first-timer" : ""} · {ageLabel(item.created_at)}
            {item.comments ? ` · ${item.comments} comment${item.comments === 1 ? "" : "s"}` : ""}{item.updated_at && (item.updated_at !== item.created_at) ? ` · active ${ageLabel(item.updated_at)}` : ""}
          </div>
        </div>
      </div>
    </li>
  );
}

export default function BoardPanel({ board, pending, compact }: { board: Board; pending: Approval[]; compact?: boolean }) {
  const [tab, setTab] = useState<Tab>("issues");
  const openIssues = board.issues.filter((i) => i.state === "open");
  const openPulls = board.pulls.filter((i) => i.state === "open");
  const counts: Record<Tab, number> = { issues: openIssues.length, pulls: openPulls.length, labels: board.labels.length, activity: board.ledger.length };
  const ghostCount = (items: Issue[]) => items.filter((i) => pending.some((a) => a.args?.number === i.number)).length;
  const ghosts: Record<Tab, number> = { issues: ghostCount(board.issues), pulls: ghostCount(board.pulls), labels: 0, activity: 0 };

  return (
    <div className={`flex h-full flex-col ${compact ? "" : "card"}`}>
      <div className="border-b border-stone-100 px-3 pt-2.5">
        <div className="flex items-center gap-2 text-sm">
          <a href={board.repo.url} target="_blank" rel="noreferrer" className="truncate font-semibold text-ink hover:text-ember-700">{board.repo.full_name}</a>
          <span className={`chip ml-auto ${board.mode === "live" ? (board.can_write ? "border-emerald-200 bg-emerald-50 text-emerald-700" : "border-violet-200 bg-violet-50 text-violet-700") : "border-stone-200 bg-stone-50 text-stone-600"}`}>
            {board.mode === "live" ? (board.can_write ? "live · write" : "live · read-only") : "sample repo"}
          </span>
        </div>
        {board.repo.description && <p className="mt-0.5 truncate text-[11px] text-stone-500">{board.repo.description}</p>}
      </div>
      <div role="tablist" aria-label="Repository" className="flex gap-1 overflow-x-auto border-b border-stone-100 p-2 scrollbar-none">
        {TABS.map(({ id, label, Icon }) => (
          <button key={id} role="tab" aria-selected={tab === id} onClick={() => setTab(id)}
                  className={`relative flex shrink-0 items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-medium transition-colors ${tab === id ? "bg-ink text-paper" : "text-stone-600 hover:bg-stone-100"}`}>
            <Icon className="h-3.5 w-3.5" aria-hidden="true" />{label}
            {counts[id] > 0 && <span className={`tabular rounded-full px-1.5 text-[10px] ${tab === id ? "bg-paper/20" : "bg-stone-200"}`}>{counts[id]}</span>}
            {ghosts[id] > 0 && <span className="absolute -right-0.5 -top-0.5 h-2 w-2 rounded-full bg-ember-500 animate-pulse-soft" aria-label={`${ghosts[id]} pending`} />}
          </button>
        ))}
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto p-3 text-[13px]">
        {tab === "issues" && (
          <ul className="space-y-1.5">
            {board.issues.length === 0 && <li className="py-8 text-center text-xs text-stone-400">No open issues.</li>}
            {board.issues.map((i) => <Row key={i.number} item={i} board={board} pending={pending} />)}
          </ul>
        )}
        {tab === "pulls" && (
          <ul className="space-y-1.5">
            {board.pulls.length === 0 && <li className="py-8 text-center text-xs text-stone-400">No open pull requests.</li>}
            {board.pulls.map((i) => <Row key={i.number} item={i} board={board} pending={pending} />)}
          </ul>
        )}
        {tab === "labels" && (
          <ul className="space-y-1.5">
            {board.labels.map((l) => (
              <li key={l.name} className="flex items-center gap-2 rounded-lg border border-stone-200 bg-white px-2.5 py-1.5">
                <LabelChip name={l.name} labels={board.labels} />
                <span className="truncate text-xs text-stone-500">{l.description}</span>
                <span className="tabular ml-auto text-[11px] text-stone-400">{board.issues.concat(board.pulls).filter((i) => i.labels.includes(l.name)).length}</span>
              </li>
            ))}
          </ul>
        )}
        {tab === "activity" && (
          <ol className="space-y-1">
            {board.ledger.length === 0 && <li className="py-8 text-center text-xs text-stone-400">Nothing yet — actions you approve land here{board.mode === "live" ? ", with links" : ""}.</li>}
            {[...board.ledger].reverse().map((l) => (
              <li key={l.seq} className={`flex items-start gap-2 rounded-lg px-2.5 py-1.5 ${l.proposed ? "bg-violet-50/70" : "bg-emerald-50/60"}`}>
                <span className="tabular mt-0.5 text-[10px] text-stone-400">{l.seq}</span>
                <span className="min-w-0 flex-1 text-stone-800">{l.proposed && <span className="mr-1 text-[11px] font-medium text-violet-700">proposed</span>}{l.summary}</span>
                {l.url && <a href={l.url} target="_blank" rel="noreferrer" className="text-[11px] text-ember-700 hover:underline">↗</a>}
              </li>
            ))}
          </ol>
        )}
      </div>
    </div>
  );
}
