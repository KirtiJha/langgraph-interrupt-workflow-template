"use client";

// One pending action: what it is, how risky, what will be posted or changed —
// and the four decisions (approve / edit / reject / reply) that resume the agent.

import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import { Check, Eye, GitMerge, MessageSquare, Pencil, Plus, ShieldAlert, ShieldCheck, Tag, Undo2, User, X, CircleCheck } from "lucide-react";
import { Approval, Decision, Label, describeCall } from "../lib/api";

const ICONS: Record<string, any> = {
  add_labels: Tag, remove_labels: Tag, comment: MessageSquare, close_issue: CircleCheck, reopen_issue: Undo2, retitle: Pencil,
  create_issue: Plus, assign: User, request_reviewers: Eye, merge_pull: GitMerge,
};

const LEVEL = {
  low: { label: "Low risk", cls: "border-emerald-200 bg-emerald-50 text-emerald-700", Icon: ShieldCheck },
  medium: { label: "Medium risk", cls: "border-amber-200 bg-amber-50 text-amber-800", Icon: ShieldAlert },
  high: { label: "High risk", cls: "border-rose-200 bg-rose-50 text-rose-700", Icon: ShieldAlert },
};

export function LabelChip({ name, labels, ghost }: { name: string; labels?: Label[]; ghost?: boolean }) {
  const color = labels?.find((l) => l.name === name)?.color || "ededed";
  return (
    <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-medium ${ghost ? "border-dashed" : ""}`}
          style={{ backgroundColor: `#${color}22`, borderColor: `#${color}`, color: "#1c1917" }}>{name}</span>
  );
}

function Target({ p }: { p: any }) {
  if (!p?.number) return null;
  return (
    <div className="mb-2 flex items-center gap-2 text-xs text-stone-500">
      <span className="font-mono">#{p.number}</span>
      <span className="truncate text-stone-700">{p.title}</span>
      {p.is_pr && <span className="chip border-sky-200 bg-sky-50 text-sky-700">PR</span>}
      {p.url && <a href={p.url} target="_blank" rel="noreferrer" className="ml-auto shrink-0 text-ember-700 hover:underline">open ↗</a>}
    </div>
  );
}

export function Preview({ preview, labels }: { preview: any; labels?: Label[] }) {
  if (!preview) return null;
  const box = "rounded-xl border border-stone-200 bg-stone-50 p-3 text-sm";
  switch (preview.kind) {
    case "labels":
      return (
        <div className={box}><Target p={preview} />
          <div className="flex flex-wrap items-center gap-1.5">
            {preview.before.length ? preview.before.map((l: string) => <LabelChip key={l} name={l} labels={labels} />) : <span className="text-xs text-stone-400">no labels</span>}
            <span className="mx-1 text-stone-400">→</span>
            {preview.after.map((l: string) => <LabelChip key={l} name={l} labels={labels} ghost={!preview.before.includes(l)} />)}
          </div>
        </div>
      );
    case "comment":
      return (
        <div className="rounded-xl border border-stone-200 bg-white text-sm"><div className="px-3 pt-2"><Target p={preview} /></div>
          <div className="prose-steward max-h-56 overflow-auto border-t border-stone-100 px-3 py-2 text-[13px] leading-relaxed text-stone-800"><ReactMarkdown>{preview.body}</ReactMarkdown></div>
        </div>
      );
    case "close":
      return (
        <div className={box}><Target p={preview} />
          <div className="text-xs text-stone-600">Will close as <strong>{String(preview.reason || "completed").replace("_", " ")}</strong>
            {preview.comments ? ` · ${preview.comments} comment${preview.comments === 1 ? "" : "s"}` : ""}{preview.last_activity_days != null ? ` · last activity ${preview.last_activity_days}d ago` : ""}</div>
          {preview.note && <div className="prose-steward mt-2 rounded-lg border border-stone-200 bg-white px-3 py-2 text-[13px] text-stone-800"><ReactMarkdown>{preview.note}</ReactMarkdown></div>}
        </div>
      );
    case "retitle":
      return <div className={box}><Target p={preview} /><div className="text-xs text-stone-500 line-through">{preview.title}</div><div className="font-medium">{preview.new_title}</div></div>;
    case "assign":
    case "review":
      return <div className={box}><Target p={preview} /><div className="text-xs text-stone-600">{preview.kind === "assign" ? "Assign to" : "Request review from"} <strong>{(preview.assignees || preview.reviewers || []).map((u: string) => `@${u}`).join(", ")}</strong></div></div>;
    case "reopen":
      return <div className={box}><Target p={preview} /><div className="text-xs text-stone-600">Will reopen.</div></div>;
    case "new_issue":
      return (
        <div className="rounded-xl border border-dashed border-ember-400 bg-ember-50/60 text-sm">
          <div className="px-3 pt-2.5 font-medium text-ink">{preview.title}</div>
          <div className="flex flex-wrap gap-1 px-3 pt-1">{(preview.labels || []).map((l: string) => <LabelChip key={l} name={l} labels={labels} ghost />)}</div>
          <div className="prose-steward max-h-56 overflow-auto px-3 py-2 text-[13px] text-stone-800"><ReactMarkdown>{preview.body}</ReactMarkdown></div>
        </div>
      );
    case "merge":
      return <div className="rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm"><Target p={preview} /><div className="text-xs text-rose-800">Merges into the default branch ({preview.method}). This can't be undone.</div></div>;
    case "external":
      return <pre className={`${box} text-xs`}>{JSON.stringify(preview.args, null, 2)}</pre>;
    default:
      return null;
  }
}

type Mode = "idle" | "edit" | "reject" | "respond";

export default function ApprovalCard({ approval, index, onDecide, busy, hotkeys, labels }: {
  approval: Approval; index: number; onDecide: (d: Decision) => void; busy: boolean; hotkeys: boolean; labels?: Label[];
}) {
  const [mode, setMode] = useState<Mode>("idle");
  const [draft, setDraft] = useState<Record<string, any>>({});
  const [message, setMessage] = useState("");
  const risk = approval.risk;
  const level = LEVEL[risk?.level || "low"];
  const Icon = ICONS[approval.name] || Tag;
  const observe = !!risk?.observe;

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
    if (k === "number") return null;
    const long = typeof v === "string" && (v.length > 60 || v.includes("\n"));
    return (
      <label key={k} className={`block ${long ? "sm:col-span-2" : ""}`}>
        <span className="text-[11px] font-medium uppercase tracking-wide text-stone-500">{k.replace(/_/g, " ")}</span>
        {long ? <textarea className="field mt-1 min-h-32 font-sans" value={draft[k]} onChange={(e) => setDraft({ ...draft, [k]: e.target.value })} />
              : <input className="field mt-1" type={typeof v === "number" ? "number" : "text"} value={draft[k]} onChange={(e) => setDraft({ ...draft, [k]: e.target.value })} />}
      </label>
    );
  };

  return (
    <article className="card animate-slide-up p-4" aria-label={`Approval ${index + 1}: ${describeCall(approval.name, approval.args)}`}>
      <header className="flex items-start gap-3">
        <div className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-ember-100 text-ember-700"><Icon className="h-4.5 w-4.5" aria-hidden="true" /></div>
        <div className="min-w-0 flex-1">
          <h3 className="text-[15px] font-semibold leading-snug text-ink">{describeCall(approval.name, approval.args)}</h3>
          <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
            <span className={`chip ${level.cls}`}><level.Icon className="h-3 w-3" aria-hidden="true" />{level.label}</span>
            {risk && !risk.reversible && <span className="chip border-stone-200 bg-stone-50 text-stone-600">Can't undo</span>}
            {observe && <span className="chip border-violet-200 bg-violet-50 text-violet-700" title="Observe mode: approving records a proposal, nothing is posted">Proposal only</span>}
            {risk?.jev && <span className="chip border-violet-200 bg-violet-50 text-violet-700" title={risk.jev.reason}>Jev {risk.jev.risky ? "flagged" : "ok"}{risk.jev.confidence != null ? ` · ${Math.round(risk.jev.confidence * 100)}%` : ""}</span>}
          </div>
          {risk?.reasons?.length ? <ul className="mt-2 space-y-0.5 text-[13px] text-stone-600">{risk.reasons.map((r) => <li key={r}>· {r}</li>)}</ul> : null}
        </div>
      </header>

      <div className="mt-3"><Preview preview={risk?.preview} labels={labels} /></div>

      {mode === "idle" && (
        <div className="mt-4 flex flex-wrap items-center gap-2">
          <button type="button" className="btn-accent" onClick={() => onDecide({ type: "approve" })} disabled={busy}>
            <Check className="h-4 w-4" aria-hidden="true" /> {observe ? "Propose" : "Approve"} {hotkeys && <kbd className="kbd ml-1 border-ember-400 bg-ember-700/40 text-white">A</kbd>}
          </button>
          <button type="button" className="btn-outline" onClick={startEdit} disabled={busy}><Pencil className="h-4 w-4" aria-hidden="true" /> Edit {hotkeys && <kbd className="kbd ml-1">E</kbd>}</button>
          <button type="button" className="btn-outline" onClick={() => setMode("reject")} disabled={busy}><X className="h-4 w-4" aria-hidden="true" /> Reject {hotkeys && <kbd className="kbd ml-1">R</kbd>}</button>
          <button type="button" className="btn-ghost" onClick={() => setMode("respond")} disabled={busy} title="Answer the agent instead of running this"><MessageSquare className="h-4 w-4" aria-hidden="true" /> Reply instead</button>
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
            {mode === "reject" ? "Why? The agent learns the repo's norms from this." : "Your reply goes to the agent instead of running this action."}
            <textarea className="field mt-1 min-h-20" autoFocus value={message} onChange={(e) => setMessage(e.target.value)}
                      placeholder={mode === "reject" ? "e.g. Too formal — we keep comments casual here" : "e.g. I'll handle this one myself"} />
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
