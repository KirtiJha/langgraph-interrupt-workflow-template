"use client";

// "Connect" button + dialog: a GitHub token kept in this browser and sent per
// request. Without one, public repos are read-only and actions become proposals.

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { AlertCircle, CheckCircle, Github, KeyRound, Loader2, X } from "lucide-react";
import { clearGitHubToken, isTokenRemembered, saveGitHubToken, useGitHubToken } from "../lib/github";
import { API_URL } from "../lib/api";

export default function ConnectGitHubButton({ repo }: { repo: string }) {
  const token = useGitHubToken();
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState("");
  const [remember, setRemember] = useState(false);
  const [show, setShow] = useState(false);
  const [testing, setTesting] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; text: string } | null>(null);
  const dialogRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    setDraft(token || "");
    setRemember(isTokenRemembered());
    setResult(null);
    setShow(false);
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    window.addEventListener("keydown", onKey);
    dialogRef.current?.querySelector<HTMLElement>("input")?.focus();
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const test = async () => {
    setTesting(true);
    setResult(null);
    try {
      const res = await fetch(`${API_URL}/repos/inspect?repo=${encodeURIComponent(repo || "acme/pixelforge")}`,
                              { headers: draft.trim() ? { "X-GitHub-Token": draft.trim() } : {} });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) setResult({ ok: false, text: data?.detail || `HTTP ${res.status}` });
      else setResult({ ok: true, text: data.mode === "fixture" ? "Token accepted (the sample repo doesn't need one)."
        : data.can_write ? `Connected to ${data.repo.full_name} with write access.` : `Read ${data.repo.full_name}, but this token can't write — check its permissions.` });
    } catch {
      setResult({ ok: false, text: `Couldn't reach ${API_URL}.` });
    } finally {
      setTesting(false);
    }
  };

  const save = () => { saveGitHubToken(draft.trim(), remember); setOpen(false); };
  const disconnect = () => { clearGitHubToken(); setOpen(false); };

  return (
    <>
      <button type="button" onClick={() => setOpen(true)} aria-haspopup="dialog"
              title={token ? "GitHub connected — click to change" : "Connect a GitHub token to act on your repositories"}
              className={`flex items-center gap-1 text-xs font-medium rounded-full px-3 py-1.5 border transition-colors ${
                token ? "bg-emerald-50 hover:bg-emerald-100 border-emerald-200 text-emerald-700" : "bg-gray-50 hover:bg-gray-100 border-gray-200 text-gray-600 hover:text-gray-900"}`}>
        <Github className="w-3.5 h-3.5 shrink-0" aria-hidden="true" />
        <span className="truncate">{token ? "GitHub connected" : "Connect GitHub"}</span>
      </button>

      {open && createPortal(
        <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/30 p-0 sm:p-4"
             onMouseDown={(e) => e.target === e.currentTarget && setOpen(false)}>
          <div ref={dialogRef} role="dialog" aria-modal="true" aria-labelledby="connect-title"
               className="w-full sm:max-w-md max-h-[90dvh] overflow-y-auto rounded-t-2xl sm:rounded-2xl bg-paper shadow-lift p-5">
            <div className="flex items-start justify-between gap-3">
              <div>
                <h2 id="connect-title" className="text-base font-semibold text-gray-900">Connect GitHub</h2>
                <p className="mt-0.5 text-xs text-gray-500">A token lets the steward act on your repositories. Without one, public repos are read-only and every action becomes a proposal.</p>
              </div>
              <button type="button" onClick={() => setOpen(false)} aria-label="Close" className="rounded-full p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-700"><X className="w-4 h-4" aria-hidden="true" /></button>
            </div>

            <label className="mt-4 block">
              <span className="text-xs font-medium text-gray-700">Fine-grained personal access token</span>
              <div className="mt-1 flex gap-2">
                <input aria-label="GitHub token" className="field font-mono" type={show ? "text" : "password"} value={draft}
                       onChange={(e) => setDraft(e.target.value)} placeholder="github_pat_…" autoComplete="off" spellCheck={false} />
                <button type="button" onClick={() => setShow((v) => !v)} aria-pressed={show}
                        className="shrink-0 rounded-lg border border-gray-200 px-2 text-xs text-gray-600 hover:bg-gray-50">{show ? "Hide" : "Show"}</button>
              </div>
              <span className="mt-1 flex items-start gap-1 text-[11px] text-gray-500">
                <KeyRound className="mt-px w-3 h-3 shrink-0" aria-hidden="true" />
                Sent with each request to this app's backend, never stored there. Scope it to the repos you want managed with <strong>Issues</strong> and <strong>Pull requests: read &amp; write</strong>.
              </span>
            </label>
            <a className="mt-2 inline-block text-[11px] font-medium text-ember-700 hover:underline" target="_blank" rel="noreferrer"
               href="https://github.com/settings/personal-access-tokens/new">Create a token on GitHub ↗</a>

            <label className="mt-3 flex items-center gap-2 text-xs text-gray-700">
              <input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} className="rounded border-gray-300" />
              Remember on this device (otherwise cleared when the tab closes)
            </label>

            {result && (
              <div role="status" className={`mt-4 flex items-start gap-2 rounded-lg px-3 py-2 text-xs ${result.ok ? "bg-green-50 text-green-800" : "bg-rose-50 text-rose-700"}`}>
                {result.ok ? <CheckCircle className="mt-px w-3.5 h-3.5 shrink-0" aria-hidden="true" /> : <AlertCircle className="mt-px w-3.5 h-3.5 shrink-0" aria-hidden="true" />}
                <span className="break-words">{result.text}</span>
              </div>
            )}

            <div className="mt-5 flex flex-wrap items-center gap-2">
              {token && <button type="button" onClick={disconnect} className="text-xs font-medium text-gray-500 hover:text-gray-800 hover:underline">Disconnect</button>}
              <div className="ml-auto flex gap-2">
                <button type="button" onClick={test} disabled={testing}
                        className="flex items-center gap-1 rounded-lg border border-gray-200 px-3 py-2 text-xs font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50">
                  {testing && <Loader2 className="w-3.5 h-3.5 animate-spin" aria-hidden="true" />} Test
                </button>
                <button type="button" onClick={save} disabled={!draft.trim()} className="btn-accent h-9 px-4 text-xs">Save</button>
              </div>
            </div>
          </div>
        </div>,
        document.body
      )}
    </>
  );
}
