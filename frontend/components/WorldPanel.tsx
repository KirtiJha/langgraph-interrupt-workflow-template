"use client";

// Your world — inbox, calendar, wallet, bookings, subscriptions — with the
// agent's pending actions drawn in as dashed "ghosts" until you approve them.

import { useState } from "react";
import { Calendar, Inbox, Repeat, Ticket, Wallet } from "lucide-react";
import { Approval, World, fmtDate, fmtTime, money } from "../lib/api";

type Tab = "inbox" | "calendar" | "wallet" | "bookings" | "subscriptions";
const TABS: { id: Tab; label: string; Icon: any }[] = [
  { id: "inbox", label: "Inbox", Icon: Inbox }, { id: "calendar", label: "Calendar", Icon: Calendar },
  { id: "wallet", label: "Wallet", Icon: Wallet }, { id: "bookings", label: "Bookings", Icon: Ticket },
  { id: "subscriptions", label: "Plans", Icon: Repeat },
];

function previews(pending: Approval[], kind: string) {
  return pending.map((a) => a.risk?.preview).filter((p) => p && (p.kind === kind || (kind === "charge" && p.kind === "booking")));
}

export default function WorldPanel({ world, pending, startBalance, compact }: {
  world: World; pending: Approval[]; startBalance: number | null; compact?: boolean;
}) {
  const [tab, setTab] = useState<Tab>("inbox");
  const counts: Record<Tab, number> = {
    inbox: world.inbox.filter((e) => e.unread).length, calendar: 0, wallet: 0,
    bookings: world.bookings.length, subscriptions: world.subscriptions.filter((s) => s.status === "active").length,
  };
  const ghosts: Record<Tab, number> = {
    inbox: previews(pending, "email").length + previews(pending, "archive").length,
    calendar: previews(pending, "event").length, wallet: previews(pending, "charge").length,
    bookings: pending.filter((a) => a.name === "book").length, subscriptions: previews(pending, "cancel").length,
  };
  const delta = startBalance != null ? world.wallet.balance - startBalance : 0;

  return (
    <div className={`flex h-full flex-col ${compact ? "" : "card"}`}>
      <div role="tablist" aria-label="Your world" className="flex gap-1 overflow-x-auto border-b border-stone-100 p-2 scrollbar-none">
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
        {tab === "inbox" && (
          <div className="space-y-1.5">
            {previews(pending, "email").map((p, i) => (
              <div key={`g${i}`} className="rounded-xl border ghost p-2.5">
                <div className="flex items-center justify-between"><span className="text-[11px] font-semibold uppercase tracking-wide text-ember-700">Waiting to send</span><span className="text-[11px] text-stone-500">to {p.to.length}</span></div>
                <div className="mt-0.5 truncate font-medium text-ink">{p.subject}</div>
              </div>
            ))}
            {world.inbox.map((e) => {
              const archiving = previews(pending, "archive").some((p) => p.subjects.includes(e.subject));
              return (
                <div key={e.id} className={`rounded-xl border p-2.5 ${archiving ? "ghost opacity-70" : e.unread ? "border-stone-200 bg-white" : "border-stone-100 bg-stone-50/60"}`}>
                  <div className="flex items-center gap-1.5">
                    {e.unread && <span className="h-1.5 w-1.5 rounded-full bg-ember-500" aria-label="unread" />}
                    <span className={`truncate ${e.unread ? "font-semibold text-ink" : "text-stone-700"}`}>{e.from_name}</span>
                    {e.urgent && <span className="chip border-rose-200 bg-rose-50 text-rose-700">urgent</span>}
                    {e.replied && <span className="chip border-emerald-200 bg-emerald-50 text-emerald-700">replied</span>}
                    {archiving && <span className="chip border-ember-300 bg-ember-50 text-ember-700">archiving…</span>}
                    <span className="ml-auto shrink-0 text-[11px] text-stone-400">{fmtDate(e.date, { month: "short", day: "numeric" })}</span>
                  </div>
                  <div className="mt-0.5 truncate text-stone-800">{e.subject}</div>
                  <div className="truncate text-xs text-stone-500">{e.body}</div>
                </div>
              );
            })}
            {world.sent.length > 0 && (
              <div className="pt-2">
                <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-stone-500">Sent by the agent</div>
                {world.sent.map((s) => (
                  <div key={s.id} className="mb-1.5 rounded-xl border border-emerald-200 bg-emerald-50/50 p-2.5">
                    <div className="truncate font-medium text-ink">{s.subject}</div>
                    <div className="truncate text-xs text-stone-600">to {s.to.join(", ")}</div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {tab === "calendar" && (
          <ol className="space-y-1.5">
            {[...world.calendar.map((e) => ({ ...e, ghost: false })),
              ...previews(pending, "event").map((p, i) => ({ id: `g${i}`, title: p.title, start: p.start, end: p.end, location: p.location, attendees: p.attendees || [], source: "agent", ghost: true }))]
              .sort((a, b) => (a.start || "").localeCompare(b.start || ""))
              .map((e) => (
                <li key={e.id} className={`flex gap-2.5 rounded-xl border p-2.5 ${e.ghost ? "ghost" : e.source === "agent" ? "border-emerald-200 bg-emerald-50/50" : "border-stone-200 bg-white"}`}>
                  <div className="w-11 shrink-0 text-center">
                    <div className="text-[10px] font-semibold uppercase text-stone-500">{fmtDate(e.start, { weekday: "short" })}</div>
                    <div className="tabular text-lg font-semibold leading-none text-ink">{new Date(e.start).getDate()}</div>
                    <div className="text-[10px] text-stone-500">{fmtDate(e.start, { month: "short" })}</div>
                  </div>
                  <div className="min-w-0">
                    <div className="truncate font-medium text-ink">{e.title}{e.ghost && <span className="ml-1.5 text-[11px] font-normal text-ember-700">pending</span>}</div>
                    <div className="text-xs text-stone-500">{fmtTime(e.start)}–{fmtTime(e.end)}{e.location ? ` · ${e.location}` : ""}</div>
                    {e.attendees?.length > 0 && <div className="text-[11px] text-stone-500">{e.attendees.length} invited</div>}
                  </div>
                </li>
              ))}
          </ol>
        )}

        {tab === "wallet" && (
          <div>
            <div className="rounded-2xl bg-ink p-4 text-paper">
              <div className="text-[11px] uppercase tracking-wide text-paper/60">Balance</div>
              <div className="tabular mt-0.5 text-3xl font-semibold">{money(world.wallet.balance, 2)}</div>
              {delta !== 0 && <div className={`tabular mt-1 text-xs ${delta < 0 ? "text-ember-300" : "text-emerald-300"}`}>{delta < 0 ? "−" : "+"}{money(Math.abs(delta), 2)} this mission</div>}
              {previews(pending, "charge").length > 0 && (
                <div className="mt-2 border-t border-paper/15 pt-2 text-xs text-paper/80">
                  Pending: {previews(pending, "charge").map((p) => `−${money(p.amount, 2)} ${p.payee}`).join(" · ")}
                </div>
              )}
            </div>
            <ul className="mt-3 space-y-1">
              {previews(pending, "charge").map((p, i) => (
                <li key={`g${i}`} className="flex items-center justify-between rounded-lg border ghost px-2.5 py-2"><span className="truncate text-ink">{p.payee} <span className="text-[11px] text-ember-700">pending</span></span><span className="tabular text-ember-700">−{money(p.amount, 2)}</span></li>
              ))}
              {world.wallet.transactions.map((t) => (
                <li key={t.id} className={`flex items-center justify-between rounded-lg px-2.5 py-2 ${t.by_agent ? "bg-emerald-50/60" : ""}`}>
                  <span className="min-w-0"><span className="block truncate text-ink">{t.payee}</span><span className="text-[11px] text-stone-500">{fmtDate(t.date, { month: "short", day: "numeric" })} · {t.category}</span></span>
                  <span className={`tabular ${t.amount > 0 ? "text-emerald-700" : "text-ink"}`}>{t.amount > 0 ? "+" : "−"}{money(Math.abs(t.amount), 2)}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {tab === "bookings" && (
          <div className="space-y-1.5">
            {pending.filter((a) => a.name === "book").map((a) => (
              <div key={a.interrupt_id} className="rounded-xl border ghost p-2.5"><div className="font-medium text-ink">{a.args.vendor} <span className="text-[11px] font-normal text-ember-700">awaiting your approval</span></div><div className="text-xs text-stone-600">{a.args.kind} · {fmtDate(a.args.date)} · {money(a.args.amount)}</div></div>
            ))}
            {world.bookings.length === 0 && pending.every((a) => a.name !== "book") && <p className="py-8 text-center text-xs text-stone-400">No bookings yet.</p>}
            {world.bookings.map((b) => (
              <div key={b.id} className="rounded-xl border border-emerald-200 bg-emerald-50/50 p-2.5">
                <div className="flex items-center justify-between"><span className="font-medium text-ink">{b.vendor}</span><span className="chip border-emerald-200 bg-white text-emerald-700">{b.confirmation}</span></div>
                <div className="text-xs text-stone-600">{b.kind} · {fmtDate(b.date)} · {money(b.amount)} · {b.refundable ? "refundable" : "non-refundable"}</div>
                {b.details && <div className="mt-0.5 text-[11px] text-stone-500">{b.details}</div>}
              </div>
            ))}
          </div>
        )}

        {tab === "subscriptions" && (
          <ul className="space-y-1.5">
            {world.subscriptions.map((s) => {
              const ghost = previews(pending, "cancel").some((p) => p.name === s.name);
              return (
                <li key={s.id} className={`flex items-center justify-between rounded-xl border p-2.5 ${s.status === "cancelled" ? "border-stone-100 bg-stone-50 opacity-60" : ghost ? "ghost" : "border-stone-200 bg-white"}`}>
                  <span className="min-w-0"><span className={`block truncate ${s.status === "cancelled" ? "line-through" : "text-ink"}`}>{s.name}</span>
                    <span className="text-[11px] text-stone-500">{s.status === "cancelled" ? "cancelled" : ghost ? "cancelling — awaiting you" : `used ${s.last_used_days}d ago`}</span></span>
                  <span className="tabular text-stone-700">{money(s.price, 2)}<span className="text-[10px] text-stone-400">/mo</span></span>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </div>
  );
}
