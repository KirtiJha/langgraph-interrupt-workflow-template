"use client";

// The mission feed: what the agent is thinking, doing, comparing, changing —
// and what you decided. Everything is a card; nothing is a wall of text.

import { useEffect, useRef } from "react";
import {
  Archive, Ban, Bed, Bot, Brain, Calendar, Check, CircleDot, Clipboard, Flag, GitBranch, Inbox, Info, LoaderCircle,
  Mail, MessageSquare, Pencil, Plane, Repeat, Search, ShieldCheck, Sparkles, Ticket, TriangleAlert, User, Users, Wallet, X,
  CircleHelp, Hand,
} from "lucide-react";
import { Report, TOOL_LABELS, describeCall, money } from "../lib/api";
import { Entry, ToolCall } from "../lib/useMission";

const ICON: Record<string, any> = {
  inbox: Inbox, calendar: Calendar, wallet: Wallet, users: Users, repeat: Repeat, search: Search, plane: Plane, bed: Bed,
  clipboard: Clipboard, help: CircleHelp, brain: Brain, mail: Mail, archive: Archive, ticket: Ticket, ban: Ban, flag: Flag,
};

function CallRow({ call }: { call: ToolCall }) {
  const label = TOOL_LABELS[call.name];
  const Icon = ICON[label?.icon || "search"] || Search;
  const status = call.status;
  const text = describeCall(call.name, call.args);
  return (
    <li className="flex items-center gap-2.5 py-1.5">
      <span className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-lg ${
        status === "rejected" ? "bg-rose-100 text-rose-700" : status === "pending" ? "bg-ember-100 text-ember-700" : status === "edited" ? "bg-sky-100 text-sky-700" : "bg-stone-100 text-stone-600"}`}>
        <Icon className="h-3.5 w-3.5" aria-hidden="true" />
      </span>
      <span className={`min-w-0 flex-1 truncate text-[13px] ${status === "rejected" ? "text-stone-400 line-through" : "text-stone-800"}`}>{text}</span>
      <span className="shrink-0 text-stone-400" aria-label={status}>
        {status === "running" && <LoaderCircle className="h-3.5 w-3.5 animate-spin text-ember-500" />}
        {status === "pending" && <Hand className="h-3.5 w-3.5 text-ember-600" />}
        {status === "ok" && <Check className="h-3.5 w-3.5 text-emerald-600" />}
        {status === "edited" && <Pencil className="h-3.5 w-3.5 text-sky-600" />}
        {status === "rejected" && <X className="h-3.5 w-3.5 text-rose-500" />}
        {status === "responded" && <MessageSquare className="h-3.5 w-3.5 text-violet-600" />}
      </span>
    </li>
  );
}

function OptionCards({ kind, options }: { kind: string; options: any[] }) {
  return (
    <div className="-mx-1 flex snap-x gap-3 overflow-x-auto px-1 pb-1 scrollbar-none">
      {options.map((o) => {
        const price = o.price ?? o.price_per_person ?? o.price_per_night;
        const unit = o.price_per_person ? "/person" : o.price_per_night ? "/night" : "";
        return (
          <div key={o.id} className="w-56 shrink-0 snap-start rounded-xl border border-stone-200 bg-white p-3 text-[13px] shadow-sm">
            <div className="flex items-start justify-between gap-2">
              <div className="font-semibold text-ink">{o.name || o.vendor || o.airline}</div>
              {o.rating && <span className="chip border-amber-200 bg-amber-50 text-amber-800">★ {o.rating}</span>}
            </div>
            <div className="mt-0.5 text-stone-500">{o.cuisine || o.area || o.route || (o.crew ? `${o.crew}-person crew` : "")}{o.neighborhood ? ` · ${o.neighborhood}` : ""}{o.duration ? ` · ${o.duration}` : ""}</div>
            <div className="mt-2 flex items-baseline justify-between">
              <span className="tabular text-base font-semibold text-ink">{money(price)}<span className="text-xs font-normal text-stone-500">{unit}</span></span>
              <span className={`text-[11px] ${o.refundable ? "text-emerald-700" : "text-rose-700"}`}>{o.refundable ? "refundable" : "non-refundable"}</span>
            </div>
            {(o.highlight || o.note) && <div className="mt-1.5 text-xs text-stone-600">{o.highlight || o.note}</div>}
            {o.deposit != null && <div className="mt-1 text-[11px] text-stone-500">Deposit {money(o.deposit)}</div>}
            {kind === "restaurants" && <div className="mt-1 text-[11px] text-stone-500">{o.noise} · {o.vegetarian_friendly ? "vegetarian-friendly" : "limited veg"}</div>}
          </div>
        );
      })}
    </div>
  );
}

function ChangeChips({ ops }: { ops: any[] }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {ops.map((op, i) => {
        const text = op.op === "charge" ? `−${money(op.amount, 2)} · ${op.payee}` : op.op === "add_event" ? `Calendar · ${op.title}`
          : op.op === "send_email" ? `Sent · ${op.subject}` : op.op === "archive_email" ? `Archived ${op.ids?.length}` : op.op === "cancel_subscription" ? `Cancelled · ${op.id}`
          : op.op === "add_booking" ? `Booked · ${op.vendor}` : op.op;
        return <span key={i} className="chip border-emerald-200 bg-emerald-50 text-emerald-800 animate-pop"><Sparkles className="h-3 w-3" aria-hidden="true" />{text}</span>;
      })}
    </div>
  );
}

export function ReportCard({ report }: { report: Report }) {
  return (
    <div className="card animate-pop overflow-hidden">
      <div className="flex items-center gap-2 border-b border-stone-100 bg-stone-50 px-4 py-2.5">
        <Flag className="h-4 w-4 text-ember-600" aria-hidden="true" />
        <span className="text-[11px] font-semibold uppercase tracking-wide text-stone-600">Mission report</span>
        {report.spent > 0 && <span className="ml-auto tabular text-xs text-stone-600">Spent {money(report.spent, 2)}</span>}
      </div>
      <div className="p-4">
        <p className="text-[15px] leading-relaxed text-ink">{report.summary}</p>
        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          <div>
            <div className="text-[11px] font-semibold uppercase tracking-wide text-emerald-700">Done</div>
            <ul className="mt-1 space-y-1 text-[13px] text-stone-700">{report.done.map((d) => <li key={d} className="flex gap-1.5"><Check className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-600" aria-hidden="true" />{d}</li>)}</ul>
          </div>
          {report.open_items.length > 0 && (
            <div>
              <div className="text-[11px] font-semibold uppercase tracking-wide text-amber-700">Still open</div>
              <ul className="mt-1 space-y-1 text-[13px] text-stone-700">{report.open_items.map((d) => <li key={d} className="flex gap-1.5"><CircleDot className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-600" aria-hidden="true" />{d}</li>)}</ul>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default function Feed({ feed, streaming }: { feed: Entry[]; streaming: boolean }) {
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => { end.current?.scrollIntoView({ behavior: "smooth", block: "end" }); }, [feed.length, streaming]);

  return (
    <div className="space-y-3" role="log" aria-live="polite" aria-relevant="additions">
      {feed.map((e) => {
        switch (e.kind) {
          case "goal":
            return (
              <div key={e.id} className="flex justify-end animate-slide-up">
                <div className="flex max-w-[85%] items-start gap-2">
                  <div className="rounded-2xl rounded-tr-sm bg-ink px-4 py-2.5 text-[15px] leading-relaxed text-paper">{e.text}</div>
                  <span className="mt-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-stone-200 text-stone-700"><User className="h-3.5 w-3.5" aria-hidden="true" /></span>
                </div>
              </div>
            );
          case "narration":
            return (
              <div key={e.id} className="flex items-start gap-2 animate-fade-in">
                <span className="mt-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-ember-600 text-white"><Bot className="h-3.5 w-3.5" aria-hidden="true" /></span>
                <p className="max-w-[85%] rounded-2xl rounded-tl-sm border border-stone-200 bg-white px-4 py-2.5 text-[15px] leading-relaxed text-ink">
                  {e.text}{e.streaming && <span className="ml-0.5 inline-block h-4 w-1.5 animate-pulse-soft rounded-sm bg-ember-500 align-text-bottom" />}
                </p>
              </div>
            );
          case "tools":
            return (
              <div key={e.id} className="ml-9 rounded-xl border border-stone-200 bg-white/70 px-3 py-1 animate-fade-in">
                <ul className="divide-y divide-stone-100">{e.calls.map((c) => <CallRow key={c.id} call={c} />)}</ul>
              </div>
            );
          case "options":
            return <div key={e.id} className="ml-9 animate-fade-in"><OptionCards kind={e.optionsKind} options={e.options} /></div>;
          case "change":
            return <div key={e.id} className="ml-9"><ChangeChips ops={e.ops} /></div>;
          case "decision": {
            const tone = e.tone === "approve" ? "border-emerald-200 bg-emerald-50 text-emerald-800" : e.tone === "reject" ? "border-rose-200 bg-rose-50 text-rose-800"
              : e.tone === "edit" ? "border-sky-200 bg-sky-50 text-sky-800" : "border-violet-200 bg-violet-50 text-violet-800";
            const Icon = e.tone === "approve" ? Check : e.tone === "reject" ? X : e.tone === "edit" ? Pencil : MessageSquare;
            return (
              <div key={e.id} className="flex justify-end animate-slide-up">
                <span className={`chip max-w-[85%] whitespace-normal px-2.5 py-1 text-[12px] ${tone}`}><Icon className="h-3 w-3 shrink-0" aria-hidden="true" />{e.text}</span>
              </div>
            );
          }
          case "report":
            return <div key={e.id} className="ml-9"><ReportCard report={e.report} /></div>;
          case "system": {
            const Icon = e.tone === "memory" ? Brain : e.tone === "branch" ? GitBranch : e.tone === "warn" ? ShieldCheck : e.tone === "error" ? TriangleAlert : Info;
            const cls = e.tone === "error" ? "border-rose-200 bg-rose-50 text-rose-800" : e.tone === "branch" ? "border-ember-200 bg-ember-50 text-ember-800"
              : e.tone === "memory" ? "border-violet-200 bg-violet-50 text-violet-800" : "border-stone-200 bg-stone-50 text-stone-700";
            return (
              <div key={e.id} className={`ml-9 flex items-start gap-2 rounded-xl border px-3 py-2 text-[13px] animate-fade-in ${cls}`}>
                <Icon className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" /><span>{e.text}</span>
              </div>
            );
          }
        }
      })}
      {streaming && feed.length > 0 && feed[feed.length - 1].kind !== "narration" && (
        <div className="ml-9 flex items-center gap-2 text-xs text-stone-500 animate-fade-in">
          <LoaderCircle className="h-3.5 w-3.5 animate-spin text-ember-500" aria-hidden="true" /> Working…
        </div>
      )}
      <div ref={end} />
    </div>
  );
}
