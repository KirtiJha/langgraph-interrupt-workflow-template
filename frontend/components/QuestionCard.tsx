"use client";

// The agent asked something only you can answer (a raw interrupt() from a tool).

import { useEffect, useState } from "react";
import { CircleHelp, Send } from "lucide-react";
import { Question } from "../lib/api";

export default function QuestionCard({ question, onAnswer, busy }: { question: Question; onAnswer: (a: string) => void; busy: boolean }) {
  const [text, setText] = useState("");
  useEffect(() => setText(""), [question.interrupt_id]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || e.metaKey || e.ctrlKey) return;
      const n = Number(e.key);
      if (n >= 1 && n <= question.options.length) { e.preventDefault(); onAnswer(question.options[n - 1]); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [question, onAnswer]);

  return (
    <article className="card animate-slide-up border-violet-200 p-4" aria-label="The agent has a question">
      <header className="flex items-start gap-3">
        <div className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-violet-100 text-violet-700">
          <CircleHelp className="h-4.5 w-4.5" aria-hidden="true" />
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-violet-700">Your call</p>
          <p className="mt-1 text-[15px] leading-snug text-ink">{question.question}</p>
        </div>
      </header>
      {question.options.length > 0 && (
        <div className="mt-3 grid gap-2 sm:grid-cols-2">
          {question.options.map((o, i) => (
            <button key={o} type="button" disabled={busy} onClick={() => onAnswer(o)}
                    className="group flex items-center justify-between rounded-xl border border-stone-200 bg-white px-3 py-2.5 text-left text-sm font-medium text-ink transition-colors hover:border-violet-300 hover:bg-violet-50">
              <span>{o}</span><kbd className="kbd group-hover:border-violet-300">{i + 1}</kbd>
            </button>
          ))}
        </div>
      )}
      <form className="mt-3 flex gap-2" onSubmit={(e) => { e.preventDefault(); if (text.trim()) onAnswer(text.trim()); }}>
        <input className="field" value={text} onChange={(e) => setText(e.target.value)} placeholder="Or answer in your own words…" />
        <button type="submit" className="btn-primary shrink-0" disabled={busy || !text.trim()} aria-label="Send answer"><Send className="h-4 w-4" aria-hidden="true" /></button>
      </form>
    </article>
  );
}
