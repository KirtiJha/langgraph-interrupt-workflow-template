"use client";

// One pending action: what it is, how risky, what will change — and the four
// decisions (approve / edit / reject / respond) that resume the agent.

import { useEffect, useState } from "react";
import {
  Ban, Calendar, Check, Mail, MessageSquare, Pencil, ShieldAlert, ShieldCheck, Ticket, Undo2, Wallet, X, Archive,
} from "lucide-react";
import { Approval, Decision, describeCall, fmtDate, fmtTime, money } from "../lib/api";

const ICONS: Record<string, any> = {
  book: Ticket, pay: Wallet, send_email: Mail, add_calendar_event: Calendar, archive_emails: Archive, cancel_subscription: Ban,
};

const LEVEL = {
  low: { label: "Low risk", cls: "border-emerald-200 bg-emerald-50 text-emerald-700", Icon: ShieldCheck },
  medium: { label: "Medium risk", cls: "border-amber-200 bg-amber-50 text-amber-800", Icon: ShieldAlert },
  high: { label: "High risk", cls: "border-rose-200 bg-rose-50 text-rose-700", Icon: ShieldAlert },
};

export function Preview({ preview, args }: { preview: any; args: Record<string, any> }) {
  if (!preview) return null;
  switch (preview.kind) {
    case "charge":
    case "booking":
      return (
        <div className="rounded-xl border border-stone-200 bg-stone-50 p-3 text-sm">
          <div className="flex items-baseline justify-between gap-3">
            <span className="text-stone-600">Wallet</span>
            <span className="tabular">
              <span className="text-stone-500">{money(preview.balance_before, 2)}</span>
              <span className="mx-1.5 text-stone-400">→</span>
              <span className={`font-semibold ${preview.balance_after < 0 ? "text-rose-700" : "text-ink"}`}>
                {money(preview.balance_after, 2)}
              </span>
            </span>
          </div>
          <div className="mt-1 flex items-baseline justify-between gap-3">
            <span className="text-stone-600">{preview.kind === "booking" ? `${preview.booking_kind} · ${fmtDate(preview.date)}` : "Payment"}</span>
            <span className="tabular font-semibold text-ember-700">−{money(preview.amount, 2)}</span>
          </div>
          {preview.details && <p className="mt-1.5 text-xs text-stone-500">{preview.details}</p>}
          <p className="mt-1.5 text-xs">
            {preview.refundable ? <span className="text-emerald-700">Refundable</span> : <span className="text-rose-700">Non-refundable</span>}
          </p>
        </div>
      );
    case "email":
      return (
        <div className="rounded-xl border border-stone-200 bg-white text-sm">
          <div className="border-b border-stone-100 px-3 py-2 text-xs text-stone-600">
            <div><span className="text-stone-400">To </span>{preview.to.join(", ")}</div>
            <div className="mt-0.5 font-medium text-ink">{preview.subject}</div>
          </div>
          <pre className="max-h-40 overflow-auto whitespace-pre-wrap px-3 py-2 font-sans text-[13px] leading-relaxed text-stone-700">{preview.body}</pre>
        </div>
      );
    case "event":
      return (
        <div className="rounded-xl border border-dashed border-ember-400 bg-ember-50/70 p-3 text-sm">
          <div className="font-medium text-ink">{preview.title}</div>
          <div className="mt-0.5 text-xs text-stone-600">
            {fmtDate(preview.start, { weekday: "long", month: "long", day: "numeric" })} · {fmtTime(preview.start)}–{fmtTime(preview.end)}
            {preview.location ? ` · ${preview.location}` : ""}
          </div>
          {preview.attendees?.length > 0 && (
            <div className="mt-1 text-xs text-stone-600">Invites {preview.attendees.length}: {preview.attendees.join(", ")}</div>
          )}
          {preview.clashes?.length > 0 && (
            <div className="mt-1 text-xs font-medium text-rose-700">Clashes with {preview.clashes.join(", ")}</div>
          )}
        </div>
      );
    case "cancel":
      return (
        <div className="rounded-xl border border-stone-200 bg-stone-50 p-3 text-sm">
          <div className="flex items-baseline justify-between"><span className="font-medium">{preview.name}</span>
            <span className="tabular text-emerald-700">saves {money(preview.saves_per_month, 2)}/mo</span></div>
          <div className="mt-0.5 text-xs text-stone-500">Last used {preview.last_used_days} days ago</div>
        </div>
      );
    case "archive":
      return (
        <ul className="rounded-xl border border-stone-200 bg-stone-50 p-3 text-xs text-stone-700">
          {preview.subjects.map((s: string) => <li key={s} className="truncate">• {s}</li>)}
        </ul>
      );
    case "external":
      return <pre className="rounded-xl border border-stone-200 bg-stone-50 p-3 text-xs">{JSON.stringify(args, null, 2)}</pre>;
    default:
      return null;
  }
}

type Mode = "idle" | "edit" | "reject" | "respond";

export default function ApprovalCard({ approval, index, onDecide, busy, hotkeys }: {
  approval: Approval; index: number; onDecide: (d: Decision) => void; busy: boolean; hotkeys: boolean;
}) {
  const [mode, setMode] = useState<Mode>("idle");
  const [draft, setDraft] = useState<Record<string, any>>({});
  const [message, setMessage] = useState("");
  const risk = approval.risk;
  const level = LEVEL[risk?.level || "low"];
  const Icon = ICONS[approval.name] || Ticket;

  useEffect(() => { setMode("idle"); setMessage(""); setDraft({}); }, [approval.interrupt_id]);

  useEffect(() => {
    if (!hotkeys || mode !== "idle") return;
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || e.metaKey || e.ctrlKey) return;
      if (e.key === "a") { e.preventDefault(); onDecide({ type: "approve" }); }
      if (e.key === "r") { e.preventDefault(); setMode("reject"); }
      if (e.key === "e") { e.preventDefault(); startEdit(); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hotkeys, mode, approval.interrupt_id]);

  const startEdit = () => {
    const d: Record<string, any> = {};
    for (const [k, v] of Object.entries(approval.args)) d[k] = Array.isArray(v) ? v.join(", ") : v ?? "";
    setDraft(d);
    setMode("edit");
  };

  const submitEdit = () => {
    const args: Record<string, any> = {};
    for (const [k, v] of Object.entries(approval.args)) {
      const raw = draft[k];
      if (Array.isArray(v)) args[k] = String(raw).split(",").map((s) => s.trim()).filter(Boolean);
      else if (typeof v === "number") args[k] = Number(raw);
      else if (typeof v === "boolean") args[k] = Boolean(raw);
      else args[k] = raw;
    }
    onDecide({ type: "edit", edited_action: { name: approval.name, args } });
  };

  const fieldFor = (k: string, v: any) => {
    if (typeof v === "boolean") return (
      <label key={k} className="flex items-center gap-2 text-sm"><input type="checkbox" checked={!!draft[k]} onChange={(e) => setDraft({ ...draft, [k]: e.target.checked })} /> {k}</label>
    );
    const long = typeof v === "string" && (v.length > 60 || v.includes("\n"));
    return (
      <label key={k} className="block">
        <span className="text-[11px] font-medium uppercase tracking-wide text-stone-500">{k.replace(/_/g, " ")}</span>
        {long ? <textarea className="field mt-1 min-h-24 font-sans" value={draft[k]} onChange={(e) => setDraft({ ...draft, [k]: e.target.value })} />
              : <input className="field mt-1" type={typeof v === "number" ? "number" : "text"} step="any" value={draft[k]} onChange={(e) => setDraft({ ...draft, [k]: e.target.value })} />}
      </label>
    );
  };

  return (
    <article className="card animate-slide-up p-4" aria-label={`Approval ${index + 1}: ${describeCall(approval.name, approval.args, risk?.preview)}`}>
      <header className="flex items-start gap-3">
        <div className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-ember-100 text-ember-700">
          <Icon className="h-4.5 w-4.5" aria-hidden="true" />
        </div>
        <div className="min-w-0 flex-1">
          <h3 className="text-[15px] font-semibold leading-snug text-ink">{describeCall(approval.name, approval.args, risk?.preview)}</h3>
          <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
            <span className={`chip ${level.cls}`}><level.Icon className="h-3 w-3" aria-hidden="true" />{level.label}</span>
            {risk && !risk.reversible && <span className="chip border-stone-200 bg-stone-50 text-stone-600">Can't undo</span>}
            {risk?.jev && <span className="chip border-violet-200 bg-violet-50 text-violet-700" title={risk.jev.reason}>Jev {risk.jev.risky ? "flagged" : "ok"}{risk.jev.confidence != null ? ` · ${Math.round(risk.jev.confidence * 100)}%` : ""}</span>}
          </div>
          {risk?.reasons?.length ? (
            <ul className="mt-2 space-y-0.5 text-[13px] text-stone-600">
              {risk.reasons.map((r) => <li key={r}>· {r}</li>)}
            </ul>
          ) : null}
        </div>
      </header>

      <div className="mt-3"><Preview preview={risk?.preview} args={approval.args} /></div>

      {mode === "idle" && (
        <div className="mt-4 flex flex-wrap items-center gap-2">
          <button type="button" className="btn-accent" onClick={() => onDecide({ type: "approve" })} disabled={busy}>
            <Check className="h-4 w-4" aria-hidden="true" /> Approve {hotkeys && <kbd className="kbd ml-1 bg-ember-700/40 border-ember-400 text-white">A</kbd>}
          </button>
          <button type="button" className="btn-outline" onClick={startEdit} disabled={busy}>
            <Pencil className="h-4 w-4" aria-hidden="true" /> Edit {hotkeys && <kbd className="kbd ml-1">E</kbd>}
          </button>
          <button type="button" className="btn-outline" onClick={() => setMode("reject")} disabled={busy}>
            <X className="h-4 w-4" aria-hidden="true" /> Reject {hotkeys && <kbd className="kbd ml-1">R</kbd>}
          </button>
          <button type="button" className="btn-ghost" onClick={() => setMode("respond")} disabled={busy} title="Answer the agent instead of running this">
            <MessageSquare className="h-4 w-4" aria-hidden="true" /> Reply instead
          </button>
        </div>
      )}

      {mode === "edit" && (
        <form className="mt-4 space-y-3" onSubmit={(e) => { e.preventDefault(); submitEdit(); }}>
          <div className="grid gap-3 sm:grid-cols-2">{Object.entries(approval.args).map(([k, v]) => fieldFor(k, v))}</div>
          <div className="flex gap-2">
            <button type="submit" className="btn-accent" disabled={busy}><Check className="h-4 w-4" aria-hidden="true" /> Run with these changes</button>
            <button type="button" className="btn-ghost" onClick={() => setMode("idle")}><Undo2 className="h-4 w-4" aria-hidden="true" /> Back</button>
          </div>
        </form>
      )}

      {(mode === "reject" || mode === "respond") && (
        <form className="mt-4 space-y-2" onSubmit={(e) => { e.preventDefault(); onDecide(mode === "reject" ? { type: "reject", message } : { type: "respond", message }); }}>
          <label className="block text-[13px] text-stone-600">
            {mode === "reject" ? "Why? The agent will try something else." : "Your reply goes to the agent instead of running this action."}
            <textarea className="field mt-1 min-h-20" autoFocus value={message} onChange={(e) => setMessage(e.target.value)}
                      placeholder={mode === "reject" ? "e.g. Too expensive — find something under $100" : "e.g. I'll handle this one myself"} />
          </label>
          <div className="flex gap-2">
            <button type="submit" className={mode === "reject" ? "btn-primary" : "btn-accent"} disabled={busy || (mode === "respond" && !message.trim())}>
              {mode === "reject" ? <><X className="h-4 w-4" aria-hidden="true" /> Reject</> : <><MessageSquare className="h-4 w-4" aria-hidden="true" /> Send reply</>}
            </button>
            <button type="button" className="btn-ghost" onClick={() => setMode("idle")}>Back</button>
          </div>
        </form>
      )}
    </article>
  );
}
