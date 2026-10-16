"use client";

// Landing: pick a starter mission or type your own goal, and choose how much
// the agent should ask before acting.

import { useState } from "react";
import { ArrowRight, Brain, Gauge, Hand, Rocket, Sparkles, Zap } from "lucide-react";
import { Mission, World, money } from "../lib/api";

const ACCENT: Record<string, string> = {
  rose: "from-rose-100 to-rose-50 border-rose-200", amber: "from-amber-100 to-amber-50 border-amber-200",
  sky: "from-sky-100 to-sky-50 border-sky-200", violet: "from-violet-100 to-violet-50 border-violet-200",
  emerald: "from-emerald-100 to-emerald-50 border-emerald-200",
};

export const AUTONOMY_OPTIONS = [
  { id: "careful", label: "Careful", blurb: "Asks before every action.", Icon: Hand },
  { id: "balanced", label: "Balanced", blurb: "Asks when it's risky or over your limit.", Icon: Gauge },
  { id: "autopilot", label: "Autopilot", blurb: "Only asks for high-risk or irreversible actions.", Icon: Zap },
];

export default function Gallery({ missions, world, memories, offlinePilot, autonomy, askAbove, onAutonomy, onAskAbove, onStart, busy }: {
  missions: Mission[]; world: World | null; memories: string[]; offlinePilot: boolean;
  autonomy: string; askAbove: number; onAutonomy: (a: string) => void; onAskAbove: (n: number) => void;
  onStart: (goal: string, mission: Mission | null) => void; busy: boolean;
}) {
  const [goal, setGoal] = useState("");

  return (
    <div className="mx-auto w-full max-w-6xl px-4 pb-16 pt-8 sm:pt-12">
      <section className="grid items-start gap-8 lg:grid-cols-[1.2fr_1fr]">
        <div>
          <span className="chip border-ember-200 bg-ember-50 text-ember-700"><Sparkles className="h-3 w-3" aria-hidden="true" />Human-in-the-loop agent</span>
          <h1 className="mt-3 font-display text-4xl font-semibold leading-[1.05] tracking-tight text-ink sm:text-5xl">
            Give it a job.<br /><span className="text-ember-600">It asks before it acts.</span>
          </h1>
          <p className="mt-4 max-w-xl text-[15px] leading-relaxed text-stone-600">
            Mission Control plans and does real-life tasks inside your world — inbox, calendar, wallet, bookings — and pauses for your
            approval on anything that costs money, can't be undone, or involves other people. Approve, edit, reject or reply; rewind
            and try another path.
          </p>
          <form className="mt-6 flex flex-col gap-2 sm:flex-row" onSubmit={(e) => { e.preventDefault(); if (goal.trim()) onStart(goal.trim(), null); }}>
            <input className="field h-12 text-[15px]" value={goal} onChange={(e) => setGoal(e.target.value)} placeholder="Your own goal, e.g. “Find a weekend to see Jordan and book somewhere nice”" aria-label="Your goal" />
            <button type="submit" className="btn-accent h-12 shrink-0 px-5" disabled={busy || !goal.trim()}>
              <Rocket className="h-4 w-4" aria-hidden="true" /> Launch
            </button>
          </form>
          {offlinePilot && (
            <p className="mt-2 text-xs text-stone-500">
              Running on the offline pilot: the five starter missions below work fully without a key. For your own goals, add a model under <strong>Model</strong> in the header.
            </p>
          )}

          <div className="mt-6">
            <div className="text-[11px] font-semibold uppercase tracking-wide text-stone-500">How much should it ask?</div>
            <div role="radiogroup" aria-label="Autonomy" className="mt-2 grid gap-2 sm:grid-cols-3">
              {AUTONOMY_OPTIONS.map(({ id, label, blurb, Icon }) => (
                <button key={id} role="radio" aria-checked={autonomy === id} type="button" onClick={() => onAutonomy(id)}
                        className={`rounded-xl border p-3 text-left transition-all ${autonomy === id ? "border-ink bg-ink text-paper shadow-lift" : "border-stone-200 bg-white hover:border-stone-300"}`}>
                  <div className="flex items-center gap-1.5 text-sm font-semibold"><Icon className="h-4 w-4" aria-hidden="true" />{label}</div>
                  <div className={`mt-1 text-xs ${autonomy === id ? "text-paper/70" : "text-stone-500"}`}>{blurb}</div>
                </button>
              ))}
            </div>
            {autonomy === "balanced" && (
              <label className="mt-2 flex items-center gap-3 text-xs text-stone-600">
                Ask me before spending more than <strong className="tabular text-ink">{money(askAbove)}</strong>
                <input type="range" min={0} max={500} step={25} value={askAbove} onChange={(e) => onAskAbove(Number(e.target.value))} className="w-40 accent-ember-600" aria-label="Ask-first limit" />
              </label>
            )}
          </div>
        </div>

        <aside className="card bg-grid p-5">
          <div className="text-[11px] font-semibold uppercase tracking-wide text-stone-500">Your world (simulated)</div>
          {world ? (
            <dl className="mt-3 grid grid-cols-2 gap-2 text-sm">
              <div className="rounded-xl bg-white p-3 shadow-sm"><dt className="text-xs text-stone-500">Wallet</dt><dd className="tabular text-lg font-semibold text-ink">{money(world.wallet.balance, 2)}</dd></div>
              <div className="rounded-xl bg-white p-3 shadow-sm"><dt className="text-xs text-stone-500">Unread mail</dt><dd className="tabular text-lg font-semibold text-ink">{world.inbox.filter((e) => e.unread).length} <span className="text-xs font-normal text-rose-600">{world.inbox.filter((e) => e.urgent).length} urgent</span></dd></div>
              <div className="rounded-xl bg-white p-3 shadow-sm"><dt className="text-xs text-stone-500">Calendar</dt><dd className="tabular text-lg font-semibold text-ink">{world.calendar.length} <span className="text-xs font-normal text-stone-500">events</span></dd></div>
              <div className="rounded-xl bg-white p-3 shadow-sm"><dt className="text-xs text-stone-500">Subscriptions</dt><dd className="tabular text-lg font-semibold text-ink">{money(world.subscriptions.reduce((s, x) => s + x.price, 0))}<span className="text-xs font-normal text-stone-500">/mo</span></dd></div>
            </dl>
          ) : <p className="mt-3 text-sm text-stone-400">Loading…</p>}
          <p className="mt-3 text-xs text-stone-500">{world?.owner.name} · {world?.owner.city}. Every mission starts from this same world; nothing here is real.</p>
          <div className="mt-4 border-t border-stone-200/70 pt-3">
            <div className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-stone-500"><Brain className="h-3.5 w-3.5" aria-hidden="true" />What it remembers about you</div>
            {memories.length ? <ul className="mt-2 space-y-1 text-xs text-stone-700">{memories.map((m) => <li key={m}>· {m}</li>)}</ul>
              : <p className="mt-2 text-xs text-stone-400">Nothing yet — missions leave memories (“Mom is vegetarian”) that shape the next one.</p>}
          </div>
        </aside>
      </section>

      <section className="mt-10">
        <h2 className="text-[11px] font-semibold uppercase tracking-wide text-stone-500">Starter missions</h2>
        <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {missions.map((m) => (
            <button key={m.id} type="button" onClick={() => onStart(m.goal, m)} disabled={busy}
                    className={`group flex flex-col rounded-2xl border bg-gradient-to-br p-4 text-left shadow-card transition-all hover:-translate-y-0.5 hover:shadow-lift disabled:opacity-60 ${ACCENT[m.accent] || ACCENT.sky}`}>
              <div className="flex items-start justify-between">
                <span className="text-3xl" aria-hidden="true">{m.emoji}</span>
                <span className="chip border-white/60 bg-white/70 text-stone-600"><Hand className="h-3 w-3" aria-hidden="true" />~{m.approvals} approvals</span>
              </div>
              <h3 className="mt-3 text-base font-semibold leading-snug text-ink">{m.title}</h3>
              <p className="mt-1 text-[13px] text-stone-600">{m.blurb}</p>
              <div className="mt-3 flex flex-wrap gap-1">{m.tags.map((t) => <span key={t} className="chip border-white/60 bg-white/60 text-stone-600">{t}</span>)}</div>
              <span className="mt-4 flex items-center gap-1 text-sm font-semibold text-ink opacity-70 transition-opacity group-hover:opacity-100">Launch <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" aria-hidden="true" /></span>
            </button>
          ))}
        </div>
      </section>
    </div>
  );
}
